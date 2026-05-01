import unittest

from gif_similarity_finder.report_data import build_report_dataset
from gif_similarity_finder.report_template import render_report_html


class ReportTemplateTest(unittest.TestCase):
    def test_render_report_html_outputs_shared_app_shell(self) -> None:
        dataset = build_report_dataset({0: ["a.gif", "b.gif"], -1: ["c.gif"]}, stage="stage1_same_source")

        html = render_report_html(dataset)

        self.assertIn("report-app", html)
        self.assertIn("report-search", html)
        self.assertIn("report-grid", html)
        self.assertIn("window.__REPORT_DATA__", html)
        self.assertIn('<input id="report-search"', html)
        self.assertIn('<select id="report-sort"', html)
        self.assertIn('<input id="report-hide-noise" type="checkbox"', html)

    def test_render_report_html_does_not_pre_render_every_item_card(self) -> None:
        groups = {0: [f"/tmp/{index}.gif" for index in range(100)]}
        dataset = build_report_dataset(groups, stage="stage2_action_clusters")

        html = render_report_html(dataset)

        self.assertNotIn('class="gif-card"', html)
        self.assertIn("renderVisibleRange", html)
        self.assertIn("filter((item) => !item.is_noise)", html)

    def test_render_report_html_escapes_script_closing_sequences_in_payload(self) -> None:
        dataset = build_report_dataset(
            {0: ["/tmp/evil</script><script>alert(1)</script>.gif"]},
            stage="stage2_action_clusters",
        )

        html = render_report_html(dataset)

        self.assertIn("window.__REPORT_DATA__", html)
        self.assertNotIn("</script><script>alert(1)</script>", html)


if __name__ == "__main__":
    unittest.main()
