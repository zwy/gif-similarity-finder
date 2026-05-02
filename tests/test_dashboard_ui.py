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
                scrollTop: 0,
                clientHeight: 736,
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
            elements['dashboard-grid'].clientHeight = config.gridClientHeight || 736;
            if (config.virtualColumnsDataset != null) {
              elements['dashboard-grid'].dataset.virtualColumns = String(config.virtualColumnsDataset);
            }

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
              location: {
                search: config.locationSearch || '',
              },
              URLSearchParams,
              __GIF_DASHBOARD_STAGE_SHARDS__: {},
            };
            windowObject.getComputedStyle = () => ({
              gridTemplateColumns: config.gridTemplateColumns || '1fr 1fr 1fr 1fr',
              getPropertyValue: (name) => (name === 'grid-template-columns' ? (config.gridTemplateColumns || '1fr 1fr 1fr 1fr') : ''),
            });
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
              URLSearchParams,
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
            const stage1Shards = config.stage1Shards || [{ file_name: 'dashboard_stage1_000.js', items: stage1Items }];
            const stage2Shards = config.stage2Shards || [{ file_name: 'dashboard_stage2_000.js', items: stage2Items }];
            const manifestMeta = config.manifestMeta || {};
            const manifest = {
              ...(Object.keys(manifestMeta).length ? { meta: manifestMeta } : {}),
              stage1_same_source: {
                summary: { total_items: stage1Items.length, total_groups: 1, grouped_items: stage1Items.length, noise_items: 0, largest_group_size: 4 },
                shards: stage1Shards.map((shard) => ({ file_name: shard.file_name, size: shard.items.length })),
              },
              stage2_action_clusters: {
                summary: { total_items: stage2Items.length, total_groups: 1, grouped_items: stage2Items.length, noise_items: 0, largest_group_size: 4 },
                shards: stage2Shards.map((shard) => ({ file_name: shard.file_name, size: shard.items.length })),
              },
            };

            const shardMap = {};
            for (const shard of stage1Shards) {
              shardMap[`stage1_same_source:${shard.file_name}`] = shard.items;
            }
            for (const shard of stage2Shards) {
              shardMap[`stage2_action_clusters:${shard.file_name}`] = shard.items;
            }
            const loadCalls = [];

            const runtime = context.window.GifDashboard.createRuntime({
              window: context.window,
              document,
              loadScript: async (src) => {
                loadCalls.push(src);
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
              const flush = async () => {
                await Promise.resolve();
                await Promise.resolve();
              };
              const cardsForGrid = () => elements['dashboard-grid'].children.filter((child) => child.className === 'dashboard-card');
              const runActions = async () => {
                const actions = config.actions || [];
                for (const action of actions) {
                  if (action.type === 'scroll') {
                    elements['dashboard-grid'].scrollTop = action.scrollTop || 0;
                    if (elements['dashboard-grid'].listeners['scroll']) {
                      elements['dashboard-grid'].listeners['scroll']();
                      await flush();
                    }
                  } else if (action.type === 'search') {
                    elements['dashboard-search'].value = action.value || '';
                    if (elements['dashboard-search'].listeners['input']) {
                      elements['dashboard-search'].listeners['input']();
                      await flush();
                    }
                  } else if (action.type === 'hover-first-card') {
                    const cards = cardsForGrid();
                    if (cards[0] && cards[0].listeners['mouseenter']) {
                      cards[0].listeners['mouseenter']();
                    }
                  } else if (action.type === 'leave-first-card') {
                    const cards = cardsForGrid();
                    if (cards[0] && cards[0].listeners['mouseleave']) {
                      cards[0].listeners['mouseleave']();
                    }
                  } else if (action.type === 'hover-error-first-card') {
                    const cards = cardsForGrid();
                    const image = cards[0] && cards[0].children[0];
                    if (cards[0] && cards[0].listeners['mouseenter']) {
                      cards[0].listeners['mouseenter']();
                    }
                    if (image && typeof image.onerror === 'function') {
                      image.onerror();
                    }
                  } else if (action.type === 'click-first-card') {
                    const cards = cardsForGrid();
                    if (cards[0] && cards[0].listeners['click']) {
                      cards[0].listeners['click']();
                      await flush();
                    }
                  } else if (action.type === 'selected-preview-error') {
                    const selectedImage = elements['selected-preview'].children.find((child) => child.tagName === 'img');
                    if (selectedImage && typeof selectedImage.onerror === 'function') {
                      selectedImage.onerror();
                      await flush();
                    }
                  }
                }
              };

              runActions().then(() => {
                const cards = cardsForGrid();
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
                const selectedImage = elements['selected-preview'].children.find((child) => child.tagName === 'img');
                process.stdout.write(JSON.stringify({
                  cardCount: cards.length,
                  firstCardLabel: cards[0] && cards[0].children[1] ? cards[0].children[1].textContent : null,
                  filteredCount: runtime.getFilteredCount(),
                  visibleCount: runtime.getVisibleCount(),
                  hover,
                  hoverPreviewAfterError: firstImage ? firstImage.src : null,
                  selectedImageSrc: selectedImage ? selectedImage.src : null,
                  selectedPanelText: elements['selected-preview'].children.map((child) => child.textContent || '').join(' '),
                  loadCalls,
                }));
              }).catch((error) => {
                console.error(error);
                process.exit(1);
              });
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

    def test_runtime_uses_output_query_override_for_manifest_shard_and_preview_paths(self) -> None:
        runtime = self._run_runtime({"stage1Count": 3, "locationSearch": "?output=/abs/output"})
        self.assertIn("/abs/output/dashboard_manifest.js", runtime["loadCalls"])
        self.assertIn("/abs/output/dashboard_stage1_000.js", runtime["loadCalls"])
        self.assertTrue(runtime["hover"]["previewBefore"].startswith("/abs/output/previews/"))

    def test_runtime_resolves_relative_gif_paths_from_manifest_output_metadata(self) -> None:
        runtime = self._run_runtime(
            {
                "stage1Items": [
                    {
                        "id": "stage1-0",
                        "name": "stage1 0",
                        "gif_path": "clips/stage1-0.gif",
                        "preview_path": "previews/stage1-0.webp",
                        "group_id": "10",
                        "group_size": 1,
                        "is_noise": False,
                        "stage": "stage1_same_source",
                    }
                ],
                "manifestMeta": {"output_dir": "/custom/output"},
                "actions": [{"type": "click-first-card"}],
            }
        )
        self.assertEqual(runtime["hover"]["gifSrc"], "/custom/output/clips/stage1-0.gif")
        self.assertEqual(runtime["selectedImageSrc"], "/custom/output/clips/stage1-0.gif")

    def test_runtime_renders_bounded_visible_slice(self) -> None:
        runtime = self._run_runtime({"stage1Count": 200})
        self.assertGreater(runtime["visibleCount"], 0)
        self.assertLess(runtime["visibleCount"], runtime["filteredCount"])
        self.assertEqual(runtime["cardCount"], runtime["visibleCount"])

    def test_virtualization_window_advances_when_scrolling(self) -> None:
        runtime = self._run_runtime(
            {
                "stage1Count": 260,
                "actions": [{"type": "scroll", "scrollTop": 9200}],
            }
        )
        self.assertNotEqual(runtime["firstCardLabel"], "stage1 0")

    def test_virtualization_uses_runtime_grid_layout_instead_of_fixed_columns(self) -> None:
        runtime = self._run_runtime(
            {
                "stage1Count": 260,
                "gridTemplateColumns": "1fr 1fr",
                "virtualColumnsDataset": 4,
                "actions": [{"type": "scroll", "scrollTop": 1840}],
            }
        )
        self.assertEqual(runtime["firstCardLabel"], "stage1 16")

    def test_stage_shards_load_incrementally_on_demand(self) -> None:
        def shard(name: str, start: int, count: int) -> dict:
            items = [
                {
                    "id": f"stage1-{index}",
                    "name": f"stage1 {index}",
                    "gif_path": f"/stage1-{index}.gif",
                    "preview_path": f"previews/stage1-{index}.webp",
                    "group_id": "10",
                    "group_size": 4,
                    "is_noise": False,
                    "stage": "stage1_same_source",
                }
                for index in range(start, start + count)
            ]
            return {"file_name": name, "items": items}

        config = {
            "stage1Count": 120,
            "stage1Shards": [
                shard("dashboard_stage1_000.js", 0, 40),
                shard("dashboard_stage1_001.js", 40, 40),
                shard("dashboard_stage1_002.js", 80, 40),
            ],
        }
        initial = self._run_runtime(config)
        initial_stage1_loads = [src for src in initial["loadCalls"] if "dashboard_stage1_" in src]
        self.assertEqual(initial_stage1_loads, ["../output/dashboard_stage1_000.js"])

        after_scroll = self._run_runtime({**config, "actions": [{"type": "scroll", "scrollTop": 5200}]})
        post_scroll_stage1_loads = [src for src in after_scroll["loadCalls"] if "dashboard_stage1_" in src]
        self.assertGreaterEqual(len(post_scroll_stage1_loads), 2)

    def test_gif_load_failures_fall_back_to_preview(self) -> None:
        runtime = self._run_runtime(
            {
                "stage1Count": 4,
                "actions": [
                    {"type": "hover-error-first-card"},
                    {"type": "click-first-card"},
                    {"type": "selected-preview-error"},
                ],
            }
        )
        self.assertTrue(runtime["hoverPreviewAfterError"].endswith(".webp"))
        self.assertTrue(runtime["selectedImageSrc"].endswith(".webp"))
        self.assertIn("unavailable", runtime["selectedPanelText"].lower())


class DashboardReadmeDocsTest(unittest.TestCase):
    def test_readme_documents_dashboard_entry_and_not_legacy_reports(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("dashboard/index.html", readme)
        self.assertNotIn("report_stage1_same_source.html", readme)
        self.assertNotIn("report_stage2_action_clusters.html", readme)


if __name__ == "__main__":
    unittest.main()
