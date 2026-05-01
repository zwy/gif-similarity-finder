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
            self.assertEqual(report_path.name, "report_stage1_same_source.html")

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

    def test_save_umap_visualization_writes_file(self) -> None:
        # Use lightweight stubs for optional heavy deps so this remains a unit test
        embeddings = np.array([[0.1, 0.2], [0.2, 0.3], [0.3, 0.4], [0.4, 0.5]], dtype=np.float32)
        labels = np.array([0, 1, 0, 1])

        import types
        import sys

        # Fake umap module with deterministic UMAP.transform
        fake_umap = types.ModuleType("umap")
        class FakeUMAP:
            def __init__(self, n_components, random_state, n_neighbors, min_dist):
                pass
            def fit_transform(self, embeddings_in):
                n = embeddings_in.shape[0]
                return np.arange(n * 2, dtype=np.float32).reshape(n, 2)
        fake_umap.UMAP = FakeUMAP

        # Fake matplotlib.cm.tab20 that returns a predictable color array
        fake_cm = types.ModuleType("matplotlib.cm")
        def tab20(x):
            # return a color per input entry
            return np.tile(np.linspace(0, 1, len(x)).reshape(-1, 1), (1, 4)).astype(np.float32)
        fake_cm.tab20 = tab20

        # Fake matplotlib.pyplot that writes a minimal file when savefig is called
        fake_plt = types.ModuleType("matplotlib.pyplot")
        class _Fig:
            pass
        class _Axis:
            def scatter(self, *args, **kwargs):
                pass
        def _subplots(figsize=(14, 10)):
            return (_Fig(), _Axis())
        def _tight_layout():
            pass
        def _savefig(path, dpi=None, bbox_inches=None):
            Path(path).write_bytes(b"PNGDATA")
        def _close(fig):
            pass
        fake_plt.subplots = _subplots
        fake_plt.tight_layout = _tight_layout
        fake_plt.savefig = _savefig
        fake_plt.close = _close

        # Install fake modules into sys.modules (both package and submodules)
        sys_modules_backup = {}
        for name, mod in [("umap", fake_umap), ("matplotlib", types.ModuleType("matplotlib")), ("matplotlib.cm", fake_cm), ("matplotlib.pyplot", fake_plt)]:
            sys_modules_backup[name] = sys.modules.get(name)
            # If installing the top-level matplotlib package, ensure it exposes cm and pyplot
            if name == "matplotlib":
                matplotlib_pkg = types.ModuleType("matplotlib")
                matplotlib_pkg.cm = fake_cm
                matplotlib_pkg.pyplot = fake_plt
                sys.modules["matplotlib"] = matplotlib_pkg
            else:
                sys.modules[name] = mod

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                out = save_umap_visualization(Path(tmp_dir), embeddings, labels)
                self.assertIsNotNone(out)
                self.assertTrue((Path(tmp_dir) / "umap_clusters.png").exists())
        finally:
            # Restore sys.modules
            for name, prev in sys_modules_backup.items():
                if prev is None:
                    del sys.modules[name]
                else:
                    sys.modules[name] = prev



class ArtifactsReportShellTest(unittest.TestCase):
    def test_save_html_report_outputs_report_shell_and_embedded_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            report_path = save_html_report(
                output_dir,
                {0: ["/tmp/a.gif", "/tmp/b.gif"], -1: ["/tmp/c.gif"]},
                "stage1_same_source",
            )

            html = report_path.read_text(encoding="utf-8")

        self.assertIn("window.__REPORT_DATA__", html)
        self.assertIn("report-grid", html)
        self.assertIn("Virtualized grid ready", html)
        self.assertIn("stage1_same_source", html)
        self.assertIn("Total items", html)

    def test_save_html_report_does_not_pre_render_all_cards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            groups = {0: [f"/tmp/{index}.gif" for index in range(50)]}
            report_path = save_html_report(output_dir, groups, "stage2_action_clusters")

            html = report_path.read_text(encoding="utf-8")

        self.assertLess(html.count('class="report-card"'), 50)
        self.assertIn("report-hide-noise", html)
        self.assertIn("Action clusters", html)


if __name__ == "__main__":
    unittest.main()
