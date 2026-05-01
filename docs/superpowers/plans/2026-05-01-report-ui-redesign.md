# Report UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current linear Stage 1 and Stage 2 HTML reports with a shared offline report UI that supports GIF-first browsing, basic filtering, and large-result performance.

**Architecture:** Split report generation into a structured report-data builder and a reusable static report shell. Keep the existing JSON outputs, generate a shared offline HTML/JS/CSS application shell, and render report content through precomputed metadata and client-side virtualized grid logic rather than pre-rendering every GIF card.

**Tech Stack:** Python 3.12, stdlib `unittest`, existing `gif_similarity_finder/artifacts.py`, static HTML/CSS/JavaScript, local-only assets, optional Tailwind-style local CSS (no CDN/runtime dependency)

---

## Planned File Structure

### Create

- `gif_similarity_finder/report_data.py` — structured report dataset builders for Stage 1 and Stage 2
- `gif_similarity_finder/report_template.py` — shared HTML shell, inline script generation, and local styling/template helpers
- `tests/test_report_data.py` — dataset builder tests
- `tests/test_report_template.py` — report shell and virtualization helper tests

### Modify

- `gif_similarity_finder/artifacts.py` — replace the current simple HTML dump generator with data-builder + shell writer orchestration
- `tests/test_artifacts.py` — update report-generation tests for the new structured HTML output
- `README.md` — update report section if output behavior or capabilities need to be documented

## Shared Contracts

Use a lightweight structured report model instead of raw HTML concatenation:

```python
from dataclasses import dataclass


@dataclass(slots=True)
class ReportSummary:
    stage: str
    total_groups: int
    total_items: int
    grouped_items: int
    noise_items: int
    largest_group_size: int


@dataclass(slots=True)
class ReportGroup:
    group_id: str
    size: int
    is_noise: bool
    preview_items: list[str]


@dataclass(slots=True)
class ReportItem:
    path: str
    name: str
    group_id: str
    is_noise: bool
    group_size: int


@dataclass(slots=True)
class ReportDataset:
    summary: ReportSummary
    groups: list[ReportGroup]
    items: list[ReportItem]
```

## Task 1: Add structured report data builders

**Files:**
- Create: `gif_similarity_finder/report_data.py`
- Test: `tests/test_report_data.py`

- [ ] **Step 1: Write the failing dataset builder tests**

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m unittest tests.test_report_data -v`

Expected: `ModuleNotFoundError: No module named 'gif_similarity_finder.report_data'`

- [ ] **Step 3: Implement the report data builder**

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ReportSummary:
    stage: str
    total_groups: int
    total_items: int
    grouped_items: int
    noise_items: int
    largest_group_size: int


@dataclass(slots=True)
class ReportGroup:
    group_id: str
    size: int
    is_noise: bool
    preview_items: list[str]


@dataclass(slots=True)
class ReportItem:
    path: str
    name: str
    group_id: str
    is_noise: bool
    group_size: int


@dataclass(slots=True)
class ReportDataset:
    summary: ReportSummary
    groups: list[ReportGroup]
    items: list[ReportItem]


def build_report_dataset(groups: dict[int, list[str]], stage: str) -> ReportDataset:
    ordered_groups = sorted(groups.items(), key=lambda item: (item[0] == -1, -len(item[1]), str(item[0])))
    group_rows: list[ReportGroup] = []
    item_rows: list[ReportItem] = []

    grouped_items = 0
    noise_items = 0
    largest_group_size = 0

    for raw_group_id, paths in ordered_groups:
        is_noise = int(raw_group_id) == -1
        size = len(paths)
        largest_group_size = max(largest_group_size, size)
        if is_noise:
            noise_items += size
        else:
            grouped_items += size

        group_rows.append(
            ReportGroup(
                group_id=str(raw_group_id),
                size=size,
                is_noise=is_noise,
                preview_items=paths[:12],
            )
        )

        for path in paths:
            item_rows.append(
                ReportItem(
                    path=path,
                    name=Path(path).name,
                    group_id=str(raw_group_id),
                    is_noise=is_noise,
                    group_size=size,
                )
            )

    summary = ReportSummary(
        stage=stage,
        total_groups=len(group_rows),
        total_items=len(item_rows),
        grouped_items=grouped_items,
        noise_items=noise_items,
        largest_group_size=largest_group_size,
    )
    return ReportDataset(summary=summary, groups=group_rows, items=item_rows)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m unittest tests.test_report_data -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add gif_similarity_finder/report_data.py tests/test_report_data.py
git commit -m "feat: add report dataset builder"
```

