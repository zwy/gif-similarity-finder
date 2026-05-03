from collections import defaultdict
from pathlib import Path
import hashlib
import logging
import os

import numpy as np
from tqdm import tqdm

from .io import sample_frames
from .types import EmbeddingCacheData, Stage2Result


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Device / Model
# ---------------------------------------------------------------------------

def load_clip_model(device: str):
    import clip
    import torch

    if device == "auto":
        if torch.backends.mps.is_available():
            device = "mps"
        elif torch.cuda.is_available():
            device = "cuda"
        else:
            device = "cpu"
    model, preprocess = clip.load("ViT-B/32", device=device)
    model.eval()
    return model, preprocess, device


# ---------------------------------------------------------------------------
# Cache key: (filename, filesize, mtime) — survives folder renames
# ---------------------------------------------------------------------------

def _cache_key(path: Path) -> str:
    """Stable cache key based on file identity rather than path string."""
    try:
        stat = path.stat()
        raw = f"{path.name}:{stat.st_size}:{stat.st_mtime_ns}"
    except OSError:
        raw = str(path)
    return hashlib.md5(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Frame-weighted pooling helpers
# ---------------------------------------------------------------------------

def _frame_diff_weights(frames) -> np.ndarray:
    """
    Compute per-frame importance weights via mean absolute pixel difference
    to the previous frame. The first frame always gets weight 1.0.
    Returns a float32 array summing to 1.
    """
    if len(frames) == 1:
        return np.array([1.0], dtype=np.float32)

    arrays = [np.asarray(f, dtype=np.float32) for f in frames]
    diffs = [1.0]  # first frame baseline weight
    for i in range(1, len(arrays)):
        diff = np.mean(np.abs(arrays[i] - arrays[i - 1]))
        diffs.append(float(diff) + 1e-6)  # avoid zero weights

    weights = np.array(diffs, dtype=np.float32)
    weights /= weights.sum()
    return weights


# ---------------------------------------------------------------------------
# True batch CLIP inference
# ---------------------------------------------------------------------------

def extract_batch_embeddings(
    batch_paths: list[Path],
    model,
    preprocess,
    device: str,
    n_frames: int,
    pool: str = "weighted_mean",   # "mean" | "max" | "weighted_mean"
) -> list[tuple[Path, np.ndarray]]:
    """
    Process a batch of GIFs in a single model.encode_image() call.
    Returns a list of (path, embedding) for successfully processed GIFs.
    """
    import torch
    import torch.nn.functional as F

    per_gif_frames: list[list] = []
    per_gif_weights: list[np.ndarray] = []
    valid_paths: list[Path] = []

    for path in batch_paths:
        frames = sample_frames(path, n_frames)
        if not frames:
            log.warning("No frames sampled from '%s', skipping.", path.name)
            continue
        weights = _frame_diff_weights(frames) if pool == "weighted_mean" else None
        per_gif_frames.append(frames)
        per_gif_weights.append(weights)
        valid_paths.append(path)

    if not valid_paths:
        return []

    # Flatten all frames into one big batch tensor
    all_tensors: list = []
    frame_counts: list[int] = []
    for frames in per_gif_frames:
        tensors = [preprocess(f) for f in frames]
        all_tensors.extend(tensors)
        frame_counts.append(len(tensors))

    try:
        big_tensor = torch.stack(all_tensors).to(device)  # [total_frames, C, H, W]
        with torch.no_grad():
            all_emb = model.encode_image(big_tensor)       # [total_frames, D]
            all_emb = F.normalize(all_emb.float(), dim=-1)
    except Exception as exc:
        log.warning("CLIP batch inference failed: %s", exc)
        return []

    # Split back per GIF and pool
    results: list[tuple[Path, np.ndarray]] = []
    cursor = 0
    for i, (path, count) in enumerate(zip(valid_paths, frame_counts)):
        gif_emb = all_emb[cursor : cursor + count]  # [n_frames, D]
        cursor += count

        if pool == "max":
            pooled = gif_emb.max(dim=0).values
        elif pool == "weighted_mean":
            w = torch.tensor(per_gif_weights[i], dtype=torch.float32, device=device)
            pooled = (gif_emb * w.unsqueeze(1)).sum(dim=0)
        else:  # plain mean
            pooled = gif_emb.mean(dim=0)

        pooled = F.normalize(pooled, dim=-1)
        results.append((path, pooled.cpu().numpy()))

    return results


# ---------------------------------------------------------------------------
# Full extraction with incremental cache
# ---------------------------------------------------------------------------

def extract_all_embeddings(
    gif_paths: list[Path],
    model,
    preprocess,
    device: str,
    n_frames: int,
    batch_size: int,
    cache_data: EmbeddingCacheData | None,
    pool: str = "weighted_mean",
) -> tuple[list[Path], np.ndarray]:
    # Build cache lookup by stable key
    cache_lookup: dict[str, np.ndarray] = {}
    if cache_data:
        for path, emb in zip(cache_data.paths, cache_data.embeddings):
            cache_lookup[_cache_key(path)] = emb

    valid_paths: list[Path] = []
    embedding_list: list[np.ndarray] = []
    remaining: list[Path] = []

    for path in gif_paths:
        key = _cache_key(path)
        if key in cache_lookup:
            valid_paths.append(path)
            embedding_list.append(cache_lookup[key])
        else:
            remaining.append(path)

    log.info("Cache hit: %d / %d  |  To process: %d", len(valid_paths), len(gif_paths), len(remaining))

    # Process remaining in true batches
    for offset in tqdm(range(0, len(remaining), batch_size), desc="Extracting CLIP embeddings"):
        batch = remaining[offset : offset + batch_size]
        pairs = extract_batch_embeddings(batch, model, preprocess, device, n_frames, pool=pool)
        for path, emb in pairs:
            valid_paths.append(path)
            embedding_list.append(emb)

    if not embedding_list:
        return valid_paths, np.empty((0, 0), dtype=np.float32)
    return valid_paths, np.stack(embedding_list).astype(np.float32)


# ---------------------------------------------------------------------------
# HDBSCAN clustering
# ---------------------------------------------------------------------------

def cluster_hdbscan(embeddings: np.ndarray, min_cluster_size: int) -> np.ndarray:
    """
    HDBSCAN with:
    - cosine metric (appropriate for L2-normalized CLIP vectors)
    - multi-core core distance computation
    - optional FAISS-precomputed KNN graph for very large datasets (n > 20k)
    """
    n = len(embeddings)
    log.info("Running HDBSCAN on %d vectors (dim=%d)", n, embeddings.shape[1])

    if n > 20_000:
        return _hdbscan_with_faiss_knn(embeddings, min_cluster_size)

    from sklearn.cluster import HDBSCAN
    return HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=1,
        metric="cosine",
        cluster_selection_method="eom",
        n_jobs=max(1, (os.cpu_count() or 1) - 1),
    ).fit_predict(embeddings)


