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

    For weighted_mean pooling, weights are computed in embedding space
    (cosine distance between consecutive frame embeddings) rather than
    pixel space — more semantically accurate and much cheaper to compute.
    """
    import torch
    import torch.nn.functional as F
    from concurrent.futures import ThreadPoolExecutor

    # Sample frames for each GIF
    per_gif_frames: list[list] = []
    valid_paths: list[Path] = []

    for path in batch_paths:
        frames = sample_frames(path, n_frames)
        if not frames:
            log.warning("No frames sampled from '%s', skipping.", path.name)
            continue
        per_gif_frames.append(frames)
        valid_paths.append(path)

    if not valid_paths:
        return []

    # Flatten frames and preprocess in parallel (CPU-bound resize/normalize)
    all_frames_flat = [f for frames in per_gif_frames for f in frames]
    frame_counts = [len(frames) for frames in per_gif_frames]

    with ThreadPoolExecutor() as ex:
        all_tensors = list(ex.map(preprocess, all_frames_flat))

    try:
        big_tensor = torch.stack(all_tensors).to(device)  # [total_frames, C, H, W]
        with torch.no_grad():
            all_emb = model.encode_image(big_tensor)       # [total_frames, D]
            all_emb = F.normalize(all_emb.float(), dim=-1)
    except Exception as exc:
        log.warning("CLIP batch inference failed: %s", exc)
        return []

    # Split back per GIF, compute weights in embedding space, then pool
    results: list[tuple[Path, np.ndarray]] = []
    cursor = 0
    for path, count in zip(valid_paths, frame_counts):
        gif_emb = all_emb[cursor : cursor + count]  # [n_frames, D]
        cursor += count

        if pool == "max":
            pooled = gif_emb.max(dim=0).values

        elif pool == "weighted_mean":
            # Embedding-space inter-frame difference as importance weight.
            # First frame gets the mean difference as a neutral baseline.
            if count == 1:
                pooled = gif_emb[0]
            else:
                diffs = (gif_emb[1:] - gif_emb[:-1]).abs().mean(dim=1)  # [n_frames-1]
                first_w = diffs.mean().unsqueeze(0)                       # neutral baseline
                weights = torch.cat([first_w, diffs], dim=0)              # [n_frames]
                weights = weights / weights.sum()
                pooled = (gif_emb * weights.unsqueeze(1)).sum(dim=0)

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
    HDBSCAN with cosine metric and multi-core support.
    Automatically switches to FAISS-accelerated KNN for n > 20k.
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
        copy=False,
        n_jobs=max(1, (os.cpu_count() or 1) - 1),
    ).fit_predict(embeddings)


def _hdbscan_with_faiss_knn(embeddings: np.ndarray, min_cluster_size: int) -> np.ndarray:
    """
    For large datasets (>20k): use FAISS IVF to build an approximate KNN graph,
    then feed a precomputed sparse distance matrix to HDBSCAN.

    nlist formula: clamp(4 * sqrt(n), 64, 4096) — empirically better recall
    than the conservative sqrt(n) at 100k scale.
    """
    try:
        import faiss
        from sklearn.cluster import HDBSCAN
        from scipy.sparse import csr_matrix

        n, d = embeddings.shape
        k = min(32, n - 1)

        # Better nlist: 4*sqrt(n) gives ~1265 for n=100k vs the old 256
        nlist = int(np.clip(4 * np.sqrt(n), 64, 4096))
        nprobe = max(1, nlist // 8)  # search ~12.5% of lists — good recall/speed tradeoff

        quantizer = faiss.IndexFlatIP(d)
        index = faiss.IndexIVFFlat(quantizer, d, nlist, faiss.METRIC_INNER_PRODUCT)
        index.train(embeddings)
        index.add(embeddings)
        index.nprobe = nprobe

        log.info("FAISS IVF: nlist=%d, nprobe=%d, k=%d", nlist, nprobe, k)

        distances, indices = index.search(embeddings, k + 1)  # +1 includes self
        cos_distances = 1.0 - np.clip(distances[:, 1:], -1, 1)  # drop self (col 0)
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
            copy=False,
            n_jobs=max(1, (os.cpu_count() or 1) - 1),
        ).fit_predict(mat)

    except ImportError:
        log.warning("faiss not available; falling back to sklearn HDBSCAN.")
        from sklearn.cluster import HDBSCAN
        return HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=1,
            metric="cosine",
            cluster_selection_method="eom",
            copy=False,
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
