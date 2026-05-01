import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from gif_similarity_finder.stage1 import hamming_distance_frames, run_stage1


class Stage1Test(unittest.TestCase):
    def test_hamming_distance_uses_shortest_length(self) -> None:
        left = np.array([[1, 0, 1], [1, 1, 0]], dtype=np.uint8)
        right = np.array([[1, 1, 1]], dtype=np.uint8)
        self.assertEqual(hamming_distance_frames(left, right), 1.0)

    def test_run_stage1_returns_grouped_result_without_writing_files(self) -> None:
        paths = [Path("a.gif"), Path("b.gif"), Path("c.gif")]
        fake_hashes = {
            Path("a.gif"): np.array([[1, 0]], dtype=np.uint8),
            Path("b.gif"): np.array([[1, 0]], dtype=np.uint8),
            Path("c.gif"): np.array([[0, 1]], dtype=np.uint8),
        }

        with mock.patch(
            "gif_similarity_finder.stage1.compute_phash",
            side_effect=lambda path, n_frames=6: fake_hashes.get(path),
        ):
            result = run_stage1(paths, hash_threshold=0)

        self.assertEqual(result.groups[0], ["a.gif", "b.gif"])
        self.assertEqual(result.groups[-1], ["c.gif"])
        self.assertEqual(result.match_count, 1)


if __name__ == "__main__":
    unittest.main()
