import logging
from dataclasses import asdict, is_dataclass
from pathlib import Path

from .artifacts import (
    load_embedding_cache,
    save_embedding_cache,
    save_group_json,
    save_hnsw_index,
    save_umap_visualization,
)
from .dashboard_artifacts import save_dashboard_manifest, save_dashboard_stage_shard, save_preview_image
from .dashboard_data import build_dashboard_manifest, build_dashboard_stage, split_stage_items
from .io import collect_gifs
from .stage1 import run_stage1
from .stage2 import run_stage2
from .types import EmbeddingCacheData, PipelineConfig


log = logging.getLogger(__name__)
PREVIEW_SIZE = (240, 240)


def _serialize_dashboard_items(items: list[object]) -> list[dict]:
    payload: list[dict] = []
    for item in items:
        if isinstance(item, dict):
            payload.append(item)
        elif is_dataclass(item):
            payload.append(asdict(item))
        else:
            payload.append(vars(item))
    return payload


def _persist_dashboard_stage_artifacts(
    output_dir: Path,
    stage: object,
    saved_preview_targets: set[tuple[str, str]],
    preview_failures: list[dict],
) -> None:
    for item in stage.items:
        gif_path = Path(item.gif_path)
        preview_path = output_dir / item.preview_path
        dedupe_key = (str(gif_path), str(preview_path))
        if dedupe_key in saved_preview_targets:
            continue
        failure_reason = None
        if gif_path.exists():
            if save_preview_image(gif_path, preview_path) is None:
                failure_reason = "preview_generation_failed"
        else:
            failure_reason = "missing_source_gif"
        if failure_reason:
            preview_failures.append(
                {
                    "stage": stage.stage_key,
                    "item_id": item.id,
                    "gif_path": str(gif_path),
                    "preview_path": str(preview_path),
                    "reason": failure_reason,
                }
            )
        saved_preview_targets.add(dedupe_key)

    shards = split_stage_items(stage, shard_size=1000)
    for shard in shards:
        save_dashboard_stage_shard(
            output_dir / shard.file_name,
            stage.stage_key,
            _serialize_dashboard_items(shard.items),
        )


def run_pipeline(config: PipelineConfig) -> None:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    gif_paths = collect_gifs(config.input_dir)
    if not gif_paths:
        raise SystemExit("No GIF files found. Check --input path.")

    dashboard_stages = []
    saved_preview_targets: set[tuple[str, str]] = set()
    preview_failures: list[dict] = []
    if not config.skip_stage1:
        stage1_result = run_stage1(gif_paths, hash_threshold=config.hash_threshold)
        save_group_json(config.output_dir / "stage1_same_source_groups.json", stage1_result.groups)
        stage1_dashboard = build_dashboard_stage("stage1_same_source", stage1_result.groups, preview_dir_name="previews")
        dashboard_stages.append(stage1_dashboard)
        _persist_dashboard_stage_artifacts(
            config.output_dir,
            stage1_dashboard,
            saved_preview_targets,
            preview_failures,
        )
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
            grayscale=config.grayscale,
        )
        save_group_json(config.output_dir / "stage2_action_clusters.json", stage2_result.groups)
        stage2_dashboard = build_dashboard_stage("stage2_action_clusters", stage2_result.groups, preview_dir_name="previews")
        dashboard_stages.append(stage2_dashboard)
        _persist_dashboard_stage_artifacts(
            config.output_dir,
            stage2_dashboard,
            saved_preview_targets,
            preview_failures,
        )
        if stage2_result.valid_paths:
            save_embedding_cache(
                cache_path,
                EmbeddingCacheData(paths=stage2_result.valid_paths, embeddings=stage2_result.embeddings),
            )
            save_hnsw_index(config.output_dir / "hnsw.index", stage2_result.embeddings)
            save_umap_visualization(config.output_dir, stage2_result.embeddings, stage2_result.labels)
    else:
        log.info("Stage 2 skipped.")

    manifest_kwargs = {
        "preview_config": {
            "dir": "previews",
            "format": "webp",
            "kind": "first_frame",
            "size": {"width": PREVIEW_SIZE[0], "height": PREVIEW_SIZE[1]},
        }
    }
    if preview_failures:
        failure_count = len(preview_failures)
        manifest_kwargs["warnings"] = [
            f"Warning: failed to generate {failure_count} preview image(s); some cards may show 'Preview unavailable'."
        ]
        manifest_kwargs["warning_details"] = [
            {
                "kind": "preview_generation_failed",
                "count": failure_count,
                "items": preview_failures,
            }
        ]

    manifest = build_dashboard_manifest(
        config.output_dir,
        dashboard_stages,
        **manifest_kwargs,
    )
    save_dashboard_manifest(config.output_dir / "dashboard_manifest.js", manifest)
