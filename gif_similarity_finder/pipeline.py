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


def run_pipeline(config: PipelineConfig) -> None:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    gif_paths = collect_gifs(config.input_dir)
    if not gif_paths:
        raise SystemExit("No GIF files found. Check --input path.")

    dashboard_stages = []
    if not config.skip_stage1:
        stage1_result = run_stage1(gif_paths, hash_threshold=config.hash_threshold)
        save_group_json(config.output_dir / "stage1_same_source_groups.json", stage1_result.groups)
        dashboard_stages.append(
            build_dashboard_stage("stage1_same_source", stage1_result.groups, preview_dir_name="previews")
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
        )
        save_group_json(config.output_dir / "stage2_action_clusters.json", stage2_result.groups)
        dashboard_stages.append(
            build_dashboard_stage("stage2_action_clusters", stage2_result.groups, preview_dir_name="previews")
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

    saved_preview_targets: set[tuple[str, str]] = set()
    for stage in dashboard_stages:
        for item in stage.items:
            gif_path = Path(item.gif_path)
            preview_path = config.output_dir / item.preview_path
            dedupe_key = (str(gif_path), str(preview_path))
            if dedupe_key in saved_preview_targets:
                continue
            if gif_path.exists():
                save_preview_image(gif_path, preview_path)
            saved_preview_targets.add(dedupe_key)

        shards = split_stage_items(stage, shard_size=1000)
        for shard in shards:
            save_dashboard_stage_shard(
                config.output_dir / shard.file_name,
                stage.stage_key,
                _serialize_dashboard_items(shard.items),
            )

    manifest = build_dashboard_manifest(config.output_dir, dashboard_stages)
    save_dashboard_manifest(config.output_dir / "dashboard_manifest.js", manifest)
