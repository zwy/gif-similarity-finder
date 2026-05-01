import logging

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
