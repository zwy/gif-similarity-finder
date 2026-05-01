import unittest

from gif_similarity_finder.report_data import build_report_dataset


class ReportDataTest(unittest.TestCase):
    def test_build_report_dataset_creates_summary_groups_and_items(self) -> None:
        groups = {
            0: ["a.gif", "b.gif", "c.gif"],
            1: ["d.gif", "e.gif"],
            -1: ["z.gif"],
        }

        dataset = build_report_dataset(groups, stage="stage1_same_source")

        self.assertEqual(dataset.summary.stage, "stage1_same_source")
        self.assertEqual(dataset.summary.total_groups, 3)
        self.assertEqual(dataset.summary.grouped_items, 5)
        self.assertEqual(dataset.summary.noise_items, 1)
        self.assertEqual(dataset.summary.largest_group_size, 3)
        self.assertEqual(dataset.groups[0].preview_items, ["a.gif", "b.gif", "c.gif"])
        self.assertEqual(dataset.items[0].group_size, 3)

    def test_build_report_dataset_marks_noise_items(self) -> None:
        groups = {-1: ["noise-a.gif", "noise-b.gif"]}
        dataset = build_report_dataset(groups, stage="stage2_action_clusters")

        self.assertTrue(all(item.is_noise for item in dataset.items))
        self.assertTrue(dataset.groups[0].is_noise)


if __name__ == "__main__":
    unittest.main()
