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
