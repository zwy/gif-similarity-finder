from collections import defaultdict
from pathlib import Path
import logging

import numpy as np
from tqdm import tqdm

from .io import sample_frames
from .types import EmbeddingCacheData, Stage2Result


log = logging.getLogger(__name__)


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


def extract_gif_embedding(gif_path: Path, model, preprocess, device: str, n_frames: int = 8) -> np.ndarray | None:
    import torch

    frames = sample_frames(gif_path, n_frames)
    if not frames:
        return None
    try:
        tensors = torch.stack([preprocess(frame) for frame in frames]).to(device)
        with torch.no_grad():
            embedding = model.encode_image(tensors).mean(dim=0)
            embedding = embedding / embedding.norm()
        return embedding.cpu().float().numpy()
    except Exception as exc:
        log.warning("CLIP failed for '%s': %s", gif_path.name, exc)
        return None


def extract_all_embeddings(
    gif_paths: list[Path],
    model,
    preprocess,
    device: str,
    n_frames: int,
    batch_size: int,
    cache_data: EmbeddingCacheData | None,
) -> tuple[list[Path], np.ndarray]:
    cached_paths = cache_data.paths if cache_data else []
    cached_embeddings = list(cache_data.embeddings) if cache_data else []
    cached_set = {str(path) for path in cached_paths}
    remaining = [path for path in gif_paths if str(path) not in cached_set]

    valid_paths = list(cached_paths)
    embedding_list = list(cached_embeddings)
    for offset in tqdm(range(0, len(remaining), batch_size), desc="Extracting CLIP embeddings"):
        for path in remaining[offset : offset + batch_size]:
            embedding = extract_gif_embedding(path, model, preprocess, device, n_frames)
            if embedding is not None:
                valid_paths.append(path)
                embedding_list.append(embedding)

    if not embedding_list:
        return valid_paths, np.empty((0, 0), dtype=np.float32)
    return valid_paths, np.stack(embedding_list).astype(np.float32)


def cluster_hdbscan(embeddings: np.ndarray, min_cluster_size: int) -> np.ndarray:
    from sklearn.cluster import HDBSCAN

    return HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=1,
        metric="euclidean",
        cluster_selection_method="eom",
    ).fit_predict(embeddings)


def run_stage2(
    gif_paths: list[Path],
    n_frames: int,
    batch_size: int,
    min_cluster_size: int,
    device: str,
    cache_data: EmbeddingCacheData | None,
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