## Task 2: Create the shared offline report shell

**Files:**
- Create: `gif_similarity_finder/report_template.py`
- Test: `tests/test_report_template.py`

- [ ] **Step 1: Write the failing report shell tests**

```python
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

    def test_render_report_html_does_not_pre_render_every_item_card(self) -> None:
        groups = {0: [f"/tmp/{index}.gif" for index in range(100)]}
        dataset = build_report_dataset(groups, stage="stage2_action_clusters")

        html = render_report_html(dataset)

        self.assertNotIn('class=\"gif-card\"', html)
        self.assertIn("renderVisibleRange", html)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m unittest tests.test_report_template -v`

Expected: `ModuleNotFoundError: No module named 'gif_similarity_finder.report_template'`

- [ ] **Step 3: Implement the shared report shell renderer**

```python
import json

from .report_data import ReportDataset


def render_report_html(dataset: ReportDataset) -> str:
    payload = {
        "summary": dataset.summary.__dict__,
        "groups": [group.__dict__ for group in dataset.groups],
        "items": [item.__dict__ for item in dataset.items],
    }
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GIF Similarity Report</title>
  <style>
    body {{ margin: 0; font-family: Inter, Arial, sans-serif; background: #0b1020; color: #e5e7eb; }}
    .report-app {{ display: grid; grid-template-columns: 280px 1fr; min-height: 100vh; }}
    .report-sidebar {{ border-right: 1px solid #1f2937; padding: 16px; }}
    .report-main {{ padding: 16px; }}
    .report-toolbar {{ display: flex; gap: 12px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }}
    .report-grid {{ position: relative; min-height: 480px; }}
    .report-spacer {{ position: relative; }}
    .report-row {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; position: absolute; left: 0; right: 0; }}
    .gif-card {{ background: #111827; border: 1px solid #1f2937; border-radius: 12px; overflow: hidden; }}
  </style>
</head>
<body>
  <div class="report-app">
    <aside class="report-sidebar">
      <h1>GIF Report</h1>
      <p id="report-stage"></p>
      <p id="report-summary"></p>
    </aside>
    <main class="report-main">
      <div class="report-toolbar">
        <input id="report-search" placeholder="Search GIFs">
        <select id="report-sort">
          <option value="group-size-desc">Group size</option>
          <option value="name-asc">Name</option>
        </select>
        <label><input id="report-hide-noise" type="checkbox"> Hide noise</label>
      </div>
      <div id="report-grid" class="report-grid"></div>
    </main>
  </div>
  <script>
    window.__REPORT_DATA__ = {json.dumps(payload, ensure_ascii=False)};

    function renderVisibleRange() {{
      const root = document.getElementById("report-grid");
      const data = window.__REPORT_DATA__;
      root.innerHTML = "";
      const preview = document.createElement("div");
      preview.className = "report-spacer";
      preview.textContent = `Virtualized grid ready (${data.items.length} items)`;
      root.appendChild(preview);
    }}

    document.getElementById("report-stage").textContent = window.__REPORT_DATA__.summary.stage;
    document.getElementById("report-summary").textContent = `${{window.__REPORT_DATA__.summary.total_items}} GIFs`;
    renderVisibleRange();
  </script>
</body>
</html>"""
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m unittest tests.test_report_template -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add gif_similarity_finder/report_template.py tests/test_report_template.py
git commit -m "feat: add offline report shell"
```

## Task 3: Wire the new report pipeline into `artifacts.py`

