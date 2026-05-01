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
    save_hnsw_index,
    save_umap_visualization,
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

            # The report should exist inside the provided output directory
            # while that directory is active; do the assertion inside the
            # TemporaryDirectory scope.
            self.assertTrue(report_path.exists())

    def test_save_hnsw_index_creates_file(self) -> None:
        try:
            import hnswlib  # type: ignore
        except ImportError:
            self.skipTest("hnswlib not installed")

        rs = np.random.RandomState(42)
        embeddings = rs.rand(10, 16).astype(np.float32)
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "index.bin"
            target = save_hnsw_index(path, embeddings)
            self.assertTrue(target.exists())

    def test_save_umap_visualization_graceful_when_missing_deps(self) -> None:
        # Simulate ImportError for optional dependencies using a patched __import__
        embeddings = np.zeros((4, 8), dtype=np.float32)
        labels = np.array([0, 1, 0, 1])

        import builtins as _builtins
        real_import = _builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name.startswith("umap") or name.startswith("matplotlib"):
                raise ImportError("simulated missing optional dependency")
            return real_import(name, globals, locals, fromlist, level)

        with mock.patch("builtins.__import__", side_effect=fake_import):
            with tempfile.TemporaryDirectory() as tmp_dir:
                result = save_umap_visualization(Path(tmp_dir), embeddings, labels)
                self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
