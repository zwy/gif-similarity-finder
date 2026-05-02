import unittest
from pathlib import Path
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
        self.assertIn("stage1", manifest)
        self.assertEqual(manifest["stage1"]["summary"]["total_items"], 3)
        self.assertEqual(len(manifest["stage1"]["shards"]), 1)
        shard = manifest["stage1"]["shards"][0]
        self.assertEqual(shard["file_name"], "dashboard_stage1_000.js")
        self.assertEqual(shard["size"], 3)
        self.assertEqual(shard["path"], str(Path("out") / shard["file_name"]))

if __name__ == '__main__':
    unittest.main()
