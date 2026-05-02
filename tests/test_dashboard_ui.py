import json
import os
import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = ROOT / "dashboard" / "index.html"
JS_PATH = ROOT / "dashboard" / "dashboard.js"


class DashboardUiTest(unittest.TestCase):
    maxDiff = None

    def _run_runtime(self, config: dict) -> dict:
        if shutil.which("node") is None:
            self.skipTest("node is required for dashboard runtime tests")
        script = textwrap.dedent(
            """
            const fs = require('fs');
            const vm = require('vm');

            const config = JSON.parse(process.env.DASHBOARD_TEST_CONFIG || '{}');
            const runtimeSource = fs.readFileSync(process.env.DASHBOARD_JS_PATH, 'utf8');

            function createElement(id = null, tagName = 'div') {
              const element = {
                id,
                tagName,
                value: '',
                checked: false,
                textContent: '',
                className: '',
                style: {},
                dataset: {},
                attributes: {},
                children: [],
                listeners: {},
                appendChild(child) { this.children.push(child); return child; },
                addEventListener(type, handler) { this.listeners[type] = handler; },
                setAttribute(name, value) { this.attributes[name] = String(value); },
                getAttribute(name) { return this.attributes[name] || null; },
              };
              let innerHTMLValue = '';
              Object.defineProperty(element, 'innerHTML', {
                get() { return innerHTMLValue; },
                set(value) { innerHTMLValue = value; this.children = []; },
              });
              return element;
            }

            const elements = {
              'dashboard-search': createElement('dashboard-search', 'input'),
              'dashboard-hide-noise': createElement('dashboard-hide-noise', 'input'),
              'dashboard-summary': createElement('dashboard-summary', 'div'),
              'dashboard-grid': createElement('dashboard-grid', 'div'),
              'selected-preview': createElement('selected-preview', 'aside'),
              'stage-tab-stage1_same_source': createElement('stage-tab-stage1_same_source', 'button'),
              'stage-tab-stage2_action_clusters': createElement('stage-tab-stage2_action_clusters', 'button'),
            };

            elements['dashboard-hide-noise'].checked = config.hideNoise !== false;
            elements['dashboard-search'].value = config.search || '';

            const document = {
              readyState: 'complete',
              listeners: {},
              head: createElement('head', 'head'),
              getElementById(id) {
                if (!elements[id]) elements[id] = createElement(id);
                return elements[id];
              },
              createElement(tagName) {
                return createElement(null, tagName);
              },
              addEventListener(type, handler) {
                this.listeners[type] = handler;
              },
            };

            const windowObject = {
              console,
              document,
              __GIF_DASHBOARD_STAGE_SHARDS__: {},
            };
            windowObject.window = windowObject;

            const context = {
              window: windowObject,
              document,
              console,
              JSON,
              Math,
              Promise,
              setTimeout,
              clearTimeout,
            };
            context.globalThis = context.window;
            vm.createContext(context);
            vm.runInContext(runtimeSource, context);

            const stage1Count = config.stage1Count || 0;
            const stage2Count = config.stage2Count || 0;
            const makeItems = (prefix, count, includeNoise = false) => {
              const items = [];
              for (let i = 0; i < count; i += 1) {
                items.push({
                  id: `${prefix}-${i}`,
                  name: `${prefix} ${i}`,
                  gif_path: `/${prefix}-${i}.gif`,
                  preview_path: `previews/${prefix}-${i}.webp`,
                  group_id: includeNoise && i === 0 ? '-1' : '10',
                  group_size: 4,
                  is_noise: includeNoise && i === 0,
                  stage: prefix === 'stage1' ? 'stage1_same_source' : 'stage2_action_clusters',
                });
              }
              return items;
            };

            const stage1Items = config.stage1Items || makeItems('stage1', stage1Count, config.includeNoise);
            const stage2Items = config.stage2Items || makeItems('stage2', stage2Count, false);
            const manifest = {
              stage1_same_source: {
                summary: { total_items: stage1Items.length, total_groups: 1, grouped_items: stage1Items.length, noise_items: 0, largest_group_size: 4 },
                shards: [{ file_name: 'dashboard_stage1_000.js', size: stage1Items.length }],
              },
              stage2_action_clusters: {
                summary: { total_items: stage2Items.length, total_groups: 1, grouped_items: stage2Items.length, noise_items: 0, largest_group_size: 4 },
                shards: [{ file_name: 'dashboard_stage2_000.js', size: stage2Items.length }],
              },
            };

            const shardMap = {
              'stage1_same_source:dashboard_stage1_000.js': stage1Items,
              'stage2_action_clusters:dashboard_stage2_000.js': stage2Items,
            };

            const runtime = context.window.GifDashboard.createRuntime({
              window: context.window,
              document,
              loadScript: async (src) => {
                if (src.includes('dashboard_manifest.js')) {
                  context.window.__GIF_DASHBOARD_MANIFEST__ = manifest;
                  return;
                }
                const fileName = src.split('/').pop();
                for (const key of Object.keys(shardMap)) {
                  if (key.endsWith(`:${fileName}`)) {
                    context.window.__GIF_DASHBOARD_STAGE_SHARDS__[key] = shardMap[key];
                    return;
                  }
                }
                throw new Error(`Unknown script ${src}`);
              },
            });

            runtime.init().then(() => {
              const cards = elements['dashboard-grid'].children.filter((child) => child.className === 'dashboard-card');
              const firstImage = cards[0] ? cards[0].children[0] : null;
              let hover = null;
              if (cards[0] && cards[0].listeners['mouseenter'] && cards[0].listeners['mouseleave']) {
                const previewBefore = firstImage.src;
                cards[0].listeners['mouseenter']();
                const gifSrc = firstImage.src;
                cards[0].listeners['mouseleave']();
                const previewAfter = firstImage.src;
                hover = { previewBefore, gifSrc, previewAfter };
              }
              process.stdout.write(JSON.stringify({
                cardCount: cards.length,
                filteredCount: runtime.getFilteredCount(),
                visibleCount: runtime.getVisibleCount(),
                hover,
                selectedPanelText: elements['selected-preview'].textContent,
              }));
            }).catch((error) => {
              console.error(error);
              process.exit(1);
            });
            """
        )
        result = subprocess.run(
            ["node", "-e", script],
            text=True,
            capture_output=True,
            check=True,
            env={**os.environ, "DASHBOARD_TEST_CONFIG": json.dumps(config), "DASHBOARD_JS_PATH": str(JS_PATH)},
        )
        return json.loads(result.stdout)

    def test_shell_contains_required_structure(self) -> None:
        html = HTML_PATH.read_text(encoding="utf-8")
        self.assertNotIn("../output/dashboard_manifest.js", html)
        self.assertIn('id="dashboard-search"', html)
        self.assertIn('id="dashboard-hide-noise"', html)
        self.assertIn('id="dashboard-summary"', html)
        self.assertIn('id="dashboard-grid"', html)
        self.assertIn('id="stage-tab-stage1_same_source"', html)
        self.assertIn('id="stage-tab-stage2_action_clusters"', html)
        self.assertIn('id="selected-preview"', html)

    def test_runtime_swaps_preview_and_gif_on_hover(self) -> None:
        runtime = self._run_runtime({"stage1Count": 3})
        self.assertIsNotNone(runtime["hover"])
        self.assertTrue(runtime["hover"]["previewBefore"].endswith(".webp"))
        self.assertTrue(runtime["hover"]["gifSrc"].endswith(".gif"))
        self.assertEqual(runtime["hover"]["previewBefore"], runtime["hover"]["previewAfter"])

    def test_runtime_renders_bounded_visible_slice(self) -> None:
        runtime = self._run_runtime({"stage1Count": 200})
        self.assertGreater(runtime["visibleCount"], 0)
        self.assertLess(runtime["visibleCount"], runtime["filteredCount"])
        self.assertEqual(runtime["cardCount"], runtime["visibleCount"])


if __name__ == "__main__":
    unittest.main()
