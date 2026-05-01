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
        # Large dataset should not eagerly pre-render one card per item in the
        # generated HTML, but should still render a small visible slice.
        total = 100
        groups = {0: [f"/tmp/{index}.gif" for index in range(total)]}
        dataset = build_report_dataset(groups, stage="stage2_action_clusters")

        html = render_report_html(dataset)

        # Ensure we have some preview cards but far fewer than total items
        card_count = html.count('class="report-card"')
        self.assertGreater(card_count, 0)
        self.assertLess(card_count, total)
        self.assertIn("renderVisibleRange", html)
        self.assertIn("filter((item) => !item.is_noise)", html)

    def test_render_report_html_wires_toolbar_controls(self) -> None:
        dataset = build_report_dataset({0: ["a.gif"], -1: ["noise.gif"]}, stage="stage1_same_source")

        html = render_report_html(dataset)

        self.assertIn("document.getElementById('report-search').addEventListener", html)
        self.assertIn("document.getElementById('report-sort').addEventListener", html)
        self.assertIn("document.getElementById('report-hide-noise').addEventListener", html)
        self.assertIn("if (hideNoise)", html)

    def test_render_report_html_renders_a_visible_preview_slice(self) -> None:
        dataset = build_report_dataset({0: ["a.gif", "b.gif"]}, stage="stage1_same_source")

        html = render_report_html(dataset)

        self.assertIn('class="report-card"', html)
        self.assertIn("a.gif", html)

    def test_render_report_html_escapes_preview_card_content(self) -> None:
        dataset = build_report_dataset({0: ['a<b&"\' .gif']}, stage="stage1_same_source")

        html = render_report_html(dataset)

        self.assertIn("&lt;b&amp;&quot;&#x27; .gif", html)
        self.assertNotIn('class="report-card">a<b&"\' .gif', html)

    def test_render_report_html_escapes_preview_paths_in_initial_slice(self) -> None:
        # The initial visible slice should not expose raw dangerous sequences
        dataset = build_report_dataset({0: ["evil</script>.gif"]}, stage="stage1_same_source")

        html = render_report_html(dataset)

        # Path with script-closing fragments must not appear raw in the HTML
        self.assertNotIn("evil</script>.gif", html)

    def test_render_report_html_stage_specific_labels_are_embedded(self) -> None:
        ds1 = build_report_dataset({0: ["a.gif"]}, stage="stage1_same_source")
        ds2 = build_report_dataset({0: ["a.gif"]}, stage="stage2_action_clusters")

        html1 = render_report_html(ds1)
        html2 = render_report_html(ds2)

        self.assertIn("stage1_same_source", html1)
        self.assertIn("stage2_action_clusters", html2)
        self.assertNotEqual(html1, html2)

    def test_render_report_html_escapes_script_closing_sequences_in_payload(self) -> None:
        dataset = build_report_dataset(
            {0: ["/tmp/evil</script><script>alert(1)</script>.gif"]},
            stage="stage2_action_clusters",
        )

        html = render_report_html(dataset)

        self.assertIn("window.__REPORT_DATA__", html)
        self.assertNotIn("</script><script>alert(1)</script>", html)

    def test_render_report_html_escapes_mixed_case_script_closing_sequences_in_payload(self) -> None:
        dataset = build_report_dataset(
            {0: ["/tmp/evil</ScRiPt><script>alert(1)</script>.gif"]},
            stage="stage2_action_clusters",
        )

        html = render_report_html(dataset)

        self.assertNotIn("</ScRiPt><script>alert(1)</script>", html)


if __name__ == "__main__":
    unittest.main()
