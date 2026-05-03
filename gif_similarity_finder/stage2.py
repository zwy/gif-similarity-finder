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

# Preprocessing modes
# - "color"     : original RGB frames (no preprocessing)  [default]
# - "grayscale" : luminance-only, 3-channel RGB — strips colour bias
# - "edge"      : grayscale + edge enhancement blended at alpha=0.4
PREPROCESS_MODES = ("color", "grayscale", "edge")


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
# Frame preprocessing
# ---------------------------------------------------------------------------

def _preprocess_frame(frame, mode: str):
    """
    Apply preprocessing to a single PIL Image before CLIP encoding.

    Modes
    -----
    color     — no-op, returns original RGB frame.
    grayscale — converts to luminance (L) then back to RGB (3-channel).
    edge      — grayscale base blended with FIND_EDGES output (alpha=0.4).
    """
    from PIL import Image, ImageFilter

    if mode == "color":
        return frame

    gray = frame.convert("L")

    if mode == "grayscale":
        return gray.convert("RGB")

    # mode == "edge"
    edges = gray.filter(ImageFilter.FIND_EDGES)
    blended = Image.blend(gray, edges, alpha=0.4)
    return blended.convert("RGB")


# ---------------------------------------------------------------------------
# Cache key
# ---------------------------------------------------------------------------

def _cache_key(path: Path) -> str:
    """Stable cache key based on full path + file identity."""
    try:
        stat = path.stat()
        raw = f"{path}:{stat.st_size}:{stat.st_mtime_ns}"
    except OSError:
        raw = str(path)
    return hashlib.md5(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# True batch CLIP inference
# ---------------------------------------------------------------------------

def _extract_one_by_one(
    batch_paths: list[Path],
    model,
    preprocess,
    device: str,
    n_frames: int,
    pool: str,
    preprocess_mode: str,
) -> list[tuple[Path, np.ndarray]]:
    """Fallback: process GIFs individually when a whole batch fails."""
    import torch
    import torch.nn.functional as F

    results = []
    for path in batch_paths:
        try:
            frames = sample_frames(path, n_frames)
            if not frames:
                continue
            frames = [_preprocess_frame(f, preprocess_mode) for f in frames]
            tensors = [preprocess(f) for f in frames]
            tensor = torch.stack(tensors).to(device)
            with torch.no_grad():
                emb = model.encode_image(tensor)
                emb = F.normalize(emb.float(), dim=-1)
            pooled = _pool(emb, pool)
            pooled = F.normalize(pooled, dim=-1)
            results.append((path, pooled.cpu().numpy()))
        except Exception as exc:
            log.warning("Skipping '%s': %s", path.name, exc)
    return results


def _pool(gif_emb, pool: str):
    """Pool a [n_frames, D] embedding tensor to [D]."""
    import torch

    count = gif_emb.shape[0]
    if pool == "max":
        return gif_emb.max(dim=0).values

    elif pool == "weighted_mean":
        if count == 1:
            return gif_emb[0]
        cos_sim = (gif_emb[:-1] * gif_emb[1:]).sum(dim=1)
        diffs = 1.0 - cos_sim.clamp(-1.0, 1.0)
        first_w = diffs.mean().unsqueeze(0)
        weights = torch.cat([first_w, diffs], dim=0)
        weights = weights / weights.sum()
        return (gif_emb * weights.unsqueeze(1)).sum(dim=0)

    else:  # plain mean
        return gif_emb.mean(dim=0)


def extract_batch_embeddings(
    batch_paths: list[Path],
    model,
    preprocess,
    device: str,
    n_frames: int,
    pool: str = "weighted_mean",
    preprocess_mode: str = "color",
) -> list[tuple[Path, np.ndarray]]:
    import torch
    import torch.nn.functional as F
    from concurrent.futures import ThreadPoolExecutor

    per_gif_frames: list[list] = []
    valid_paths: list[Path] = []

    for path in batch_paths:
        frames = sample_frames(path, n_frames)
        if not frames:
            log.warning("No frames sampled from '%s', skipping.", path.name)
            continue
        frames = [_preprocess_frame(f, preprocess_mode) for f in frames]
        per_gif_frames.append(frames)
        valid_paths.append(path)

    if not valid_paths:
        return []

    all_frames_flat = [f for frames in per_gif_frames for f in frames]
    frame_counts = [len(frames) for frames in per_gif_frames]

    with ThreadPoolExecutor() as ex:
        all_tensors = list(ex.map(preprocess, all_frames_flat))

    try:
        big_tensor = torch.stack(all_tensors).to(device)
        with torch.no_grad():
            all_emb = model.encode_image(big_tensor)
            all_emb = F.normalize(all_emb.float(), dim=-1)
    except Exception as exc:
        log.warning("Batch inference failed (%s), retrying individually…", exc)
        return _extract_one_by_one(valid_paths, model, preprocess, device, n_frames, pool, preprocess_mode)

    results: list[tuple[Path, np.ndarray]] = []
    cursor = 0
    for path, count in zip(valid_paths, frame_counts):
        gif_emb = all_emb[cursor : cursor + count]
        cursor += count
        pooled = _pool(gif_emb, pool)
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
    preprocess_mode: str = "color",
) -> tuple[list[Path], np.ndarray]:
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

    for offset in tqdm(range(0, len(remaining), batch_size), desc="Extracting CLIP embeddings"):
        batch = remaining[offset : offset + batch_size]
        pairs = extract_batch_embeddings(
            batch, model, preprocess, device, n_frames,
            pool=pool, preprocess_mode=preprocess_mode,
        )
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
    try:
        import faiss
        from sklearn.cluster import HDBSCAN
        from scipy.sparse import csr_matrix

        n, d = embeddings.shape
        k = min(32, n - 1)
        nlist = int(np.clip(4 * np.sqrt(n), 64, 4096))
        nprobe = max(1, nlist // 8)

        quantizer = faiss.IndexFlatIP(d)
        index = faiss.IndexIVFFlat(quantizer, d, nlist, faiss.METRIC_INNER_PRODUCT)
        index.train(embeddings)
        index.add(embeddings)
        index.nprobe = nprobe

        log.info("FAISS IVF: nlist=%d, nprobe=%d, k=%d", nlist, nprobe, k)

        distances, indices = index.search(embeddings, k + 1)
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
    pool: str = "weighted_mean",
    preprocess_mode: str = "color",  # "color" | "grayscale" | "edge"
) -> Stage2Result:
    log.info("Stage 2 preprocess_mode: %s", preprocess_mode)
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
        preprocess_mode=preprocess_mode,
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
