import json
from pathlib import Path
from typing import List

from PIL import Image, ImageSequence


def save_preview_image(gif_path: Path, preview_path: Path, size=(240, 240)) -> Path | None:
    """Create a lightweight preview (webp) from a GIF.

    Returns the preview_path on success, or None on failure.
    """
    try:
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(gif_path) as img:
            # Select the first non-empty frame
            frame = None
            for i, f in enumerate(ImageSequence.Iterator(img)):
                frame = f.copy()
                break
            if frame is None:
                return None
            frame = frame.convert("RGBA")
            frame.thumbnail(size)
            # Save as webp
            preview_path.with_suffix(".webp")
            preview_path = preview_path.with_suffix(".webp")
            frame.save(preview_path, format="WEBP", quality=80, method=6)
        return preview_path
    except Exception:
        return None


def save_dashboard_manifest(path: Path, manifest: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "window.__GIF_DASHBOARD_MANIFEST__ = " + json.dumps(manifest, ensure_ascii=False) + ";\n"
    path.write_text(content, encoding="utf-8")
    return path


def save_dashboard_stage_shard(path: Path, stage_key: str, items: List[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    shard_key = f"{stage_key}:{path.name}"
    content = (
        "window.__GIF_DASHBOARD_STAGE_SHARDS__ = window.__GIF_DASHBOARD_STAGE_SHARDS__ || {};\n"
        + f"window.__GIF_DASHBOARD_STAGE_SHARDS__['{shard_key}'] = "
        + json.dumps(items, ensure_ascii=False)
        + ";\n"
    )
    # Append if file exists to avoid clobbering other shards
    with path.open("a", encoding="utf-8") as fh:
        fh.write(content)
    return path
