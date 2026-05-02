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


def resolve_output_dir(output_arg: str | None) -> Path:
    if output_arg:
        return Path(output_arg)
    return Path(__file__).resolve().parent / "output"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GIF Similarity Finder — same-source + action/scene clustering")
    parser.add_argument("--input", required=True, help="Folder containing GIF files")
    parser.add_argument("--output", default=None, help="Output directory")
    parser.add_argument("--frames", type=int, default=8, help="Frames to sample per GIF for CLIP")
    parser.add_argument(
        "--hash_thresh",
        type=int,
        default=10,
        help="Hamming distance threshold for same-source detection",
    )
    parser.add_argument("--min_cluster", type=int, default=3, help="Minimum cluster size for HDBSCAN")
    parser.add_argument("--batch_size", type=int, default=32, help="CLIP batch size")
    parser.add_argument(
        "--device",
        default="auto",
        choices=["auto", "cpu", "cuda", "mps"],
        help="Compute device",
    )
    parser.add_argument("--skip_stage1", action="store_true", help="Skip same-source detection")
    parser.add_argument("--skip_stage2", action="store_true", help="Skip CLIP clustering")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = PipelineConfig(
        input_dir=Path(args.input),
        output_dir=resolve_output_dir(args.output),
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
