import unittest
from pathlib import Path

from gif_similarity_finder.types import PipelineConfig, Stage1Result


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




import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from gif_similarity_finder.stage2 import run_stage2


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
        # When no embeddings are extracted, run_stage2 should return an empty Stage2Result
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

        # cluster_hdbscan should not be called when there are no valid paths
        cluster_mock.assert_not_called()
        self.assertEqual(result.groups, {})
        self.assertEqual(result.valid_paths, [])
        self.assertEqual(result.embeddings.shape, (0, 0))
        self.assertEqual(result.labels.size, 0)

    def test_run_stage2_no_persistence_side_effects(self) -> None:
        # Ensure run_stage2 does not call persistence functions (e.g., saving files/indexes)
        embeddings = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
        labels = np.array([0, -1], dtype=np.int64)

        # Patch potential persistence side-effect functions in the top-level CLI module
        with mock.patch("gif_similarity.save_html_report") as mock_save_html, \
            mock.patch("gif_similarity.np.savez") as mock_savez, \
            mock.patch("gif_similarity.build_hnswlib_index") as mock_build_index, \
            mock.patch("gif_similarity.visualise_clusters") as mock_visualise, \
            mock.patch("gif_similarity_finder.stage2.load_clip_model", return_value=("model", "pre", "cpu")), \
            mock.patch(
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

        # None of the top-level CLI persistence functions should have been called by run_stage2
        mock_save_html.assert_not_called()
        mock_savez.assert_not_called()
        mock_build_index.assert_not_called()
        mock_visualise.assert_not_called()

        # And the result should still be as expected
        self.assertEqual(result.groups[0], ["a.gif"])
        self.assertEqual(result.groups[-1], ["b.gif"])


if __name__ == "__main__":
    unittest.main()
