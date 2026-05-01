# Architecture Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the single-file GIF similarity tool into a thin CLI plus reusable internal package with clear boundaries between orchestration, computation, and artifact persistence.

**Architecture:** Keep `gif_similarity.py` as the user-facing entrypoint, but move reusable logic into a new `gif_similarity_finder/` package. Stage modules return typed result objects, the pipeline coordinates stage execution, and the artifacts layer owns all disk writes.

**Tech Stack:** Python 3.10+, Pillow, NumPy, tqdm, imagehash, CLIP/PyTorch, hnswlib, scikit-learn, optional umap-learn/matplotlib, stdlib `unittest`

---

## Planned File Structure

### Create

- `gif_similarity_finder/__init__.py` — package export surface
- `gif_similarity_finder/types.py` — shared dataclasses and config models
- `gif_similarity_finder/io.py` — GIF discovery and frame sampling helpers
- `gif_similarity_finder/stage1.py` — Stage 1 pHash computation and grouping
- `gif_similarity_finder/stage2.py` — Stage 2 CLIP embedding extraction and clustering
- `gif_similarity_finder/artifacts.py` — JSON/cache/index/report/visualization persistence
- `gif_similarity_finder/pipeline.py` — end-to-end orchestration
- `tests/__init__.py` — make the tests package importable by `unittest`
- `tests/test_io.py` — IO helper tests
- `tests/test_stage1.py` — Stage 1 logic tests
- `tests/test_artifacts.py` — artifact persistence tests
- `tests/test_pipeline.py` — pipeline orchestration tests

### Modify

- `gif_similarity.py` — reduce to CLI argument parsing and pipeline invocation
- `README.md` — update the architecture section and output/index naming if it changes during the refactor

## Shared Contracts

Use these shared types consistently across all tasks:

```python
from dataclasses import dataclass
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
```

### Task 1: Create the package skeleton and shared types

**Files:**
- Create: `gif_similarity_finder/__init__.py`
- Create: `gif_similarity_finder/types.py`
- Create: `tests/__init__.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing shared-type test**

```python
import unittest
from pathlib import Path

from gif_similarity_finder.types import PipelineConfig, Stage1Result


class TypesTest(unittest.TestCase):
    def test_pipeline_config_stores_cli_values(self) -> None:
        config = PipelineConfig(
            input_dir=Path("input"),
            output_dir=Path("output"),
            frames=8,
            hash_threshold=10,
            min_cluster_size=3,
            batch_size=32,
            device="auto",
            skip_stage1=False,
            skip_stage2=True,
        )

        self.assertEqual(config.output_dir, Path("output"))
        self.assertTrue(config.skip_stage2)

    def test_stage1_result_uses_integer_group_keys(self) -> None:
        result = Stage1Result(groups={0: ["a.gif"], -1: ["b.gif"]}, hashed_paths=[], match_count=0)
        self.assertEqual(sorted(result.groups.keys()), [-1, 0])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m unittest tests.test_pipeline -v`

Expected: `ModuleNotFoundError: No module named 'gif_similarity_finder'`

- [ ] **Step 3: Create the package entrypoint and shared dataclasses**

```python
# gif_similarity_finder/__init__.py
from .types import EmbeddingCacheData, PipelineConfig, Stage1Result, Stage2Result

__all__ = [
    "EmbeddingCacheData",
    "PipelineConfig",
    "Stage1Result",
    "Stage2Result",
]
```

```python
# gif_similarity_finder/types.py
from dataclasses import dataclass
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
```

```python
# tests/__init__.py
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m unittest tests.test_pipeline -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add gif_similarity_finder/__init__.py gif_similarity_finder/types.py tests/__init__.py tests/test_pipeline.py
git commit -m "refactor: add package types scaffold"
```

### Task 2: Extract GIF discovery and frame sampling into `io.py`

**Files:**
- Create: `gif_similarity_finder/io.py`
- Test: `tests/test_io.py`

- [ ] **Step 1: Write the failing IO tests**

```python
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from gif_similarity_finder.io import collect_gifs, sample_frames


