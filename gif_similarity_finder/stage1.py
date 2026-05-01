from collections import defaultdict
from pathlib import Path
import logging

import numpy as np
from tqdm import tqdm

from .io import sample_frames
from .types import Stage1Result


log = logging.getLogger(__name__)


def compute_phash(gif_path: Path, n_frames: int = 6) -> np.ndarray | None:
    import imagehash

    frames = sample_frames(gif_path, n_frames)
    if not frames:
        return None
    try:
        return np.array([imagehash.phash(frame).hash.flatten().astype(np.uint8) for frame in frames])
    except Exception as exc:
        log.warning("pHash failed for '%s': %s", gif_path.name, exc)
        return None


def hamming_distance_frames(h1: np.ndarray, h2: np.ndarray) -> float:
    compared = min(len(h1), len(h2))
    distances = [np.sum(h1[index] != h2[index]) for index in range(compared)]
    return float(np.mean(distances))


def run_stage1(gif_paths: list[Path], hash_threshold: int) -> Stage1Result:
    hashes: dict[Path, np.ndarray] = {}
    for path in tqdm(gif_paths, desc="Computing pHash"):
        hashed = compute_phash(path)
        if hashed is not None:
            hashes[path] = hashed

    valid_paths = list(hashes.keys())
    parent = list(range(len(valid_paths)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        root_left = find(left)
        root_right = find(right)
        if root_left != root_right:
            parent[root_left] = root_right

    match_count = 0
    for left in tqdm(range(len(valid_paths)), desc="Grouping by pHash"):
        for right in range(left + 1, len(valid_paths)):
            if hamming_distance_frames(hashes[valid_paths[left]], hashes[valid_paths[right]]) <= hash_threshold:
                union(left, right)
                match_count += 1

    raw_groups: dict[int, list[str]] = defaultdict(list)
    for index, path in enumerate(valid_paths):
        raw_groups[find(index)].append(str(path))

    grouped = {group_id: members for group_id, members in raw_groups.items() if len(members) > 1}
    ordered = {
        new_id: members
        for new_id, (_, members) in enumerate(sorted(grouped.items(), key=lambda item: -len(item[1])))
    }
    ordered[-1] = [str(path) for path in valid_paths if not any(str(path) in values for values in grouped.values())]
    return Stage1Result(groups=ordered, hashed_paths=valid_paths, match_count=match_count)