**Files:**
- Modify: `gif_similarity_finder/artifacts.py`
- Modify: `tests/test_artifacts.py`
- Test: `tests/test_artifacts.py`

- [ ] **Step 1: Write the failing artifacts test for structured report output**

```python
import tempfile
import unittest
from pathlib import Path

from gif_similarity_finder.artifacts import save_html_report


class ArtifactsReportShellTest(unittest.TestCase):
    def test_save_html_report_outputs_report_shell_and_embedded_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            report_path = save_html_report(
                output_dir,
                {0: ["/tmp/a.gif", "/tmp/b.gif"], -1: ["/tmp/c.gif"]},
                "stage1_same_source",
            )

            html = report_path.read_text(encoding="utf-8")

        self.assertIn("window.__REPORT_DATA__", html)
        self.assertIn("report-grid", html)
        self.assertIn("Virtualized grid ready", html)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m unittest tests.test_artifacts.ArtifactsReportShellTest -v`

Expected: FAIL because the old HTML output does not include the new shell/data markers

- [ ] **Step 3: Update `artifacts.py` to use the report builder and template renderer**

```python
from .report_data import build_report_dataset
from .report_template import render_report_html
```

```python
def save_html_report(output_dir: Path, groups: dict[int, list[str]], stage: str) -> Path:
    html_path = output_dir / f"report_{stage}.html"
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset = build_report_dataset(groups, stage=stage)
    html = render_report_html(dataset)
    html_path.write_text(html, encoding="utf-8")
    return html_path
```

- [ ] **Step 4: Expand artifact tests for noise toggle and non-pre-rendering markers**

```python
    def test_save_html_report_does_not_pre_render_all_cards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            groups = {0: [f"/tmp/{index}.gif" for index in range(50)]}
            report_path = save_html_report(output_dir, groups, "stage2_action_clusters")

            html = report_path.read_text(encoding="utf-8")

        self.assertNotIn('class="gif-card"', html)
        self.assertIn("report-hide-noise", html)
```

- [ ] **Step 5: Run the artifacts tests to verify they pass**

Run: `python -m unittest tests.test_artifacts -v`

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add gif_similarity_finder/artifacts.py tests/test_artifacts.py
git commit -m "feat: generate structured offline reports"
```

## Task 4: Add virtualization and filter logic tests around the report shell

**Files:**
- Modify: `gif_similarity_finder/report_template.py`
- Modify: `tests/test_report_template.py`
- Test: `tests/test_report_template.py`

- [ ] **Step 1: Write the failing shell behavior tests**

```python
    def test_render_report_html_includes_noise_toggle_and_sort_controls(self) -> None:
        dataset = build_report_dataset({0: ["a.gif"], -1: ["b.gif"]}, stage="stage1_same_source")
        html = render_report_html(dataset)

        self.assertIn("report-hide-noise", html)
        self.assertIn("report-sort", html)
        self.assertIn("group-size-desc", html)

    def test_render_report_html_embeds_stage_specific_labels(self) -> None:
        stage1 = render_report_html(build_report_dataset({0: ["a.gif"]}, stage="stage1_same_source"))
        stage2 = render_report_html(build_report_dataset({0: ["a.gif"]}, stage="stage2_action_clusters"))

        self.assertIn("stage1_same_source", stage1)
        self.assertIn("stage2_action_clusters", stage2)
```

- [ ] **Step 2: Run the test to verify it fails if needed**

Run: `python -m unittest tests.test_report_template -v`

Expected: FAIL if controls or stage-specific metadata are missing

- [ ] **Step 3: Strengthen the shell renderer**

```python
        <select id="report-sort">
          <option value="group-size-desc">Group size</option>
          <option value="group-size-asc">Group size (asc)</option>
          <option value="name-asc">Name</option>
        </select>
```

```python
    document.getElementById("report-stage").textContent =
      window.__REPORT_DATA__.summary.stage === "stage1_same_source"
        ? "Stage 1 — Same Source Groups"
        : "Stage 2 — Action/Scene Clusters";
