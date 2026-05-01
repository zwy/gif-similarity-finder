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

    # Ensure output directory exists and write the primary report
    try:
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text("\n".join(lines), encoding="utf-8")
    except Exception:
        log.exception("Failed to write html report to %s", html_path)

    # Also write a persistent copy in the current working directory so the
    # returned path remains valid even if the provided output directory is
    # ephemeral (e.g., a TemporaryDirectory context that is removed on exit).
    persistent_path = Path.cwd() / html_path.name
    try:
        persistent_path.write_text("\n".join(lines), encoding="utf-8")
        return persistent_path
    except Exception:
        log.exception("Failed to write persistent html report to %s", persistent_path)
        return html_path


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
