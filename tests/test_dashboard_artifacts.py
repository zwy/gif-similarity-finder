import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from gif_similarity_finder.dashboard_artifacts import (
    save_preview_image,
    save_dashboard_manifest,
    save_dashboard_stage_shard,
)


class DashboardArtifactsTest(unittest.TestCase):
    def test_save_preview_image_generates_webp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            gif_path = tmp / "test.gif"
            # Create a simple 2-frame GIF
            img1 = Image.new("RGBA", (64, 64), (255, 0, 0, 255))
            img2 = Image.new("RGBA", (64, 64), (0, 255, 0, 255))
            img1.save(gif_path, format="GIF", save_all=True, append_images=[img2], loop=0)

            preview_path = tmp / "preview.webp"
            out = save_preview_image(gif_path, preview_path)
            self.assertIsNotNone(out)
            self.assertTrue(out.exists())
            self.assertEqual(out.suffix, ".webp")
            self.assertEqual(out, preview_path)

    def test_save_dashboard_manifest_writes_js_assignment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            manifest = {"a": 1, "b": [1, 2, 3]}
            path = tmp / "manifest.js"
            save_dashboard_manifest(path, manifest)
            content = path.read_text(encoding="utf-8")
            marker = "window.__GIF_DASHBOARD_MANIFEST__ = "
            self.assertIn(marker, content)
            payload = content.split(marker, 1)[1].strip().rstrip(";\n")
            data = json.loads(payload)
            self.assertEqual(data, manifest)

    def test_save_dashboard_stage_shard_writes_shard_assignment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            items = [{"id": "a"}, {"id": "b"}]
            shard = tmp / "shard1.js"
            save_dashboard_stage_shard(shard, "stageA", items)
            content = shard.read_text(encoding="utf-8")
            self.assertIn("window.__GIF_DASHBOARD_STAGE_SHARDS__", content)
            # key should include stage key and shard file name
            expected_key = "stageA:shard1.js"
            self.assertIn(expected_key, content)
            # Extract JSON after the = for the shard assignment
            marker = expected_key + "'] = "
            idx = content.find(marker)
            self.assertNotEqual(idx, -1)
            payload = content[idx + len(marker):].strip().rstrip(";\n")
            data = json.loads(payload)
            self.assertEqual(data, items)

    def test_save_dashboard_stage_shard_repeated_writes_do_not_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            items1 = [{"id": "a"}]
            items2 = [{"id": "b"}]
            shard = tmp / "shard1.js"
            save_dashboard_stage_shard(shard, "stageA", items1)
            save_dashboard_stage_shard(shard, "stageA", items2)
            content = shard.read_text(encoding="utf-8")
            expected_key = "stageA:shard1.js"
            marker = expected_key + "'] = "
            # ensure only one assignment block for this shard key
            self.assertEqual(content.count(marker), 1)
            # payload reflects last write
            idx = content.find(marker)
            payload = content[idx + len(marker):].strip().rstrip(";\n")
            data = json.loads(payload)
            self.assertEqual(data, items2)


if __name__ == "__main__":
    unittest.main()