class IoTest(unittest.TestCase):
    def test_collect_gifs_deduplicates_case_variants(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "a.gif").write_bytes(b"GIF89a")
            (root / "b.GIF").write_bytes(b"GIF89a")

            paths = collect_gifs(root)

            self.assertEqual([path.name for path in paths], ["a.gif", "b.GIF"])

    def test_sample_frames_returns_requested_count_or_less(self) -> None:
        fake_frames = [Image.new("RGB", (8, 8), color=(i, i, i)) for i in range(5)]

        with mock.patch("gif_similarity_finder.io.Image.open"), mock.patch(
            "gif_similarity_finder.io.ImageSequence.Iterator",
            return_value=fake_frames,
        ):
            frames = sample_frames(Path("demo.gif"), n_frames=3)

        self.assertEqual(len(frames), 3)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m unittest tests.test_io -v`

Expected: `ModuleNotFoundError: No module named 'gif_similarity_finder.io'`

- [ ] **Step 3: Write the minimal IO module**

```python
from pathlib import Path
import logging

import numpy as np
from PIL import Image, ImageSequence


log = logging.getLogger(__name__)


def collect_gifs(folder: str | Path) -> list[Path]:
    root = Path(folder)
    gifs = sorted(root.rglob("*.gif")) + sorted(root.rglob("*.GIF"))
    seen: set[str] = set()
    result: list[Path] = []
    for path in gifs:
        resolved = str(path.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        result.append(path)
    return result


def sample_frames(gif_path: Path, n_frames: int = 8) -> list[Image.Image]:
    try:
        gif = Image.open(gif_path)
        frames = [frame.copy().convert("RGB") for frame in ImageSequence.Iterator(gif)]
        if not frames:
            return []
        indices = np.linspace(0, len(frames) - 1, min(n_frames, len(frames)), dtype=int)
        return [frames[index] for index in indices]
    except Exception as exc:
        log.warning("Cannot read '%s': %s", gif_path.name, exc)
        return []
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m unittest tests.test_io -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add gif_similarity_finder/io.py tests/test_io.py
git commit -m "refactor: extract gif io helpers"
```

### Task 3: Extract Stage 1 computation into a pure stage module

**Files:**
- Create: `gif_similarity_finder/stage1.py`
- Test: `tests/test_stage1.py`

- [ ] **Step 1: Write the failing Stage 1 tests**

```python
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from gif_similarity_finder.stage1 import hamming_distance_frames, run_stage1


class Stage1Test(unittest.TestCase):
    def test_hamming_distance_uses_shortest_length(self) -> None:
        left = np.array([[1, 0, 1], [1, 1, 0]], dtype=np.uint8)
        right = np.array([[1, 1, 1]], dtype=np.uint8)
        self.assertEqual(hamming_distance_frames(left, right), 1.0)

    def test_run_stage1_returns_grouped_result_without_writing_files(self) -> None:
        paths = [Path("a.gif"), Path("b.gif"), Path("c.gif")]
        fake_hashes = {
            Path("a.gif"): np.array([[1, 0]], dtype=np.uint8),
            Path("b.gif"): np.array([[1, 0]], dtype=np.uint8),
            Path("c.gif"): np.array([[0, 1]], dtype=np.uint8),
        }

        with mock.patch(
            "gif_similarity_finder.stage1.compute_phash",
            side_effect=lambda path, n_frames=6: fake_hashes.get(path),
        ):
            result = run_stage1(paths, hash_threshold=0)

        self.assertEqual(result.groups[0], ["a.gif", "b.gif"])
        self.assertEqual(result.groups[-1], ["c.gif"])
        self.assertEqual(result.match_count, 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m unittest tests.test_stage1 -v`

Expected: `ModuleNotFoundError: No module named 'gif_similarity_finder.stage1'`

- [ ] **Step 3: Implement Stage 1 with a typed return value**

```python
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m unittest tests.test_stage1 -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add gif_similarity_finder/stage1.py tests/test_stage1.py
git commit -m "refactor: extract stage1 computation"
```

### Task 4: Extract Stage 2 computation and keep cache/index writes out of the stage

**Files:**
- Create: `gif_similarity_finder/stage2.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing Stage 2 contract test**

```python
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from gif_similarity_finder.stage2 import run_stage2


class Stage2ContractTest(unittest.TestCase):
    def test_run_stage2_returns_embeddings_and_labels(self) -> None:
        embeddings = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
        labels = np.array([0, -1], dtype=np.int64)

        with mock.patch("gif_similarity_finder.stage2.load_clip_model", return_value=("model", "pre", "cpu")), mock.patch(
            "gif_similarity_finder.stage2.extract_all_embeddings",
            return_value=([Path("a.gif"), Path("b.gif")], embeddings),
        ), mock.patch("gif_similarity_finder.stage2.cluster_hdbscan", return_value=labels):
            result = run_stage2(
                gif_paths=[Path("a.gif"), Path("b.gif")],
                n_frames=8,
                batch_size=32,
                min_cluster_size=3,
                device="auto",
                cache_data=None,
            )

        self.assertEqual(result.groups[0], ["a.gif"])
        self.assertEqual(result.groups[-1], ["b.gif"])
        self.assertEqual(result.embeddings.shape, (2, 2))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m unittest tests.test_pipeline.Stage2ContractTest -v`

Expected: `ModuleNotFoundError: No module named 'gif_similarity_finder.stage2'`

- [ ] **Step 3: Implement Stage 2 without file writes**

```python
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m unittest tests.test_pipeline.Stage2ContractTest -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add gif_similarity_finder/stage2.py gif_similarity_finder/types.py tests/test_pipeline.py
git commit -m "refactor: extract stage2 computation"
```

### Task 5: Create the artifacts layer for JSON, cache, index, and HTML outputs

**Files:**
- Create: `gif_similarity_finder/artifacts.py`
- Test: `tests/test_artifacts.py`

- [ ] **Step 1: Write the failing artifact tests**

```python
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from gif_similarity_finder.artifacts import (
    load_embedding_cache,
    save_embedding_cache,
    save_group_json,
    save_html_report,
)
from gif_similarity_finder.types import EmbeddingCacheData


class ArtifactsTest(unittest.TestCase):
    def test_save_group_json_writes_string_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            target = save_group_json(output_dir / "groups.json", {0: ["a.gif"], -1: ["b.gif"]})

            payload = json.loads(target.read_text(encoding="utf-8"))

        self.assertEqual(payload, {"0": ["a.gif"], "-1": ["b.gif"]})

    def test_cache_round_trip_preserves_paths_and_embeddings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_path = Path(tmp_dir) / "clip_embeddings_cache.npz"
            data = EmbeddingCacheData(paths=[Path("a.gif")], embeddings=np.array([[1.0, 0.0]], dtype=np.float32))

            save_embedding_cache(cache_path, data)
            restored = load_embedding_cache(cache_path)

        self.assertEqual(restored.paths, [Path("a.gif")])
        self.assertEqual(restored.embeddings.shape, (1, 2))

    def test_save_html_report_creates_report_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            report_path = save_html_report(output_dir, {0: ["a.gif"]}, "stage1_same_source")

        self.assertTrue(report_path.exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m unittest tests.test_artifacts -v`

Expected: `ModuleNotFoundError: No module named 'gif_similarity_finder.artifacts'`

- [ ] **Step 3: Implement the artifact helpers**

```python
import json
import logging
import time
from pathlib import Path

import numpy as np

from .types import EmbeddingCacheData


log = logging.getLogger(__name__)


def save_group_json(path: Path, groups: dict[int, list[str]]) -> Path:
    path.write_text(json.dumps({str(key): value for key, value in groups.items()}, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def save_embedding_cache(path: Path, cache_data: EmbeddingCacheData) -> Path:
    np.savez(path, paths=np.array([str(item) for item in cache_data.paths]), embeddings=cache_data.embeddings)
    return path


def load_embedding_cache(path: Path) -> EmbeddingCacheData | None:
    if not path.exists():
        return None
    payload = np.load(path, allow_pickle=True)
    return EmbeddingCacheData(
        paths=[Path(str(item)) for item in payload["paths"]],
        embeddings=payload["embeddings"],
    )


def save_html_report(output_dir: Path, groups: dict[int, list[str]], stage: str) -> Path:
    html_path = output_dir / f"report_{stage}.html"
    lines = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        f"<title>GIF Similarity Report – {stage}</title>",
        "</head><body>",
        f"<h1>GIF Similarity Report — {stage}</h1>",
        f"<p>Total groups: {len(groups)} | Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}</p>",
    ]
    for group_id, paths in sorted(groups.items(), key=lambda item: -len(item[1])):
        label = "Noise/Ungrouped" if str(group_id) == "-1" else f"Group {group_id}"
        lines.append(f"<h2>{label}</h2>")
        for path in paths[:40]:
            name = Path(path).name
            lines.append(f"<div>{name}</div>")
    lines.append("</body></html>")
    html_path.write_text("\n".join(lines), encoding="utf-8")
    return html_path
```

- [ ] **Step 4: Extend the artifact layer with index and visualization helpers**

```python
def save_hnsw_index(path: Path, embeddings: np.ndarray) -> Path:
    import hnswlib

    count, dimensions = embeddings.shape
    index = hnswlib.Index(space="cosine", dim=dimensions)
    index.init_index(max_elements=count, ef_construction=200, M=16)
    index.add_items(embeddings, list(range(count)))
    index.set_ef(50)
    index.save_index(str(path))
    return path


def save_umap_visualization(output_dir: Path, embeddings: np.ndarray, labels: np.ndarray) -> Path | None:
    try:
        import matplotlib.cm as cm
        import matplotlib.pyplot as plt
        import umap
    except ImportError:
        return None

    reducer = umap.UMAP(n_components=2, random_state=42, n_neighbors=15, min_dist=0.1)
    xy = reducer.fit_transform(embeddings)
    unique_labels = sorted(set(labels))
    colors = cm.tab20(np.linspace(0, 1, max(len(unique_labels), 1)))
    path = output_dir / "umap_clusters.png"
    fig, axis = plt.subplots(figsize=(14, 10))
    for index, label in enumerate(unique_labels):
        mask = labels == label
        axis.scatter(xy[mask, 0], xy[mask, 1], c=[colors[index % len(colors)]], s=8)
    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m unittest tests.test_artifacts -v`

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add gif_similarity_finder/artifacts.py tests/test_artifacts.py
git commit -m "refactor: add artifact persistence layer"
```

### Task 6: Create the pipeline module and move orchestration out of the script

**Files:**
- Create: `gif_similarity_finder/pipeline.py`
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: Expand the pipeline test to fail on missing orchestration**

```python
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from gif_similarity_finder.pipeline import run_pipeline
from gif_similarity_finder.types import PipelineConfig, Stage1Result, Stage2Result


class PipelineOrchestrationTest(unittest.TestCase):
    def test_run_pipeline_calls_stage_modules_and_artifact_writers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = PipelineConfig(
                input_dir=Path(tmp_dir),
                output_dir=Path(tmp_dir) / "output",
                frames=8,
                hash_threshold=10,
                min_cluster_size=3,
                batch_size=32,
                device="auto",
                skip_stage1=False,
                skip_stage2=False,
            )

            with mock.patch("gif_similarity_finder.pipeline.collect_gifs", return_value=[Path("a.gif")]), mock.patch(
                "gif_similarity_finder.pipeline.run_stage1",
                return_value=Stage1Result(groups={0: ["a.gif"]}, hashed_paths=[Path("a.gif")], match_count=0),
            ) as stage1_mock, mock.patch(
                "gif_similarity_finder.pipeline.run_stage2",
                return_value=Stage2Result(
                    groups={0: ["a.gif"]},
                    valid_paths=[Path("a.gif")],
                    embeddings=np.array([[1.0, 0.0]], dtype=np.float32),
                    labels=np.array([0], dtype=np.int64),
                ),
            ) as stage2_mock, mock.patch("gif_similarity_finder.pipeline.save_group_json") as save_group_json_mock:
                run_pipeline(config)

        stage1_mock.assert_called_once()
        stage2_mock.assert_called_once()
        self.assertGreaterEqual(save_group_json_mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m unittest tests.test_pipeline.PipelineOrchestrationTest -v`

Expected: `ModuleNotFoundError: No module named 'gif_similarity_finder.pipeline'`

- [ ] **Step 3: Implement the pipeline**

```python
import logging
from pathlib import Path

from .artifacts import (
    load_embedding_cache,
    save_embedding_cache,
    save_group_json,
    save_hnsw_index,
    save_html_report,
    save_umap_visualization,
)
from .io import collect_gifs
from .stage1 import run_stage1
from .stage2 import run_stage2
from .types import EmbeddingCacheData, PipelineConfig


log = logging.getLogger(__name__)


def run_pipeline(config: PipelineConfig) -> None:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    gif_paths = collect_gifs(config.input_dir)
    if not gif_paths:
        raise SystemExit("No GIF files found. Check --input path.")

    if not config.skip_stage1:
        stage1_result = run_stage1(gif_paths, hash_threshold=config.hash_threshold)
        save_group_json(config.output_dir / "stage1_same_source_groups.json", stage1_result.groups)
        save_html_report(config.output_dir, stage1_result.groups, "stage1_same_source")
    else:
        log.info("Stage 1 skipped.")

    if not config.skip_stage2:
        cache_path = config.output_dir / "clip_embeddings_cache.npz"
        cache_data = load_embedding_cache(cache_path)
        stage2_result = run_stage2(
            gif_paths=gif_paths,
            n_frames=config.frames,
            batch_size=config.batch_size,
            min_cluster_size=config.min_cluster_size,
            device=config.device,
            cache_data=cache_data,
        )
        save_group_json(config.output_dir / "stage2_action_clusters.json", stage2_result.groups)
        save_html_report(config.output_dir, stage2_result.groups, "stage2_action_clusters")
        if stage2_result.valid_paths:
            save_embedding_cache(
                cache_path,
                EmbeddingCacheData(paths=stage2_result.valid_paths, embeddings=stage2_result.embeddings),
            )
            save_hnsw_index(config.output_dir / "hnsw.index", stage2_result.embeddings)
            save_umap_visualization(config.output_dir, stage2_result.embeddings, stage2_result.labels)
    else:
        log.info("Stage 2 skipped.")
```

- [ ] **Step 4: Run the pipeline test to verify it passes**

Run: `python -m unittest tests.test_pipeline.PipelineOrchestrationTest -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add gif_similarity_finder/pipeline.py tests/test_pipeline.py
git commit -m "refactor: add pipeline orchestration"
```

### Task 7: Replace the monolithic script with a thin CLI and update docs

**Files:**
- Modify: `gif_similarity.py`
- Modify: `README.md`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing CLI test**

```python
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

import gif_similarity


class CliTest(unittest.TestCase):
    def test_main_builds_pipeline_config_and_calls_pipeline(self) -> None:
        args = Namespace(
            input="input",
            output="output",
            frames=8,
            hash_thresh=10,
            min_cluster=3,
            batch_size=32,
            device="auto",
            skip_stage1=False,
            skip_stage2=True,
        )

        with mock.patch("gif_similarity.parse_args", return_value=args), mock.patch(
            "gif_similarity.run_pipeline"
        ) as run_pipeline_mock:
            gif_similarity.main()

        config = run_pipeline_mock.call_args.args[0]
        self.assertEqual(config.input_dir, Path("input"))
        self.assertTrue(config.skip_stage2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m unittest tests.test_pipeline.CliTest -v`

Expected: `AttributeError` because `parse_args` does not exist yet

- [ ] **Step 3: Rewrite `gif_similarity.py` as a thin CLI**

```python
import argparse
import logging
import sys
import time
from pathlib import Path

from gif_similarity_finder.pipeline import run_pipeline
from gif_similarity_finder.types import PipelineConfig


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

log = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GIF Similarity Finder — same-source + action/scene clustering")
    parser.add_argument("--input", required=True, help="Folder containing GIF files")
    parser.add_argument("--output", default="./output", help="Output directory")
    parser.add_argument("--frames", type=int, default=8, help="Frames to sample per GIF for CLIP")
    parser.add_argument("--hash_thresh", type=int, default=10, help="Hamming distance threshold for same-source detection")
    parser.add_argument("--min_cluster", type=int, default=3, help="Minimum cluster size for HDBSCAN")
    parser.add_argument("--batch_size", type=int, default=32, help="CLIP batch size")
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda", "mps"], help="Compute device")
    parser.add_argument("--skip_stage1", action="store_true", help="Skip same-source detection")
    parser.add_argument("--skip_stage2", action="store_true", help="Skip CLIP clustering")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = PipelineConfig(
        input_dir=Path(args.input),
        output_dir=Path(args.output),
        frames=args.frames,
        hash_threshold=args.hash_thresh,
        min_cluster_size=args.min_cluster,
        batch_size=args.batch_size,
        device=args.device,
        skip_stage1=args.skip_stage1,
        skip_stage2=args.skip_stage2,
    )
    started_at = time.time()
    run_pipeline(config)
    elapsed = time.time() - started_at
    log.info("Done in %.1fs — results in '%s'", elapsed, config.output_dir)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Update the README architecture section**

````markdown
## Technical Architecture

```text
gif_similarity.py
    -> CLI argument parsing
    -> PipelineConfig construction
    -> run_pipeline(...)

gif_similarity_finder/
    io.py          # GIF collection and frame sampling
    stage1.py      # pHash-based same-source grouping
    stage2.py      # CLIP embedding extraction and clustering
    artifacts.py   # cache, json, report, index, visualization outputs
    pipeline.py    # orchestration
    types.py       # shared result models
```
````

- [ ] **Step 5: Run the CLI-focused test to verify it passes**

Run: `python -m unittest tests.test_pipeline.CliTest -v`

Expected: `OK`

- [ ] **Step 6: Run the full refactor regression suite**

Run: `python -m unittest tests.test_io tests.test_stage1 tests.test_artifacts tests.test_pipeline -v`

Expected: all tests pass with `OK`

- [ ] **Step 7: Commit**

```bash
git add gif_similarity.py README.md tests/test_pipeline.py
git commit -m "refactor: thin cli and document package architecture"
```

## Spec Coverage Check

- Thin CLI entrypoint — covered by Task 7.
- Pipeline orchestration module — covered by Task 6.
- Stage 1 computation isolation — covered by Task 3.
- Stage 2 computation isolation — covered by Task 4.
- Artifact ownership of JSON/cache/index/report/visualization writes — covered by Task 5 and Task 6.
- Shared result models and config contracts — covered by Task 1.
- Small, focused tests around boundaries — covered across Tasks 1 through 7.
- README architecture update — covered by Task 7.

## Placeholder Scan

Reviewed the plan for placeholder language and vague implementation instructions. None remain.

## Type Consistency Check

- `PipelineConfig`, `Stage1Result`, `EmbeddingCacheData`, and `Stage2Result` are defined once in `gif_similarity_finder/types.py` and reused consistently.
- The stage entrypoints are consistently named `run_stage1` and `run_stage2`.
- The orchestrator entrypoint is consistently named `run_pipeline`.
