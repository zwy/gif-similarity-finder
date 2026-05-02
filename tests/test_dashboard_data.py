import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image
from gif_similarity_finder import dashboard_data as dd

class TestDashboardData(unittest.TestCase):
    def test_build_dashboard_stage_summary_and_items(self):
        groups = {
            "g1": ["/gifs/a.gif", "/gifs/b.gif"],
            "-1": ["/gifs/c.gif"],
            "g3": ["/gifs/d.gif", "/gifs/e.gif", "/gifs/f.gif"],
        }
        stage = dd.build_dashboard_stage("stage1", groups, preview_dir_name="previews")
        self.assertEqual(stage.stage_key, "stage1")
        # summary checks
        self.assertEqual(stage.summary.total_items, 6)
        self.assertEqual(stage.summary.total_groups, 2)
        self.assertEqual(stage.summary.grouped_items, 5)
        self.assertEqual(stage.summary.noise_items, 1)
        self.assertEqual(stage.summary.largest_group_size, 3)
        # items checks
        ids = {item.id for item in stage.items}
        self.assertEqual(len(ids), 6)
        for item in stage.items:
            # name should be file stem
            self.assertIn(item.name, ["a", "b", "c", "d", "e", "f"])
            # preview path must equal previews/{stable_id}.webp
            expected = f"previews/{dd.stable_item_id(Path(item.gif_path))}.webp"
            self.assertEqual(item.preview_path, expected)

    def test_stable_item_id_is_deterministic(self):
        p = Path("/gifs/a.gif")
        id1 = dd.stable_item_id(p)
        id2 = dd.stable_item_id(p)
        self.assertEqual(id1, id2)
        self.assertEqual(len(id1), 16)

    def test_build_dashboard_stage_normalizes_relative_gif_paths_to_absolute(self):
        groups = {"g1": ["relative/path/a.gif"]}
        stage = dd.build_dashboard_stage("stage1", groups, preview_dir_name="previews")
        self.assertEqual(len(stage.items), 1)
        expected_gif_path = str(Path("relative/path/a.gif").resolve())
        self.assertEqual(stage.items[0].gif_path, expected_gif_path)
        self.assertTrue(Path(stage.items[0].gif_path).is_absolute())
        self.assertEqual(
            stage.items[0].preview_path,
            f"previews/{dd.stable_item_id(Path(expected_gif_path))}.webp",
        )

    def test_split_stage_items_shards(self):
        groups = {"g1": [f"/gifs/{i}.gif" for i in range(5)]}
        stage = dd.build_dashboard_stage("stage1_same_source", groups, preview_dir_name="previews")
        shards = dd.split_stage_items(stage, shard_size=2)
        # expect 3 shards: 2,2,1
        self.assertEqual([len(s.items) for s in shards], [2,2,1])
        # filenames use fixed stage family mapping (stage1)
        expected_names = ["dashboard_stage1_000.js", "dashboard_stage1_001.js", "dashboard_stage1_002.js"]
        self.assertEqual([s.file_name for s in shards], expected_names)

    def test_build_dashboard_manifest_json_serializable(self):
        groups = {
            "g1": ["/gifs/a.gif", "/gifs/b.gif"],
            "-1": ["/gifs/c.gif"],
        }
        stage = dd.build_dashboard_stage("stage1", groups, preview_dir_name="previews")
        manifest = dd.build_dashboard_manifest(Path("out"), [stage])
        # Ensure JSON serialization works
        import json
        json.dumps(manifest)  # should not raise
        # check shard list and summary values
        self.assertIn("meta", manifest)
        self.assertIn("output_dir", manifest["meta"])
        self.assertIn("stage1", manifest)
        self.assertEqual(manifest["stage1"]["summary"]["total_items"], 3)
        self.assertEqual(len(manifest["stage1"]["shards"]), 1)
        shard = manifest["stage1"]["shards"][0]
        self.assertEqual(shard["file_name"], "dashboard_stage1_000.js")
        self.assertEqual(shard["size"], 3)
        self.assertEqual(shard["path"], str(Path("out") / shard["file_name"]))
        self.assertIn("generated_at", manifest["meta"])
        self.assertIn("available_stages", manifest["meta"])
        self.assertEqual(manifest["meta"]["available_stages"], ["stage1"])
        self.assertIn("preview", manifest["meta"])

    def test_build_dashboard_stage_best_effort_dimensions_when_available(self):
        with TemporaryDirectory() as tmp_dir:
            gif_path = Path(tmp_dir) / "sized.gif"
            Image.new("RGB", (16, 11), color="red").save(gif_path, format="GIF")
            stage = dd.build_dashboard_stage("stage1", {"g1": [str(gif_path)]}, preview_dir_name="previews")
            self.assertEqual(stage.items[0].width, 16)
            self.assertEqual(stage.items[0].height, 11)

    def test_build_dashboard_manifest_includes_stage_details(self):
        groups = {
            "g1": ["/gifs/a.gif", "/gifs/b.gif"],
            "-1": ["/gifs/c.gif"],
        }
        stage = dd.build_dashboard_stage("stage1", groups, preview_dir_name="previews")
        manifest = dd.build_dashboard_manifest(Path("out"), [stage])
        stage_manifest = manifest["stage1"]
        self.assertIn("stage", stage_manifest)
        self.assertEqual(stage_manifest["stage"]["stage_key"], "stage1")
        self.assertEqual(stage_manifest["stage"]["item_count"], 3)
        self.assertEqual(stage_manifest["stage"]["group_count"], 1)
        self.assertEqual(stage_manifest["stage"]["noise_count"], 1)
        self.assertEqual(stage_manifest["stage"]["shard_count"], 1)

if __name__ == '__main__':
    unittest.main()
