from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass(slots=True)
class PipelineConfig:
    input_dir: Path
    output_dir: Path
    frames: int
    hash_threshold: int
    min_cluster_size: int
    batch_size: int
    device: str
    skip_stage1: bool
    skip_stage2: bool
    # Frame preprocessing mode for CLIP encoding:
    #   "color"     — original RGB (no transformation)
    #   "grayscale" — luminance only, reduces colour/scene bias  [default]
    #   "edge"      — grayscale + edge enhancement, focuses on contours/pose
    preprocess_mode: str = "grayscale"


@dataclass(slots=True)
class Stage1Result:
    groups: dict[int, list[str]]
    hashed_paths: list[Path]
    match_count: int


@dataclass(slots=True)
class EmbeddingCacheData:
    paths: list[Path]
    embeddings: np.ndarray


@dataclass(slots=True)
class Stage2Result:
    groups: dict[int, list[str]]
    valid_paths: list[Path]
    embeddings: np.ndarray
    labels: np.ndarray
