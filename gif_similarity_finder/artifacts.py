import json
import time
from pathlib import Path

import numpy as np

from .types import EmbeddingCacheData
from .report_data import build_report_dataset
from .report_template import render_report_html


def save_group_json(path: Path, groups: dict[int, list[str]]) -> Path:
    # Ensure parent directory exists before writing
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({str(key): value for key, value in groups.items()}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def save_embedding_cache(path: Path, cache_data: EmbeddingCacheData) -> Path:
    # Ensure parent directory exists before writing
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, paths=np.array([str(item) for item in cache_data.paths]), embeddings=cache_data.embeddings)
    return path


def load_embedding_cache(path: Path) -> EmbeddingCacheData | None:
    if not path.exists():
        return None
    # Use a context manager to ensure the NpzFile is closed promptly
    with np.load(path, allow_pickle=True) as payload:
        paths = [Path(str(item)) for item in payload["paths"]]
        embeddings = payload["embeddings"].copy()
    return EmbeddingCacheData(paths=paths, embeddings=embeddings)


def save_html_report(output_dir: Path, groups: dict[int, list[str]], stage: str) -> Path:
    """Build a structured dataset and render the lightweight HTML shell.

    Uses build_report_dataset and render_report_html to produce the
    final HTML string, then writes it to report_{stage}.html inside
    output_dir. IO errors are allowed to propagate.
    """
    html_path = output_dir / f"report_{stage}.html"

    # Build the structured dataset and render the HTML shell
    dataset = build_report_dataset(groups, stage=stage)
    html = render_report_html(dataset)

    # Ensure output directory exists and write the primary report.
    output_dir.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html, encoding="utf-8")

    return html_path


def save_hnsw_index(path: Path, embeddings: np.ndarray) -> Path:
    import hnswlib

    # Ensure parent directory exists before saving the index file
    path.parent.mkdir(parents=True, exist_ok=True)

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
        # Optional dependency; if unavailable, be graceful and return None
        return None

    # Ensure output directory exists before creating the figure
    output_dir.mkdir(parents=True, exist_ok=True)

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
