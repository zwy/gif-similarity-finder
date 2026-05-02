import tempfile
import unittest
from argparse import Namespace
from dataclasses import asdict
from pathlib import Path
from unittest import mock

import gif_similarity
import numpy as np

import gif_similarity_finder.pipeline as pipeline_module
from gif_similarity_finder.dashboard_data import DashboardItem, DashboardShard, DashboardStage, DashboardSummary
from gif_similarity_finder.pipeline import run_pipeline
from gif_similarity_finder.stage2 import run_stage2
from gif_similarity_finder.types import (
    EmbeddingCacheData,
    PipelineConfig,
    Stage1Result,
    Stage2Result,
)


class CliTest(unittest.TestCase):
    def test_resolve_output_dir_defaults_to_repo_output(self) -> None:
        expected = Path(gif_similarity.__file__).resolve().parent / "output"
        self.assertEqual(gif_similarity.resolve_output_dir(None), expected)

    def test_main_uses_repo_local_output_when_cli_omits_output(self) -> None:
        args = Namespace(
            input="input",
            output=None,
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
        self.assertEqual(config.output_dir, Path(gif_similarity.__file__).resolve().parent / "output")

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

        run_pipeline_mock.assert_called_once()
        config = run_pipeline_mock.call_args.args[0]
        self.assertEqual(config.input_dir, Path("input"))
        self.assertEqual(config.output_dir, Path("output"))
        self.assertEqual(config.frames, 8)
        self.assertEqual(config.hash_threshold, 10)
        self.assertEqual(config.min_cluster_size, 3)
        self.assertEqual(config.batch_size, 32)
        self.assertEqual(config.device, "auto")
        self.assertFalse(config.skip_stage1)
        self.assertTrue(config.skip_stage2)

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

    def test_run_stage2_empty_result(self) -> None:
        empty_embeddings = np.empty((0, 0), dtype=np.float32)

        with mock.patch("gif_similarity_finder.stage2.load_clip_model", return_value=("model", "pre", "cpu")), mock.patch(
            "gif_similarity_finder.stage2.extract_all_embeddings",
            return_value=([], empty_embeddings),
        ), mock.patch("gif_similarity_finder.stage2.cluster_hdbscan") as cluster_mock:
            result = run_stage2(
                gif_paths=[],
                n_frames=8,
                batch_size=32,
                min_cluster_size=3,
                device="auto",
                cache_data=None,
            )

        cluster_mock.assert_not_called()
        self.assertEqual(result.groups, {})
        self.assertEqual(result.valid_paths, [])
        self.assertEqual(result.embeddings.shape, (0, 0))
        self.assertEqual(result.labels.size, 0)

    def test_run_stage2_no_persistence_side_effects(self) -> None:
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


class PipelineOrchestrationTest(unittest.TestCase):
    def make_config(
        self,
        tmp_dir: str,
        *,
        skip_stage1: bool = False,
        skip_stage2: bool = False,
    ) -> PipelineConfig:
        return PipelineConfig(
            input_dir=Path(tmp_dir),
            output_dir=Path(tmp_dir) / "output",
            frames=8,
            hash_threshold=10,
            min_cluster_size=3,
            batch_size=32,
            device="auto",
            skip_stage1=skip_stage1,
            skip_stage2=skip_stage2,
        )

    def make_stage(self, stage_key: str, gif_paths: list[Path]) -> DashboardStage:
        items = [
            DashboardItem(
                id=f"{stage_key}-{index}",
                name=gif_path.stem,
                gif_path=str(gif_path),
                preview_path=f"previews/{stage_key}-{index}.webp",
                group_id="0",
                group_size=1,
                is_noise=False,
                stage=stage_key,
            )
            for index, gif_path in enumerate(gif_paths)
        ]
        summary = DashboardSummary(
            total_items=len(items),
            total_groups=1 if items else 0,
            grouped_items=len(items),
            noise_items=0,
            largest_group_size=1 if items else 0,
        )
        return DashboardStage(stage_key=stage_key, summary=summary, items=items)

    def test_run_pipeline_wires_stage_calls_and_artifact_writers(self) -> None:
        self.assertFalse(hasattr(pipeline_module, "save_html_report"))
        cache_data = EmbeddingCacheData(
            paths=[Path("cached.gif")],
            embeddings=np.array([[0.1, 0.2]], dtype=np.float32),
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.make_config(tmp_dir)
            cache_path = config.output_dir / "clip_embeddings_cache.npz"
            gif_a = Path(tmp_dir) / "a.gif"
            gif_b = Path(tmp_dir) / "b.gif"
            gif_a.write_bytes(b"GIF89a")
            gif_b.write_bytes(b"GIF89a")
            gif_paths = [gif_a, gif_b]
            stage1_result = Stage1Result(groups={0: [str(gif_a)]}, hashed_paths=gif_paths, match_count=1)
            stage2_result = Stage2Result(
                groups={1: [str(gif_b)]},
                valid_paths=gif_paths,
                embeddings=np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
                labels=np.array([1, 1], dtype=np.int64),
            )
            stage1_dashboard = self.make_stage("stage1_same_source", [gif_a])
            stage2_dashboard = self.make_stage("stage2_action_clusters", [gif_b])
            stage1_shard = DashboardShard(file_name="dashboard_stage1_000.js", items=stage1_dashboard.items)
            stage2_shard = DashboardShard(file_name="dashboard_stage2_000.js", items=stage2_dashboard.items)
            manifest_payload = {"stage1_same_source": {"shards": []}, "stage2_action_clusters": {"shards": []}}

            with mock.patch("gif_similarity_finder.pipeline.collect_gifs", return_value=gif_paths) as collect_mock, mock.patch(
                "gif_similarity_finder.pipeline.run_stage1", return_value=stage1_result
            ) as stage1_mock, mock.patch(
                "gif_similarity_finder.pipeline.load_embedding_cache", return_value=cache_data
            ) as load_cache_mock, mock.patch(
                "gif_similarity_finder.pipeline.run_stage2", return_value=stage2_result
            ) as stage2_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_group_json"
            ) as save_group_json_mock, mock.patch(
                "gif_similarity_finder.pipeline.build_dashboard_stage",
                side_effect=[stage1_dashboard, stage2_dashboard],
            ) as build_dashboard_stage_mock, mock.patch(
                "gif_similarity_finder.pipeline.split_stage_items",
                side_effect=[[stage1_shard], [stage2_shard]],
            ) as split_stage_items_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_preview_image"
            ) as save_preview_image_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_dashboard_stage_shard"
            ) as save_dashboard_stage_shard_mock, mock.patch(
                "gif_similarity_finder.pipeline.build_dashboard_manifest", return_value=manifest_payload
            ) as build_dashboard_manifest_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_dashboard_manifest"
            ) as save_dashboard_manifest_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_embedding_cache"
            ) as save_embedding_cache_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_hnsw_index"
            ) as save_hnsw_index_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_umap_visualization"
            ) as save_umap_visualization_mock:
                run_pipeline(config)

        collect_mock.assert_called_once_with(config.input_dir)
        stage1_mock.assert_called_once_with(gif_paths, hash_threshold=config.hash_threshold)
        load_cache_mock.assert_called_once_with(cache_path)
        stage2_mock.assert_called_once_with(
            gif_paths=gif_paths,
            n_frames=config.frames,
            batch_size=config.batch_size,
            min_cluster_size=config.min_cluster_size,
            device=config.device,
            cache_data=cache_data,
        )
        save_group_json_mock.assert_has_calls(
            [
                mock.call(config.output_dir / "stage1_same_source_groups.json", stage1_result.groups),
                mock.call(config.output_dir / "stage2_action_clusters.json", stage2_result.groups),
            ]
        )
        build_dashboard_stage_mock.assert_has_calls(
            [
                mock.call("stage1_same_source", stage1_result.groups, preview_dir_name="previews"),
                mock.call("stage2_action_clusters", stage2_result.groups, preview_dir_name="previews"),
            ]
        )
        split_stage_items_mock.assert_has_calls(
            [mock.call(stage1_dashboard, shard_size=1000), mock.call(stage2_dashboard, shard_size=1000)]
        )
        save_preview_image_mock.assert_has_calls(
            [
                mock.call(gif_a, config.output_dir / stage1_dashboard.items[0].preview_path),
                mock.call(gif_b, config.output_dir / stage2_dashboard.items[0].preview_path),
            ]
        )
        save_dashboard_stage_shard_mock.assert_has_calls(
            [
                mock.call(config.output_dir / stage1_shard.file_name, stage1_dashboard.stage_key, [asdict(item) for item in stage1_shard.items]),
                mock.call(config.output_dir / stage2_shard.file_name, stage2_dashboard.stage_key, [asdict(item) for item in stage2_shard.items]),
            ]
        )
        build_dashboard_manifest_mock.assert_called_once_with(
            config.output_dir,
            [stage1_dashboard, stage2_dashboard],
            preview_config={
                "dir": "previews",
                "format": "webp",
                "kind": "first_frame",
                "size": {"width": 240, "height": 240},
            },
        )
        save_dashboard_manifest_mock.assert_called_once_with(config.output_dir / "dashboard_manifest.js", manifest_payload)
        save_embedding_cache_mock.assert_called_once()
        cache_call_args = save_embedding_cache_mock.call_args.args
        self.assertEqual(cache_call_args[0], cache_path)
        self.assertEqual(cache_call_args[1].paths, stage2_result.valid_paths)
        np.testing.assert_array_equal(cache_call_args[1].embeddings, stage2_result.embeddings)
        save_hnsw_index_mock.assert_called_once_with(config.output_dir / "hnsw.index", stage2_result.embeddings)
        save_umap_visualization_mock.assert_called_once_with(
            config.output_dir,
            stage2_result.embeddings,
            stage2_result.labels,
        )

    def test_run_pipeline_skips_stage1_when_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.make_config(tmp_dir, skip_stage1=True)
            gif_a = Path(tmp_dir) / "a.gif"
            gif_a.write_bytes(b"GIF89a")
            gif_paths = [gif_a]
            stage2_result = Stage2Result(
                groups={0: [str(gif_a)]},
                valid_paths=gif_paths,
                embeddings=np.array([[1.0, 0.0]], dtype=np.float32),
                labels=np.array([0], dtype=np.int64),
            )
            stage2_dashboard = self.make_stage("stage2_action_clusters", [gif_a])
            stage2_shard = DashboardShard(file_name="dashboard_stage2_000.js", items=stage2_dashboard.items)
            manifest_payload = {"stage2_action_clusters": {"shards": []}}

            with mock.patch("gif_similarity_finder.pipeline.collect_gifs", return_value=gif_paths), mock.patch(
                "gif_similarity_finder.pipeline.run_stage1"
            ) as stage1_mock, mock.patch(
                "gif_similarity_finder.pipeline.load_embedding_cache", return_value=None
            ) as load_cache_mock, mock.patch(
                "gif_similarity_finder.pipeline.run_stage2", return_value=stage2_result
            ) as stage2_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_group_json"
            ) as save_group_json_mock, mock.patch(
                "gif_similarity_finder.pipeline.build_dashboard_stage", return_value=stage2_dashboard
            ) as build_dashboard_stage_mock, mock.patch(
                "gif_similarity_finder.pipeline.split_stage_items", return_value=[stage2_shard]
            ) as split_stage_items_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_preview_image"
            ) as save_preview_image_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_dashboard_stage_shard"
            ) as save_dashboard_stage_shard_mock, mock.patch(
                "gif_similarity_finder.pipeline.build_dashboard_manifest", return_value=manifest_payload
            ) as build_dashboard_manifest_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_dashboard_manifest"
            ) as save_dashboard_manifest_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_embedding_cache"
            ) as save_embedding_cache_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_hnsw_index"
            ) as save_hnsw_index_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_umap_visualization"
            ) as save_umap_visualization_mock:
                run_pipeline(config)

        stage1_mock.assert_not_called()
        load_cache_mock.assert_called_once_with(config.output_dir / "clip_embeddings_cache.npz")
        stage2_mock.assert_called_once()
        save_group_json_mock.assert_called_once_with(config.output_dir / "stage2_action_clusters.json", stage2_result.groups)
        build_dashboard_stage_mock.assert_called_once_with("stage2_action_clusters", stage2_result.groups, preview_dir_name="previews")
        split_stage_items_mock.assert_called_once_with(stage2_dashboard, shard_size=1000)
        save_preview_image_mock.assert_called_once_with(gif_a, config.output_dir / stage2_dashboard.items[0].preview_path)
        save_dashboard_stage_shard_mock.assert_called_once_with(
            config.output_dir / stage2_shard.file_name,
            stage2_dashboard.stage_key,
            [asdict(item) for item in stage2_shard.items],
        )
        build_dashboard_manifest_mock.assert_called_once_with(
            config.output_dir,
            [stage2_dashboard],
            preview_config={
                "dir": "previews",
                "format": "webp",
                "kind": "first_frame",
                "size": {"width": 240, "height": 240},
            },
        )
        save_dashboard_manifest_mock.assert_called_once_with(config.output_dir / "dashboard_manifest.js", manifest_payload)
        save_embedding_cache_mock.assert_called_once()
        save_hnsw_index_mock.assert_called_once_with(config.output_dir / "hnsw.index", stage2_result.embeddings)
        save_umap_visualization_mock.assert_called_once_with(
            config.output_dir,
            stage2_result.embeddings,
            stage2_result.labels,
        )

    def test_run_pipeline_skips_stage2_when_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.make_config(tmp_dir, skip_stage2=True)
            gif_a = Path(tmp_dir) / "a.gif"
            gif_a.write_bytes(b"GIF89a")
            gif_paths = [gif_a]
            stage1_result = Stage1Result(groups={0: [str(gif_a)]}, hashed_paths=gif_paths, match_count=1)
            stage1_dashboard = self.make_stage("stage1_same_source", [gif_a])
            stage1_shard = DashboardShard(file_name="dashboard_stage1_000.js", items=stage1_dashboard.items)
            manifest_payload = {"stage1_same_source": {"shards": []}}

            with mock.patch("gif_similarity_finder.pipeline.collect_gifs", return_value=gif_paths), mock.patch(
                "gif_similarity_finder.pipeline.run_stage1", return_value=stage1_result
            ) as stage1_mock, mock.patch(
                "gif_similarity_finder.pipeline.load_embedding_cache"
            ) as load_cache_mock, mock.patch(
                "gif_similarity_finder.pipeline.run_stage2"
            ) as stage2_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_group_json"
            ) as save_group_json_mock, mock.patch(
                "gif_similarity_finder.pipeline.build_dashboard_stage", return_value=stage1_dashboard
            ) as build_dashboard_stage_mock, mock.patch(
                "gif_similarity_finder.pipeline.split_stage_items", return_value=[stage1_shard]
            ) as split_stage_items_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_preview_image"
            ) as save_preview_image_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_dashboard_stage_shard"
            ) as save_dashboard_stage_shard_mock, mock.patch(
                "gif_similarity_finder.pipeline.build_dashboard_manifest", return_value=manifest_payload
            ) as build_dashboard_manifest_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_dashboard_manifest"
            ) as save_dashboard_manifest_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_embedding_cache"
            ) as save_embedding_cache_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_hnsw_index"
            ) as save_hnsw_index_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_umap_visualization"
            ) as save_umap_visualization_mock:
                run_pipeline(config)

        stage1_mock.assert_called_once_with(gif_paths, hash_threshold=config.hash_threshold)
        load_cache_mock.assert_not_called()
        stage2_mock.assert_not_called()
        save_group_json_mock.assert_called_once_with(config.output_dir / "stage1_same_source_groups.json", stage1_result.groups)
        build_dashboard_stage_mock.assert_called_once_with("stage1_same_source", stage1_result.groups, preview_dir_name="previews")
        split_stage_items_mock.assert_called_once_with(stage1_dashboard, shard_size=1000)
        save_preview_image_mock.assert_called_once_with(gif_a, config.output_dir / stage1_dashboard.items[0].preview_path)
        save_dashboard_stage_shard_mock.assert_called_once_with(
            config.output_dir / stage1_shard.file_name,
            stage1_dashboard.stage_key,
            [asdict(item) for item in stage1_shard.items],
        )
        build_dashboard_manifest_mock.assert_called_once_with(
            config.output_dir,
            [stage1_dashboard],
            preview_config={
                "dir": "previews",
                "format": "webp",
                "kind": "first_frame",
                "size": {"width": 240, "height": 240},
            },
        )
        save_dashboard_manifest_mock.assert_called_once_with(config.output_dir / "dashboard_manifest.js", manifest_payload)
        save_embedding_cache_mock.assert_not_called()
        save_hnsw_index_mock.assert_not_called()
        save_umap_visualization_mock.assert_not_called()

    def test_run_pipeline_skips_stage2_embedding_artifacts_without_valid_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.make_config(tmp_dir)
            gif_a = Path(tmp_dir) / "a.gif"
            gif_a.write_bytes(b"GIF89a")
            gif_paths = [gif_a]
            stage1_result = Stage1Result(groups={0: [str(gif_a)]}, hashed_paths=gif_paths, match_count=1)
            stage2_result = Stage2Result(
                groups={},
                valid_paths=[],
                embeddings=np.empty((0, 0), dtype=np.float32),
                labels=np.array([], dtype=np.int64),
            )
            stage1_dashboard = self.make_stage("stage1_same_source", [gif_a])
            stage2_dashboard = self.make_stage("stage2_action_clusters", [])
            stage1_shard = DashboardShard(file_name="dashboard_stage1_000.js", items=stage1_dashboard.items)
            manifest_payload = {"stage1_same_source": {"shards": []}, "stage2_action_clusters": {"shards": []}}

            with mock.patch("gif_similarity_finder.pipeline.collect_gifs", return_value=gif_paths), mock.patch(
                "gif_similarity_finder.pipeline.run_stage1", return_value=stage1_result
            ), mock.patch("gif_similarity_finder.pipeline.load_embedding_cache", return_value=None), mock.patch(
                "gif_similarity_finder.pipeline.run_stage2", return_value=stage2_result
            ), mock.patch("gif_similarity_finder.pipeline.save_group_json") as save_group_json_mock, mock.patch(
                "gif_similarity_finder.pipeline.build_dashboard_stage",
                side_effect=[stage1_dashboard, stage2_dashboard],
            ) as build_dashboard_stage_mock, mock.patch(
                "gif_similarity_finder.pipeline.split_stage_items",
                side_effect=[[stage1_shard], []],
            ) as split_stage_items_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_preview_image"
            ) as save_preview_image_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_dashboard_stage_shard"
            ) as save_dashboard_stage_shard_mock, mock.patch(
                "gif_similarity_finder.pipeline.build_dashboard_manifest", return_value=manifest_payload
            ) as build_dashboard_manifest_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_dashboard_manifest"
            ) as save_dashboard_manifest_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_embedding_cache"
            ) as save_embedding_cache_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_hnsw_index"
            ) as save_hnsw_index_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_umap_visualization"
            ) as save_umap_visualization_mock:
                run_pipeline(config)

        save_group_json_mock.assert_has_calls(
            [
                mock.call(config.output_dir / "stage1_same_source_groups.json", stage1_result.groups),
                mock.call(config.output_dir / "stage2_action_clusters.json", stage2_result.groups),
            ]
        )
        build_dashboard_stage_mock.assert_has_calls(
            [
                mock.call("stage1_same_source", stage1_result.groups, preview_dir_name="previews"),
                mock.call("stage2_action_clusters", stage2_result.groups, preview_dir_name="previews"),
            ]
        )
        split_stage_items_mock.assert_has_calls(
            [mock.call(stage1_dashboard, shard_size=1000), mock.call(stage2_dashboard, shard_size=1000)]
        )
        save_preview_image_mock.assert_called_once_with(gif_a, config.output_dir / stage1_dashboard.items[0].preview_path)
        save_dashboard_stage_shard_mock.assert_called_once_with(
            config.output_dir / stage1_shard.file_name,
            stage1_dashboard.stage_key,
            [asdict(item) for item in stage1_shard.items],
        )
        build_dashboard_manifest_mock.assert_called_once_with(
            config.output_dir,
            [stage1_dashboard, stage2_dashboard],
            preview_config={
                "dir": "previews",
                "format": "webp",
                "kind": "first_frame",
                "size": {"width": 240, "height": 240},
            },
        )
        save_dashboard_manifest_mock.assert_called_once_with(config.output_dir / "dashboard_manifest.js", manifest_payload)
        save_embedding_cache_mock.assert_not_called()
        save_hnsw_index_mock.assert_not_called()
        save_umap_visualization_mock.assert_not_called()

    def test_run_pipeline_persists_stage1_dashboard_artifacts_before_stage2_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.make_config(tmp_dir)
            gif_a = Path(tmp_dir) / "a.gif"
            gif_a.write_bytes(b"GIF89a")
            gif_paths = [gif_a]
            stage1_result = Stage1Result(groups={0: [str(gif_a)]}, hashed_paths=gif_paths, match_count=1)
            stage1_dashboard = self.make_stage("stage1_same_source", [gif_a])
            stage1_shard = DashboardShard(file_name="dashboard_stage1_000.js", items=stage1_dashboard.items)

            with mock.patch("gif_similarity_finder.pipeline.collect_gifs", return_value=gif_paths), mock.patch(
                "gif_similarity_finder.pipeline.run_stage1", return_value=stage1_result
            ), mock.patch("gif_similarity_finder.pipeline.load_embedding_cache", return_value=None), mock.patch(
                "gif_similarity_finder.pipeline.run_stage2", side_effect=RuntimeError("stage2 failed")
            ), mock.patch("gif_similarity_finder.pipeline.save_group_json") as save_group_json_mock, mock.patch(
                "gif_similarity_finder.pipeline.build_dashboard_stage",
                return_value=stage1_dashboard,
            ) as build_dashboard_stage_mock, mock.patch(
                "gif_similarity_finder.pipeline.split_stage_items",
                return_value=[stage1_shard],
            ) as split_stage_items_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_preview_image"
            ) as save_preview_image_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_dashboard_stage_shard"
            ) as save_dashboard_stage_shard_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_dashboard_manifest"
            ) as save_dashboard_manifest_mock:
                with self.assertRaisesRegex(RuntimeError, "stage2 failed"):
                    run_pipeline(config)

        save_group_json_mock.assert_called_once_with(config.output_dir / "stage1_same_source_groups.json", stage1_result.groups)
        build_dashboard_stage_mock.assert_called_once_with("stage1_same_source", stage1_result.groups, preview_dir_name="previews")
        split_stage_items_mock.assert_called_once_with(stage1_dashboard, shard_size=1000)
        save_preview_image_mock.assert_called_once_with(gif_a, config.output_dir / stage1_dashboard.items[0].preview_path)
        save_dashboard_stage_shard_mock.assert_called_once_with(
            config.output_dir / stage1_shard.file_name,
            stage1_dashboard.stage_key,
            [asdict(item) for item in stage1_shard.items],
        )
        save_dashboard_manifest_mock.assert_not_called()

    def test_run_pipeline_includes_preview_generation_failures_in_manifest_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.make_config(tmp_dir, skip_stage2=True)
            gif_a = Path(tmp_dir) / "a.gif"
            gif_a.write_bytes(b"GIF89a")
            gif_paths = [gif_a]
            stage1_result = Stage1Result(groups={0: [str(gif_a)]}, hashed_paths=gif_paths, match_count=1)
            stage1_dashboard = self.make_stage("stage1_same_source", [gif_a])
            stage1_shard = DashboardShard(file_name="dashboard_stage1_000.js", items=stage1_dashboard.items)
            manifest_payload = {"stage1_same_source": {"shards": []}}

            with mock.patch("gif_similarity_finder.pipeline.collect_gifs", return_value=gif_paths), mock.patch(
                "gif_similarity_finder.pipeline.run_stage1", return_value=stage1_result
            ), mock.patch("gif_similarity_finder.pipeline.save_group_json"), mock.patch(
                "gif_similarity_finder.pipeline.build_dashboard_stage", return_value=stage1_dashboard
            ), mock.patch(
                "gif_similarity_finder.pipeline.split_stage_items", return_value=[stage1_shard]
            ), mock.patch(
                "gif_similarity_finder.pipeline.save_preview_image", return_value=None
            ), mock.patch(
                "gif_similarity_finder.pipeline.save_dashboard_stage_shard"
            ), mock.patch(
                "gif_similarity_finder.pipeline.build_dashboard_manifest", return_value=manifest_payload
            ) as build_dashboard_manifest_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_dashboard_manifest"
            ):
                run_pipeline(config)

        _, _, kwargs = build_dashboard_manifest_mock.mock_calls[0]
        self.assertIn("warnings", kwargs)
        self.assertIn("warning_details", kwargs)
        self.assertIn("failed to generate 1 preview image", kwargs["warnings"][0].lower())
        self.assertEqual(kwargs["warning_details"][0]["kind"], "preview_generation_failed")
        self.assertEqual(kwargs["warning_details"][0]["count"], 1)
        self.assertEqual(kwargs["warning_details"][0]["items"][0]["gif_path"], str(gif_a))


if __name__ == "__main__":
    unittest.main()
