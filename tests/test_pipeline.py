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


if __name__ == "__main__":
    unittest.main()