def _hdbscan_with_faiss_knn(embeddings: np.ndarray, min_cluster_size: int) -> np.ndarray:
    """
    For large datasets (>20k): use FAISS IVF to build approximate KNN graph,
    then feed a precomputed sparse distance matrix to HDBSCAN.
    Embeddings must be L2-normalized (cosine similarity = inner product).
    Falls back to plain sklearn HDBSCAN if faiss is not installed.
    """
    try:
        import faiss
        from sklearn.cluster import HDBSCAN
        from scipy.sparse import csr_matrix

        n, d = embeddings.shape
        k = min(32, n - 1)

        nlist = min(int(np.sqrt(n)), 256)
        quantizer = faiss.IndexFlatIP(d)
        index = faiss.IndexIVFFlat(quantizer, d, nlist, faiss.METRIC_INNER_PRODUCT)
        index.train(embeddings)
        index.add(embeddings)
        index.nprobe = min(nlist, 32)

        distances, indices = index.search(embeddings, k + 1)  # +1 includes self
        cos_distances = 1.0 - np.clip(distances[:, 1:], -1, 1)
        neighbours = indices[:, 1:]

        rows = np.repeat(np.arange(n), k)
        cols = neighbours.ravel()
        data = cos_distances.ravel()
        mat = csr_matrix((data, (rows, cols)), shape=(n, n))
        mat = (mat + mat.T) / 2

        return HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=1,
            metric="precomputed",
            cluster_selection_method="eom",
            n_jobs=max(1, (os.cpu_count() or 1) - 1),
        ).fit_predict(mat)

    except ImportError:
        log.warning("faiss not available for large-scale KNN; falling back to sklearn HDBSCAN.")
        from sklearn.cluster import HDBSCAN
        return HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=1,
            metric="cosine",
            cluster_selection_method="eom",
            n_jobs=max(1, (os.cpu_count() or 1) - 1),
        ).fit_predict(embeddings)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_stage2(
    gif_paths: list[Path],
    n_frames: int,
    batch_size: int,
    min_cluster_size: int,
    device: str,
    cache_data: EmbeddingCacheData | None,
    pool: str = "weighted_mean",  # "mean" | "max" | "weighted_mean"
) -> Stage2Result:
    model, preprocess, resolved_device = load_clip_model(device)
    valid_paths, embeddings = extract_all_embeddings(
        gif_paths=gif_paths,
        model=model,
        preprocess=preprocess,
        device=resolved_device,
        n_frames=n_frames,
        batch_size=batch_size,
        cache_data=cache_data,
        pool=pool,
    )
    if len(valid_paths) == 0:
        return Stage2Result(
            groups={},
            valid_paths=[],
            embeddings=np.empty((0, 0), dtype=np.float32),
            labels=np.array([], dtype=np.int64),
        )

    labels = cluster_hdbscan(embeddings, min_cluster_size)
    grouped: dict[int, list[str]] = defaultdict(list)
    for path, label in zip(valid_paths, labels):
        grouped[int(label)].append(str(path))
    ordered = dict(sorted(grouped.items(), key=lambda item: -len(item[1])))
    return Stage2Result(groups=ordered, valid_paths=valid_paths, embeddings=embeddings, labels=labels)