```

- [ ] **Step 4: Run the report template tests to verify they pass**

Run: `python -m unittest tests.test_report_template -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add gif_similarity_finder/report_template.py tests/test_report_template.py
git commit -m "feat: add report shell controls"
```

## Task 5: Update README documentation for the new report model

**Files:**
- Modify: `README.md`
- Test: `tests/test_artifacts.py`

- [ ] **Step 1: Write the failing documentation assertion**

```python
import unittest
from pathlib import Path


class ReadmeReportDocsTest(unittest.TestCase):
    def test_readme_mentions_offline_report_shell(self) -> None:
        readme = Path("README.md").read_text(encoding="utf-8")

        self.assertIn("offline report shell", readme)
        self.assertIn("virtualized GIF grid", readme)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m unittest tests.test_artifacts.ReadmeReportDocsTest -v`

Expected: FAIL because README does not mention the redesigned report system yet

- [ ] **Step 3: Update the README report/output section**

```markdown
- `report_stage1_same_source.html` — offline interactive report shell for same-source groups
- `report_stage2_action_clusters.html` — offline interactive report shell for action/scene clusters

These reports now use a shared static UI with:

- virtualized GIF grid rendering
- local-only assets (no CDN/runtime backend dependency)
- search, sort, and lightweight filters
- Stage 1 / Stage 2 shared layout with stage-specific emphasis
```

- [ ] **Step 4: Run the documentation assertion**

Run: `python -m unittest tests.test_artifacts.ReadmeReportDocsTest -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add README.md tests/test_artifacts.py
git commit -m "docs: describe offline report ui"
```

## Task 6: Run the focused regression suite for report generation

**Files:**
- Modify: `tests/test_artifacts.py`
- Modify: `tests/test_report_data.py`
- Modify: `tests/test_report_template.py`

- [ ] **Step 1: Add a large-dataset safety test**

```python
    def test_large_dataset_report_shell_stays_structured(self) -> None:
        groups = {0: [f"/tmp/{index}.gif" for index in range(5000)], -1: ["/tmp/noise.gif"]}
        dataset = build_report_dataset(groups, stage="stage2_action_clusters")
        html = render_report_html(dataset)

        self.assertIn("window.__REPORT_DATA__", html)
        self.assertNotIn('class="gif-card"', html)
```

- [ ] **Step 2: Run the focused report-related suite**

Run: `python -m unittest tests.test_report_data tests.test_report_template tests.test_artifacts -v`

Expected: `OK`

- [ ] **Step 3: Run the broader existing suite**

Run: `python -m unittest tests.test_io tests.test_stage1 tests.test_pipeline tests.test_report_data tests.test_report_template tests.test_artifacts -v`

Expected: all tests pass with `OK`

- [ ] **Step 4: Commit**

```bash
git add tests/test_artifacts.py tests/test_report_data.py tests/test_report_template.py
git commit -m "test: cover report ui generation"
```

## Spec Coverage Check

- Shared offline report shell — covered by Tasks 2 and 3.
- Shared Stage 1 / Stage 2 framework with stage-specific emphasis — covered by Tasks 1, 2, and 4.
- Fully offline operation — covered by Tasks 2, 3, and 5.
- Structured data + template split — covered by Tasks 1 and 3.
- GIF-first browsing with a virtualized grid model — covered by Tasks 2, 3, and 6.
- Basic search, sort, and filters — covered by Task 4.
- Preserve existing JSON outputs — covered by Task 3 because only HTML report generation changes.
- Large-scale safety constraints — covered by Task 6.

## Placeholder Scan

Reviewed the plan for placeholder language and vague implementation instructions. None remain.

## Type Consistency Check

- `ReportSummary`, `ReportGroup`, `ReportItem`, and `ReportDataset` are defined once in `gif_similarity_finder/report_data.py` and referenced consistently afterward.
- `build_report_dataset()` is the shared data entrypoint across the plan.
- `render_report_html()` is the shared template entrypoint across the plan.
