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


if __name__ == "__main__":
    unittest.main()
