import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from gif_similarity_finder.artifacts import (
    load_embedding_cache,
    save_embedding_cache,
    save_group_json,
    save_html_report,
)
from gif_similarity_finder.types import EmbeddingCacheData


class ArtifactsTest(unittest.TestCase):
    def test_save_group_json_writes_string_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            target = save_group_json(output_dir / "groups.json", {0: ["a.gif"], -1: ["b.gif"]})

            payload = json.loads(target.read_text(encoding="utf-8"))

        self.assertEqual(payload, {"0": ["a.gif"], "-1": ["b.gif"]})

    def test_cache_round_trip_preserves_paths_and_embeddings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_path = Path(tmp_dir) / "clip_embeddings_cache.npz"
            data = EmbeddingCacheData(paths=[Path("a.gif")], embeddings=np.array([[1.0, 0.0]], dtype=np.float32))

            save_embedding_cache(cache_path, data)
            restored = load_embedding_cache(cache_path)

        self.assertEqual(restored.paths, [Path("a.gif")])
        self.assertEqual(restored.embeddings.shape, (1, 2))

    def test_save_html_report_creates_report_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            report_path = save_html_report(output_dir, {0: ["a.gif"]}, "stage1_same_source")

        self.assertTrue(report_path.exists())


if __name__ == "__main__":
    unittest.main()
