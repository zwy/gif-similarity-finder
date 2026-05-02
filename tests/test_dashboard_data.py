import unittest
from pathlib import Path
from gif_similarity_finder import dashboard_data as dd

class TestDashboardData(unittest.TestCase):
    def test_build_dashboard_stage_summary_and_items(self):
        groups = {
            "g1": ["/gifs/a.gif", "/gifs/b.gif"],
            "g2": ["/gifs/c.gif"],
            "g3": ["/gifs/d.gif", "/gifs/e.gif", "/gifs/f.gif"],
        }
        stage = dd.build_dashboard_stage("stage1", groups, preview_dir_name="previews")
        self.assertEqual(stage.stage_key, "stage1")
        # summary checks
        self.assertEqual(stage.summary.total_items, 6)
        self.assertEqual(stage.summary.total_groups, 3)
        self.assertEqual(stage.summary.grouped_items, 5)
        self.assertEqual(stage.summary.noise_items, 1)
        self.assertEqual(stage.summary.largest_group_size, 3)
        # items checks
        ids = {item.id for item in stage.items}
        self.assertEqual(len(ids), 6)
        for item in stage.items:
            # name should be file stem
            self.assertIn(item.name, ["a", "b", "c", "d", "e", "f"])
            # preview path ends with stable id + .png and uses preview_dir_name
            self.assertTrue(item.preview_path.startswith("previews/"))
            self.assertTrue(item.preview_path.endswith(".png"))

    def test_stable_item_id_is_deterministic(self):
        p = Path("/gifs/a.gif")
        id1 = dd.stable_item_id(p)
        id2 = dd.stable_item_id(p)
        self.assertEqual(id1, id2)
        self.assertEqual(len(id1), 16)

    def test_split_stage_items_shards(self):
        groups = {"g1": [f"/gifs/{i}.gif" for i in range(5)]}
        stage = dd.build_dashboard_stage("s", groups, preview_dir_name="previews")
        shards = dd.split_stage_items(stage, shard_size=2)
        # expect 3 shards: 2,2,1
        self.assertEqual([len(s.items) for s in shards], [2,2,1])
        # filenames deterministic and include stage key
        expected_names = ["s-shard-000.json", "s-shard-001.json", "s-shard-002.json"]
        self.assertEqual([s.file_name for s in shards], expected_names)

if __name__ == '__main__':
    unittest.main()
