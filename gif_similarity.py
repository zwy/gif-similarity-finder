"""
GIF Similarity Finder
======================
Two-stage pipeline:
  Stage 1 - Perceptual Hash  → Group GIFs from the same source video
  Stage 2 - CLIP Embeddings  → Group GIFs with similar actions/scenes

Usage:
    python gif_similarity.py --input /path/to/gif/folder [options]

Options:
    --input         Path to folder containing GIF files (required)
    --output        Output directory for results (default: ./output)
    --frames        Number of frames to sample per GIF for CLIP (default: 8)
    --hash_thresh   Hamming distance threshold for same-source grouping (default: 10)
    --min_cluster   Minimum cluster size for HDBSCAN (default: 3)
    --batch_size    Batch size for CLIP inference (default: 32)
    --device        Device for CLIP: 'cpu', 'cuda', 'mps' (default: auto-detect)
    --skip_stage1   Skip perceptual hash stage
    --skip_stage2   Skip CLIP semantic clustering stage
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageSequence
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────

def collect_gifs(folder: str) -> list[Path]:
    folder = Path(folder)
    gifs = sorted(folder.rglob("*.gif")) + sorted(folder.rglob("*.GIF"))
    # deduplicate (rglob may return duplicates on case-insensitive FS)
    seen = set()
    result = []
    for p in gifs:
        key = str(p.resolve())
        if key not in seen:
            seen.add(key)
            result.append(p)
    log.info(f"Found {len(result)} GIF files in '{folder}'")
    return result


def sample_frames(gif_path: Path, n_frames: int = 8) -> list[Image.Image]:
    """Uniformly sample up to n_frames frames from a GIF."""
    try:
        gif = Image.open(gif_path)
        frames = []
        for frame in ImageSequence.Iterator(gif):
            frames.append(frame.copy().convert("RGB"))
        if not frames:
            return []
        # Uniform sampling
        indices = np.linspace(0, len(frames) - 1, min(n_frames, len(frames)), dtype=int)
        return [frames[i] for i in indices]
    except Exception as e:
        log.warning(f"Cannot read '{gif_path.name}': {e}")
        return []


def save_html_report(output_dir: Path, groups: dict, stage: str, gif_folder: Path):
    """Generate a simple HTML report to visually inspect groups."""
    html_path = output_dir / f"report_{stage}.html"
    lines = [
        "<!DOCTYPE html><html><head>",
        "<meta charset='utf-8'>",
        f"<title>GIF Similarity Report – {stage}</title>",
        "<style>",
        "body{font-family:sans-serif;background:#1a1a1a;color:#e0e0e0;margin:20px}",
        "h1{color:#4f98a3} h2{color:#aaa;border-bottom:1px solid #333;padding-bottom:4px}",
        ".group{margin-bottom:40px}",
        ".gif-grid{display:flex;flex-wrap:wrap;gap:8px}",
        ".gif-item{text-align:center;font-size:11px;color:#888;max-width:160px}",
        "img{width:160px;height:120px;object-fit:cover;border-radius:4px;border:1px solid #333}",
        "</style></head><body>",
        f"<h1>GIF Similarity Report — {stage}</h1>",
        f"<p>Total groups: {len(groups)} | Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}</p>",
    ]
    for group_id, paths in sorted(groups.items(), key=lambda x: -len(x[1])):
        label = "Noise/Ungrouped" if str(group_id) == "-1" else f"Group {group_id}"
        lines += [
            f"<div class='group'>",
            f"<h2>{label} — {len(paths)} GIFs</h2>",
            "<div class='gif-grid'>",
        ]
        for p in paths[:40]:  # cap at 40 per group to keep HTML sane
            rel = os.path.relpath(p, output_dir)
            abs_path = Path(p)
            lines.append(
                f"<div class='gif-item'>"
                f"<img src='{abs_path.as_posix()}' alt='' loading='lazy'>"
                f"<div>{abs_path.name}</div>"
                f"</div>"
            )
        if len(paths) > 40:
            lines.append(f"<p>... and {len(paths)-40} more</p>")
        lines.append("</div></div>")
    lines.append("</body></html>")
    html_path.write_text("\n".join(lines), encoding="utf-8")
    log.info(f"HTML report saved: {html_path}")
    return html_path


# ─────────────────────────────────────────────
# Stage 1: Perceptual Hash – Same Source Video
# ─────────────────────────────────────────────

def compute_phash(gif_path: Path, n_frames: int = 6) -> np.ndarray | None:
    """
    Sample frames from GIF, compute pHash for each, return as int64 array.
    We'll compare using average bit-difference across sampled frames.
    """
    try:
        import imagehash
        frames = sample_frames(gif_path, n_frames)
        if not frames:
            return None
        hashes = [imagehash.phash(f) for f in frames]
        # Store as flat array of hash ints
        return np.array([h.hash.flatten().astype(np.uint8) for h in hashes])
    except Exception as e:
        log.warning(f"pHash failed for '{gif_path.name}': {e}")
        return None


def hamming_distance_frames(h1: np.ndarray, h2: np.ndarray) -> float:
    """
    Average hamming distance between two sets of frame hashes.
    Each is shape (n_frames, 64) uint8 (bits).
    """
    # Compare frame by frame using shortest length
    n = min(len(h1), len(h2))
    dists = [np.sum(h1[i] != h2[i]) for i in range(n)]
    return float(np.mean(dists))


def stage1_same_source(gif_paths: list[Path], hash_thresh: int, output_dir: Path) -> dict:
    """
    Group GIFs likely cut from the same source video using perceptual hash.
    Returns {group_id: [path_str, ...]}
    """
    log.info("=" * 60)
    log.info("STAGE 1: Perceptual Hash — Same-Source Grouping")
    log.info("=" * 60)

    hashes = {}
    for p in tqdm(gif_paths, desc="Computing pHash"):
        h = compute_phash(p)
        if h is not None:
            hashes[p] = h

    valid_paths = list(hashes.keys())
    n = len(valid_paths)
    log.info(f"Successfully hashed {n}/{len(gif_paths)} GIFs")

    # Union-Find for grouping
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    log.info(f"Comparing pairs (threshold={hash_thresh})…")
    match_count = 0
    for i in tqdm(range(n), desc="Grouping by pHash"):
        for j in range(i + 1, n):
            dist = hamming_distance_frames(hashes[valid_paths[i]], hashes[valid_paths[j]])
            if dist <= hash_thresh:
                union(i, j)
                match_count += 1

    # Build groups
    from collections import defaultdict
    groups: dict[int, list[str]] = defaultdict(list)
    for i, p in enumerate(valid_paths):
        groups[find(i)].append(str(p))

    # Remap group IDs to 0-based integers, only keep groups with >1 member
    multi_groups = {gid: members for gid, members in groups.items() if len(members) > 1}
    singleton_group = [str(p) for p in valid_paths if groups[find(valid_paths.index(p))] == [str(p)]]

    # Re-index
    result = {}
    for new_id, (_, members) in enumerate(
        sorted(multi_groups.items(), key=lambda x: -len(x[1]))
    ):
        result[new_id] = members
    result[-1] = [str(p) for p in valid_paths
                  if not any(str(p) in v for v in multi_groups.values())]

    multi_count = len(result) - 1  # exclude -1
    total_grouped = sum(len(v) for k, v in result.items() if k != -1)
    log.info(f"Stage 1 complete: {multi_count} same-source groups, {total_grouped} GIFs grouped, "
             f"{len(result.get(-1, []))} singletons")

    # Save JSON
    out_json = output_dir / "stage1_same_source_groups.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in result.items()}, f, indent=2, ensure_ascii=False)
    log.info(f"Stage 1 JSON saved: {out_json}")

    return result


# ─────────────────────────────────────────────
# Stage 2: CLIP Embeddings – Action/Scene Clustering
# ─────────────────────────────────────────────

def load_clip_model(device: str):
    """Load CLIP ViT-B/32 model."""
    import torch
    import clip

    if device == "auto":
        if torch.backends.mps.is_available():
            device = "mps"
        elif torch.cuda.is_available():
            device = "cuda"
        else:
            device = "cpu"
    log.info(f"Loading CLIP ViT-B/32 on device: {device}")
    model, preprocess = clip.load("ViT-B/32", device=device)
    model.eval()
    return model, preprocess, device


def extract_gif_embedding(
    gif_path: Path,
    model,
    preprocess,
    device: str,
    n_frames: int = 8,
) -> np.ndarray | None:
    """Extract mean-pooled CLIP embedding for a GIF."""
    import torch

    frames = sample_frames(gif_path, n_frames)
    if not frames:
        return None
    try:
        tensors = torch.stack([preprocess(f) for f in frames]).to(device)
        with torch.no_grad():
            embeddings = model.encode_image(tensors)  # (n_frames, 512)
            embedding = embeddings.mean(dim=0)         # mean pooling
            embedding = embedding / embedding.norm()   # L2 normalize
        return embedding.cpu().float().numpy()
    except Exception as e:
        log.warning(f"CLIP failed for '{gif_path.name}': {e}")
        return None


def extract_all_embeddings(
    gif_paths: list[Path],
    model,
    preprocess,
    device: str,
    n_frames: int,
    batch_size: int,
    cache_path: Path,
) -> tuple[list[Path], np.ndarray]:
    """Extract embeddings for all GIFs, with disk cache."""
    # Check cache
    if cache_path.exists():
        log.info(f"Loading cached embeddings from {cache_path}")
        data = np.load(cache_path, allow_pickle=True)
        cached_paths = [Path(str(p)) for p in data["paths"]]
        cached_embs = data["embeddings"]
        cached_set = {str(p) for p in cached_paths}
        remaining = [p for p in gif_paths if str(p) not in cached_set]
        if not remaining:
            return cached_paths, cached_embs
        log.info(f"Cache has {len(cached_paths)} entries, processing {len(remaining)} new GIFs")
    else:
        cached_paths, cached_embs_list = [], []
        remaining = gif_paths

    valid_paths = list(cached_paths)
    emb_list = list(cached_embs) if cache_path.exists() else []

    for i in tqdm(range(0, len(remaining), batch_size), desc="Extracting CLIP embeddings"):
        batch = remaining[i: i + batch_size]
        for p in batch:
            emb = extract_gif_embedding(p, model, preprocess, device, n_frames)
            if emb is not None:
                valid_paths.append(p)
                emb_list.append(emb)

    embeddings = np.stack(emb_list).astype(np.float32)

    # Save cache
    np.savez(cache_path, paths=np.array([str(p) for p in valid_paths]), embeddings=embeddings)
    log.info(f"Embeddings cached to {cache_path} ({len(valid_paths)} GIFs)")

    return valid_paths, embeddings


def build_faiss_index(embeddings: np.ndarray):
    """Build FAISS IVF index for fast nearest-neighbor search."""
    import faiss

    d = embeddings.shape[1]  # 512 for ViT-B/32
    n = embeddings.shape[0]

    if n < 1000:
        # Small dataset: use flat index
        index = faiss.IndexFlatIP(d)
        index.add(embeddings)
        log.info(f"FAISS Flat index built ({n} vectors, dim={d})")
    else:
        # Larger dataset: IVF index
        nlist = min(int(np.sqrt(n)), 256)
        quantizer = faiss.IndexFlatIP(d)
        index = faiss.IndexIVFFlat(quantizer, d, nlist, faiss.METRIC_INNER_PRODUCT)
        index.train(embeddings)
        index.add(embeddings)
        index.nprobe = min(nlist, 32)
        log.info(f"FAISS IVF index built ({n} vectors, nlist={nlist}, dim={d})")

    return index


def cluster_hdbscan(embeddings: np.ndarray, min_cluster_size: int) -> np.ndarray:
    """Cluster embeddings with HDBSCAN."""
    from sklearn.cluster import HDBSCAN

    log.info(f"Running HDBSCAN (min_cluster_size={min_cluster_size}) on {len(embeddings)} vectors…")
    clusterer = HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=1,
        metric="euclidean",
        cluster_selection_method="eom",
    )
    labels = clusterer.fit_predict(embeddings)
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = int(np.sum(labels == -1))
    log.info(f"HDBSCAN done: {n_clusters} clusters, {n_noise} noise points")
    return labels


def stage2_action_clustering(
    gif_paths: list[Path],
    output_dir: Path,
    n_frames: int,
    batch_size: int,
    min_cluster_size: int,
    device: str,
) -> dict:
    """
    Cluster GIFs by action/scene similarity using CLIP embeddings + HDBSCAN.
    Returns {cluster_id: [path_str, ...]}
    """
    log.info("=" * 60)
    log.info("STAGE 2: CLIP Semantic Clustering — Action/Scene Grouping")
    log.info("=" * 60)

    model, preprocess, device = load_clip_model(device)

    cache_path = output_dir / "clip_embeddings_cache.npz"
    valid_paths, embeddings = extract_all_embeddings(
        gif_paths, model, preprocess, device, n_frames, batch_size, cache_path
    )

    if len(valid_paths) == 0:
        log.error("No valid embeddings extracted. Exiting stage 2.")
        return {}

    # Faiss index (optional, useful for nearest-neighbor queries later)
    faiss_index = build_faiss_index(embeddings)
    faiss_index_path = output_dir / "faiss.index"
    import faiss
    faiss.write_index(faiss_index, str(faiss_index_path))
    log.info(f"FAISS index saved: {faiss_index_path}")

    # Cluster
    labels = cluster_hdbscan(embeddings, min_cluster_size)

    # Build result dict
    from collections import defaultdict
    groups: dict[int, list[str]] = defaultdict(list)
    for path, label in zip(valid_paths, labels):
        groups[int(label)].append(str(path))

    # Sort by size descending
    result = dict(sorted(groups.items(), key=lambda x: -len(x[1])))

    # Save cluster label mapping
    label_map = {str(p): int(l) for p, l in zip(valid_paths, labels)}
    out_json = output_dir / "stage2_action_clusters.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in result.items()}, f, indent=2, ensure_ascii=False)
    log.info(f"Stage 2 JSON saved: {out_json}")

    n_clusters = len(result) - (1 if -1 in result else 0)
    total_grouped = sum(len(v) for k, v in result.items() if k != -1)
    log.info(f"Stage 2 complete: {n_clusters} action clusters, {total_grouped} GIFs grouped")

    return result


# ─────────────────────────────────────────────
# Visualisation: UMAP 2D scatter
# ─────────────────────────────────────────────

def visualise_clusters(output_dir: Path):
    """Generate UMAP 2D scatter plot of clusters (optional, runs if umap-learn installed)."""
    try:
        import umap
        import matplotlib.pyplot as plt
        import matplotlib.cm as cm

        cache_path = output_dir / "clip_embeddings_cache.npz"
        cluster_json = output_dir / "stage2_action_clusters.json"
        if not cache_path.exists() or not cluster_json.exists():
            return

        data = np.load(cache_path, allow_pickle=True)
        paths = list(data["paths"])
        embeddings = data["embeddings"]

        with open(cluster_json) as f:
            clusters = json.load(f)
        path_to_label = {}
        for label, ps in clusters.items():
            for p in ps:
                path_to_label[p] = int(label)

        labels = np.array([path_to_label.get(p, -1) for p in paths])

        log.info("Running UMAP dimensionality reduction…")
        reducer = umap.UMAP(n_components=2, random_state=42, n_neighbors=15, min_dist=0.1)
        xy = reducer.fit_transform(embeddings)

        unique_labels = sorted(set(labels))
        colors = cm.tab20(np.linspace(0, 1, max(len(unique_labels), 1)))
        color_map = {l: colors[i % len(colors)] for i, l in enumerate(unique_labels)}

        fig, ax = plt.subplots(figsize=(14, 10))
        fig.patch.set_facecolor("#1a1a1a")
        ax.set_facecolor("#1a1a1a")
        for l in unique_labels:
            mask = labels == l
            c = color_map[l]
            lab = "Noise" if l == -1 else f"Cluster {l}"
            alpha = 0.3 if l == -1 else 0.7
            size = 4 if l == -1 else 8
            ax.scatter(xy[mask, 0], xy[mask, 1], c=[c], label=lab, alpha=alpha, s=size)

        ax.set_title("GIF Action Clusters (UMAP)", color="white", fontsize=14)
        ax.tick_params(colors="gray")
        for spine in ax.spines.values():
            spine.set_edgecolor("#333")
        handles, lbls = ax.get_legend_handles_labels()
        if len(handles) <= 30:
            ax.legend(handles, lbls, fontsize=7, loc="best",
                      facecolor="#222", labelcolor="white", markerscale=2)

        out_png = output_dir / "umap_clusters.png"
        plt.tight_layout()
        plt.savefig(out_png, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close()
        log.info(f"UMAP plot saved: {out_png}")
    except ImportError:
        log.info("umap-learn or matplotlib not installed, skipping UMAP visualisation")
    except Exception as e:
        log.warning(f"UMAP visualisation failed: {e}")


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="GIF Similarity Finder — same-source + action/scene clustering"
    )
    parser.add_argument("--input", required=True, help="Folder containing GIF files")
    parser.add_argument("--output", default="./output", help="Output directory")
    parser.add_argument("--frames", type=int, default=8, help="Frames to sample per GIF for CLIP")
    parser.add_argument("--hash_thresh", type=int, default=10,
                        help="Hamming distance threshold for same-source detection")
    parser.add_argument("--min_cluster", type=int, default=3,
                        help="Minimum cluster size for HDBSCAN")
    parser.add_argument("--batch_size", type=int, default=32, help="CLIP batch size")
    parser.add_argument("--device", default="auto",
                        choices=["auto", "cpu", "cuda", "mps"], help="Compute device")
    parser.add_argument("--skip_stage1", action="store_true", help="Skip same-source detection")
    parser.add_argument("--skip_stage2", action="store_true", help="Skip CLIP clustering")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    gif_paths = collect_gifs(args.input)
    if not gif_paths:
        log.error("No GIF files found. Check --input path.")
        sys.exit(1)

    t0 = time.time()

    # Stage 1
    if not args.skip_stage1:
        s1_groups = stage1_same_source(gif_paths, args.hash_thresh, output_dir)
        save_html_report(output_dir, s1_groups, "stage1_same_source", Path(args.input))
    else:
        log.info("Stage 1 skipped.")

    # Stage 2
    if not args.skip_stage2:
        s2_groups = stage2_action_clustering(
            gif_paths, output_dir, args.frames, args.batch_size,
            args.min_cluster, args.device,
        )
        save_html_report(output_dir, s2_groups, "stage2_action_clusters", Path(args.input))
        visualise_clusters(output_dir)
    else:
        log.info("Stage 2 skipped.")

    elapsed = time.time() - t0
    log.info(f"\n✅ Done in {elapsed:.1f}s — results in '{output_dir}'")
    log.info("Output files:")
    for f in sorted(output_dir.iterdir()):
        log.info(f"  {f.name}")


if __name__ == "__main__":
    main()
