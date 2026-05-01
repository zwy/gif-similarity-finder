import json
import os
import re
import shutil
import subprocess
import unittest

from gif_similarity_finder.report_data import build_report_dataset
from gif_similarity_finder.report_template import (
    INITIAL_PREVIEW_LIMIT,
    VISIBLE_SLICE_LIMIT,
    render_report_html,
)


class ReportTemplateTest(unittest.TestCase):
    maxDiff = None

    def _render_runtime_state(
        self,
        html: str,
        *,
        search: str = "",
        sort: str = "group-size-desc",
        hide_noise: bool = True,
        ready_state: str = "complete",
        fire_dom_content_loaded: bool = False,
    ) -> dict:
        if shutil.which("node") is None:
            self.skipTest("node is required for report runtime tests")
        script_match = re.search(r"<script>(.*)</script>", html, re.DOTALL)
        self.assertIsNotNone(script_match)
        node_script = """
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync(0, 'utf8');
const scriptMatch = html.match(/<script>([\\s\\S]*)<\\/script>/);
if (!scriptMatch) {
  throw new Error('report script not found');
}

const config = JSON.parse(process.env.REPORT_CONFIG || '{}');
const initialCardCount = (html.match(/class="report-card"/g) || []).length;

function createElement(id = null) {
  const element = {
    id,
    value: '',
    checked: false,
    textContent: '',
    className: '',
    style: {},
    children: [],
    listeners: {},
    appendChild(child) {
      this.children.push(child);
      return child;
    },
    addEventListener(type, handler) {
      this.listeners[type] = handler;
    },
  };
  let innerHTMLValue = '';
  Object.defineProperty(element, 'innerHTML', {
    get() {
      return innerHTMLValue;
    },
    set(value) {
      innerHTMLValue = value;
      this.children = [];
    },
  });
  return element;
}

const elements = {
  'report-grid': createElement('report-grid'),
  'report-search': createElement('report-search'),
  'report-sort': createElement('report-sort'),
  'report-hide-noise': createElement('report-hide-noise'),
  'report-stage': createElement('report-stage'),
  'report-summary': createElement('report-summary'),
};

elements['report-search'].value = config.search || '';
elements['report-sort'].value = config.sort || 'group-size-desc';
elements['report-hide-noise'].checked = config.hideNoise !== false;
for (let index = 0; index < initialCardCount; index += 1) {
  const card = createElement('article');
  card.className = 'report-card';
  elements['report-grid'].children.push(card);
}

const document = {
  readyState: config.readyState || 'complete',
  listeners: {},
  getElementById(id) {
    if (!elements[id]) {
      elements[id] = createElement(id);
    }
    return elements[id];
  },
  createElement(tagName) {
    return createElement(tagName);
  },
  addEventListener(type, handler) {
    this.listeners[type] = handler;
  },
};

const context = {
  window: {},
  document,
  console,
  Math,
  JSON,
  setTimeout,
  clearTimeout,
};
context.window = context;
vm.createContext(context);
vm.runInContext(scriptMatch[1], context);
if (config.fireDOMContentLoaded && document.listeners['DOMContentLoaded']) {
  document.listeners['DOMContentLoaded']();
}

const cards = elements['report-grid'].children.filter((child) => child.className === 'report-card');
const spacers = elements['report-grid'].children.filter((child) => child.className === 'spacer');

process.stdout.write(JSON.stringify({
  stageText: elements['report-stage'].textContent,
  summaryText: elements['report-summary'].textContent,
  gridCardCount: cards.length,
  spacerCount: spacers.length,
  paths: cards.map((card) => card.children[2]?.textContent || ''),
  metas: cards.map((card) => card.children[1]?.textContent || ''),
  listenerTypes: {
    search: Object.keys(elements['report-search'].listeners),
    sort: Object.keys(elements['report-sort'].listeners),
    hideNoise: Object.keys(elements['report-hide-noise'].listeners),
  },
  documentListenerTypes: Object.keys(document.listeners),
}));
"""
        result = subprocess.run(
            ["node", "-e", node_script],
            input=html,
            text=True,
            capture_output=True,
            check=True,
            env={
                **os.environ,
                "REPORT_CONFIG": json.dumps(
                    {
                        "search": search,
                        "sort": sort,
                        "hideNoise": hide_noise,
                        "readyState": ready_state,
                        "fireDOMContentLoaded": fire_dom_content_loaded,
                    }
                ),
            },
        )
        return json.loads(result.stdout)

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

        # Ensure we have a bounded preview slice rather than nearly all items.
        card_count = html.count('class="report-card"')
        self.assertGreater(card_count, 0)
        self.assertLess(card_count, total)
        self.assertLessEqual(card_count, INITIAL_PREVIEW_LIMIT)

        runtime = self._render_runtime_state(html)
        self.assertGreater(runtime["gridCardCount"], 0)
        self.assertLess(runtime["gridCardCount"], total)
        self.assertLessEqual(runtime["gridCardCount"], VISIBLE_SLICE_LIMIT)
        self.assertEqual(runtime["spacerCount"], 1)

    def test_render_report_html_wires_toolbar_controls(self) -> None:
        dataset = build_report_dataset({0: ["b.gif", "a.gif"], -1: ["noise.gif"]}, stage="stage1_same_source")

        html = render_report_html(dataset)
        runtime = self._render_runtime_state(html)
        runtime_with_noise = self._render_runtime_state(html, hide_noise=False)
        runtime_search = self._render_runtime_state(html, search="b")
        runtime_sorted = self._render_runtime_state(html, sort="name-asc", hide_noise=False)

        self.assertIn('<input id="report-hide-noise" type="checkbox" checked>', html)
        self.assertEqual(runtime["listenerTypes"]["search"], ["input"])
        self.assertEqual(runtime["listenerTypes"]["sort"], ["change"])
        self.assertEqual(runtime["listenerTypes"]["hideNoise"], ["change"])
        self.assertNotIn("noise.gif", runtime["paths"])
        self.assertIn("noise.gif", runtime_with_noise["paths"])
        self.assertEqual(runtime_search["paths"], ["b.gif"])
        self.assertEqual(runtime_sorted["paths"][0], "a.gif")

    def test_render_report_html_shows_noise_fallback_when_dataset_is_all_noise(self) -> None:
        dataset = build_report_dataset({-1: ["noise-a.gif", "noise-b.gif"]}, stage="stage2_action_clusters")

        html = render_report_html(dataset)
        runtime = self._render_runtime_state(html)

        self.assertIn('class="report-card"', html)
        self.assertIn("noise-a.gif", html)
        self.assertEqual(runtime["gridCardCount"], 2)
        self.assertEqual(runtime["spacerCount"], 1)

    def test_render_report_html_renders_a_visible_preview_slice(self) -> None:
        dataset = build_report_dataset({0: ["a.gif", "b.gif"]}, stage="stage1_same_source")

        html = render_report_html(dataset)

        self.assertIn('class="report-card"', html)
        self.assertIn("a.gif", html)

    def test_render_report_html_auto_renders_after_dom_content_loaded(self) -> None:
        dataset = build_report_dataset({0: ["a.gif", "b.gif"]}, stage="stage1_same_source")

        html = render_report_html(dataset)
        runtime = self._render_runtime_state(
            html,
            ready_state="loading",
            fire_dom_content_loaded=True,
        )

        self.assertIn("DOMContentLoaded", runtime["documentListenerTypes"])
        self.assertGreater(runtime["gridCardCount"], 0)
        self.assertEqual(runtime["stageText"], "Same-source groups")

    def test_render_report_html_escapes_preview_card_content(self) -> None:
        dataset = build_report_dataset({0: ['a<b&"\' .gif']}, stage="stage1_same_source")

        html = render_report_html(dataset)

        self.assertIn("&lt;b&amp;&quot;&#x27; .gif", html)
        self.assertNotIn('class="report-card">a<b&"\' .gif', html)

    def test_render_report_html_escapes_preview_paths_in_initial_slice(self) -> None:
        # The initial visible slice should expose a safe, escaped preview path.
        dataset = build_report_dataset({0: ["/tmp/evil</script>.gif"]}, stage="stage1_same_source")

        html = render_report_html(dataset)

        self.assertIn("/tmp/evil&lt;/script&gt;.gif", html)
        self.assertNotIn("/tmp/evil</script>.gif", html)

    def test_render_report_html_stage_specific_labels_are_embedded(self) -> None:
        ds1 = build_report_dataset({0: ["a.gif"]}, stage="stage1_same_source")
        ds2 = build_report_dataset({0: ["a.gif"]}, stage="stage2_action_clusters")

        html1 = render_report_html(ds1)
        html2 = render_report_html(ds2)
        runtime1 = self._render_runtime_state(html1)
        runtime2 = self._render_runtime_state(html2)

        self.assertIn("Same-source groups", html1)
        self.assertIn("Action clusters", html2)
        self.assertIn('<p id="report-stage-label" data-stage-key="stage1_same_source"></p>', html1)
        self.assertIn('<p id="report-stage-label" data-stage-key="stage2_action_clusters"></p>', html2)
        self.assertIn("Source group 0", html1)
        self.assertIn("Cluster 0", html2)
        self.assertEqual(runtime1["stageText"], "Same-source groups")
        self.assertEqual(runtime2["stageText"], "Action clusters")
        self.assertEqual(runtime1["metas"][0], "Source group 0 · 1 items")
        self.assertEqual(runtime2["metas"][0], "Cluster 0 · 1 items")
        self.assertNotIn("Action clusters", html1)
        self.assertNotIn("Same-source groups", html2)

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
