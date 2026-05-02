# Output Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split output data from presentation, stop writing HTML into `output/`, and ship a single Tailwind-based dashboard that reads fixed output artifacts and scales to large GIF datasets with preview-first browsing.

**Architecture:** Keep the pipeline as the producer of stable artifacts under a fixed output directory, add dashboard-oriented manifest/shard/preview artifacts alongside the existing clustering data, and move presentation into a single static `dashboard/index.html` entry point. The dashboard loads a small manifest first, loads stage shards on demand, renders only the visible card window, and swaps previews to real GIFs only on hover or explicit selection.

**Tech Stack:** Python 3, unittest, Pillow, NumPy, plain browser JavaScript, HTML, Tailwind CDN

---

## File Structure

### Existing files to modify

- `gif_similarity.py` — resolve the default output directory relative to the repository instead of the caller's current working directory.
- `gif_similarity_finder/pipeline.py` — replace HTML report generation with dashboard data generation and preview emission.
- `gif_similarity_finder/artifacts.py` — keep generic JSON/cache/index/UMAP writers and remove report-shell-specific code paths.
- `tests/test_pipeline.py` — cover output-path resolution and pipeline orchestration around dashboard artifacts.
- `tests/test_artifacts.py` — keep generic artifact tests and remove HTML report assertions.
- `README.md` — document the fixed output layout and dashboard usage.

### New files to create

- `gif_similarity_finder/dashboard_data.py` — dataclasses and builders for dashboard summaries, records, shards, and manifest payloads.
- `gif_similarity_finder/dashboard_artifacts.py` — manifest/shard writers plus preview-image generation helpers.
- `dashboard/index.html` — single dashboard entry point.
- `dashboard/dashboard.js` — dashboard runtime for loading data, tab switching, filtering, virtualization, hover playback, and selected-item inspection.
- `tests/test_dashboard_data.py` — unit tests for manifest/stage/shard builders.
- `tests/test_dashboard_artifacts.py` — unit tests for preview generation and `.js` data writers.
- `tests/test_dashboard_ui.py` — runtime tests for the dashboard JavaScript using the existing Node-backed DOM stub pattern.

### Files to delete after replacement is complete

- `gif_similarity_finder/report_data.py`
- `gif_similarity_finder/report_template.py`
- `tests/test_report_data.py`
- `tests/test_report_template.py`

---

### Task 1: Lock the output-path contract

**Files:**
- Modify: `gif_similarity.py`
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing CLI tests**

```python
class CliTest(unittest.TestCase):
    def test_resolve_output_dir_defaults_to_repo_output(self) -> None:
        expected = Path(gif_similarity.__file__).resolve().parent / "output"
        self.assertEqual(gif_similarity.resolve_output_dir(None), expected)

    def test_main_uses_repo_local_output_when_cli_omits_output(self) -> None:
        args = Namespace(
            input="input",
            output=None,
            frames=8,
            hash_thresh=10,
            min_cluster=3,
            batch_size=32,
            device="auto",
            skip_stage1=False,
            skip_stage2=True,
        )

        with mock.patch("gif_similarity.parse_args", return_value=args), mock.patch(
            "gif_similarity.run_pipeline"
        ) as run_pipeline_mock:
            gif_similarity.main()

        config = run_pipeline_mock.call_args.args[0]
        self.assertEqual(config.output_dir, Path(gif_similarity.__file__).resolve().parent / "output")
```

- [ ] **Step 2: Run the targeted CLI tests and watch them fail**

Run: `python3 -m unittest tests.test_pipeline.CliTest -v`

Expected: FAIL with `AttributeError: module 'gif_similarity' has no attribute 'resolve_output_dir'` and a mismatch because `output` is currently expected as the literal CLI string.

- [ ] **Step 3: Add `resolve_output_dir()` and wire `main()` through it**

```python
def resolve_output_dir(output_arg: str | None) -> Path:
    if output_arg:
        return Path(output_arg)
    return Path(__file__).resolve().parent / "output"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GIF Similarity Finder — same-source + action/scene clustering")
    parser.add_argument("--input", required=True, help="Folder containing GIF files")
    parser.add_argument("--output", default=None, help="Output directory")
    parser.add_argument("--frames", type=int, default=8, help="Frames to sample per GIF for CLIP")
    parser.add_argument("--hash_thresh", type=int, default=10, help="Hamming distance threshold for same-source detection")
    parser.add_argument("--min_cluster", type=int, default=3, help="Minimum cluster size for HDBSCAN")
    parser.add_argument("--batch_size", type=int, default=32, help="CLIP batch size")
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda", "mps"], help="Compute device")
    parser.add_argument("--skip_stage1", action="store_true", help="Skip same-source detection")
    parser.add_argument("--skip_stage2", action="store_true", help="Skip CLIP clustering")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = PipelineConfig(
        input_dir=Path(args.input),
        output_dir=resolve_output_dir(args.output),
        frames=args.frames,
        hash_threshold=args.hash_thresh,
        min_cluster_size=args.min_cluster,
        batch_size=args.batch_size,
        device=args.device,
        skip_stage1=args.skip_stage1,
        skip_stage2=args.skip_stage2,
    )
```

- [ ] **Step 4: Re-run the CLI tests**

Run: `python3 -m unittest tests.test_pipeline.CliTest -v`

Expected: PASS for both `CliTest` cases, including the new repo-local default.

- [ ] **Step 5: Commit the output-path contract**

```bash
git add gif_similarity.py tests/test_pipeline.py
git commit -m "refactor: lock output path resolution" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 2: Introduce dashboard data models and shard builders

**Files:**
- Create: `gif_similarity_finder/dashboard_data.py`
- Create: `tests/test_dashboard_data.py`

- [ ] **Step 1: Write the failing dashboard-data tests**

```python
class DashboardDataTest(unittest.TestCase):
    def test_build_dashboard_stage_summarizes_groups_and_items(self) -> None:
        stage = build_dashboard_stage(
            stage_key="stage2_action_clusters",
            groups={0: ["/tmp/a.gif", "/tmp/b.gif"], -1: ["/tmp/noise.gif"]},
            preview_dir_name="previews",
        )

        self.assertEqual(stage.summary.total_items, 3)
        self.assertEqual(stage.summary.total_groups, 1)
        self.assertEqual(stage.summary.noise_items, 1)
        self.assertEqual(stage.items[0].preview_path, "previews/" + stage.items[0].id + ".webp")

    def test_split_stage_items_creates_deterministic_shards(self) -> None:
        stage = build_dashboard_stage(
            stage_key="stage1_same_source",
            groups={0: [f"/tmp/{index}.gif" for index in range(5)]},
            preview_dir_name="previews",
        )

        shards = split_stage_items(stage, shard_size=2)

        self.assertEqual([shard.file_name for shard in shards], [
            "dashboard_stage1_same_source_000.js",
            "dashboard_stage1_same_source_001.js",
            "dashboard_stage1_same_source_002.js",
        ])
        self.assertEqual([len(shard.items) for shard in shards], [2, 2, 1])
```

- [ ] **Step 2: Run the dashboard-data tests to verify they fail**

Run: `python3 -m unittest tests.test_dashboard_data -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'gif_similarity_finder.dashboard_data'`.

- [ ] **Step 3: Implement stage/summary/item/shard builders**

```python
@dataclass(slots=True)
class DashboardSummary:
    total_items: int
    total_groups: int
    grouped_items: int
    noise_items: int
    largest_group_size: int


@dataclass(slots=True)
class DashboardItem:
    id: str
    name: str
    gif_path: str
    preview_path: str
    group_id: str
    group_size: int
    is_noise: bool
    stage: str


@dataclass(slots=True)
class DashboardStage:
    stage_key: str
    summary: DashboardSummary
    items: list[DashboardItem]


@dataclass(slots=True)
class DashboardShard:
    file_name: str
    items: list[DashboardItem]


def stable_item_id(gif_path: Path) -> str:
    return hashlib.sha1(str(gif_path).encode("utf-8")).hexdigest()[:16]


def build_dashboard_stage(stage_key: str, groups: dict[int | str, list[str]], preview_dir_name: str) -> DashboardStage:
    ordered_groups = sorted(groups.items(), key=lambda item: (int(item[0]) == -1, -len(item[1]), int(item[0])))
    items: list[DashboardItem] = []
    grouped_items = 0
    noise_items = 0
    largest_group_size = 0

    for raw_group_id, paths in ordered_groups:
        is_noise = int(raw_group_id) == -1
        group_size = len(paths)
        grouped_items += 0 if is_noise else group_size
        noise_items += group_size if is_noise else 0
        largest_group_size = max(largest_group_size, 0 if is_noise else group_size)
        for raw_path in paths:
            gif_path = Path(raw_path)
            item_id = stable_item_id(gif_path)
            items.append(
                DashboardItem(
                    id=item_id,
                    name=gif_path.name,
                    gif_path=str(gif_path),
                    preview_path=f"{preview_dir_name}/{item_id}.webp",
                    group_id=str(raw_group_id),
                    group_size=group_size,
                    is_noise=is_noise,
                    stage=stage_key,
                )
            )

    return DashboardStage(
        stage_key=stage_key,
        summary=DashboardSummary(
            total_items=len(items),
            total_groups=sum(1 for group_id, _paths in ordered_groups if int(group_id) != -1),
            grouped_items=grouped_items,
            noise_items=noise_items,
            largest_group_size=largest_group_size,
        ),
        items=items,
    )


def split_stage_items(stage: DashboardStage, shard_size: int) -> list[DashboardShard]:
    shards: list[DashboardShard] = []
    for index in range(0, len(stage.items), shard_size):
        shard_number = index // shard_size
        shards.append(
            DashboardShard(
                file_name=f"dashboard_{stage.stage_key}_{shard_number:03d}.js",
                items=stage.items[index : index + shard_size],
            )
        )
    return shards


def build_dashboard_manifest(output_dir: Path, stages: list[DashboardStage]) -> dict[str, object]:
    return {
        "outputDir": str(output_dir),
        "stages": {
            stage.stage_key: {
                "summary": asdict(stage.summary),
                "shards": [shard.file_name for shard in split_stage_items(stage, shard_size=500)],
            }
            for stage in stages
        },
    }
```

- [ ] **Step 4: Re-run the dashboard-data tests**

Run: `python3 -m unittest tests.test_dashboard_data -v`

Expected: PASS for the stage summary and shard naming assertions.

- [ ] **Step 5: Commit the dashboard data layer**

```bash
git add gif_similarity_finder/dashboard_data.py tests/test_dashboard_data.py
git commit -m "feat: add dashboard data builders" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 3: Add preview generation and dashboard artifact writers

**Files:**
- Create: `gif_similarity_finder/dashboard_artifacts.py`
- Create: `tests/test_dashboard_artifacts.py`
- Modify: `gif_similarity_finder/artifacts.py`
- Modify: `tests/test_artifacts.py`

- [ ] **Step 1: Write the failing artifact tests**

```python
class DashboardArtifactsTest(unittest.TestCase):
    def test_save_preview_image_writes_webp_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            gif_path = Path(tmp_dir) / "sample.gif"
            preview_path = Path(tmp_dir) / "previews" / "sample.webp"
            Image.new("RGBA", (16, 16), "red").save(gif_path, save_all=True)

            result = save_preview_image(gif_path, preview_path)

            self.assertEqual(result, preview_path)
            self.assertTrue(preview_path.exists())

    def test_save_dashboard_manifest_writes_global_assignment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "dashboard_manifest.js"
            manifest = {"stages": {"stage1_same_source": {"shards": ["dashboard_stage1_same_source_000.js"]}}}

            save_dashboard_manifest(target, manifest)

            content = target.read_text(encoding="utf-8")
            self.assertIn("window.__GIF_DASHBOARD_MANIFEST__", content)
            self.assertIn("dashboard_stage1_same_source_000.js", content)
```

- [ ] **Step 2: Run the dashboard artifact tests**

Run: `python3 -m unittest tests.test_dashboard_artifacts tests.test_artifacts -v`

Expected: FAIL because `save_preview_image` and `save_dashboard_manifest` do not exist yet, while the old HTML-report assertions still describe obsolete behavior.

- [ ] **Step 3: Implement preview and manifest writers, and remove HTML helpers from generic artifacts**

```python
def save_preview_image(gif_path: Path, preview_path: Path, size: tuple[int, int] = (240, 240)) -> Path | None:
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(gif_path) as image:
        frame = image.convert("RGBA")
        frame.thumbnail(size)
        frame.save(preview_path, format="WEBP", quality=80)
    return preview_path


def save_dashboard_manifest(path: Path, manifest: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))
    path.write_text(f"window.__GIF_DASHBOARD_MANIFEST__ = {payload};\n", encoding="utf-8")
    return path


def save_dashboard_stage_shard(path: Path, stage_key: str, items: list[dict[str, object]]) -> Path:
    payload = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
    path.write_text(
        f"window.__GIF_DASHBOARD_STAGE_SHARDS__ = window.__GIF_DASHBOARD_STAGE_SHARDS__ || {{}};\n"
        f"window.__GIF_DASHBOARD_STAGE_SHARDS__['{stage_key}:{path.name}'] = {payload};\n",
        encoding="utf-8",
    )
    return path
```

- [ ] **Step 4: Re-run the artifact tests**

Run: `python3 -m unittest tests.test_dashboard_artifacts tests.test_artifacts -v`

Expected: PASS for preview generation and `.js` payload writing, with no remaining assertions about `report_*.html`.

- [ ] **Step 5: Commit the dashboard artifact writers**

```bash
git add gif_similarity_finder/dashboard_artifacts.py gif_similarity_finder/artifacts.py tests/test_dashboard_artifacts.py tests/test_artifacts.py
git commit -m "feat: add dashboard artifact writers" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 4: Rewire the pipeline to generate dashboard data instead of HTML reports

**Files:**
- Modify: `gif_similarity_finder/pipeline.py`
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing pipeline orchestration tests**

```python
class PipelineOrchestrationTest(unittest.TestCase):
    def test_run_pipeline_writes_dashboard_artifacts_and_never_calls_html_report_writer(self) -> None:
        gif_paths = [Path("a.gif"), Path("b.gif")]
        stage1_result = Stage1Result(groups={0: ["a.gif"]}, hashed_paths=gif_paths, match_count=1)
        stage2_result = Stage2Result(
            groups={1: ["b.gif"]},
            valid_paths=gif_paths,
            embeddings=np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
            labels=np.array([1, 1], dtype=np.int64),
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.make_config(tmp_dir)
            with mock.patch("gif_similarity_finder.pipeline.collect_gifs", return_value=gif_paths), mock.patch(
                "gif_similarity_finder.pipeline.run_stage1", return_value=stage1_result
            ), mock.patch(
                "gif_similarity_finder.pipeline.load_embedding_cache", return_value=None
            ), mock.patch(
                "gif_similarity_finder.pipeline.run_stage2", return_value=stage2_result
            ), mock.patch("gif_similarity_finder.pipeline.save_group_json") as save_group_json_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_dashboard_manifest"
            ) as save_dashboard_manifest_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_dashboard_stage_shard"
            ) as save_dashboard_stage_shard_mock, mock.patch(
                "gif_similarity_finder.pipeline.save_preview_image"
            ) as save_preview_image_mock:
                run_pipeline(config)

        save_group_json_mock.assert_has_calls([
            mock.call(config.output_dir / "stage1_same_source_groups.json", stage1_result.groups),
            mock.call(config.output_dir / "stage2_action_clusters.json", stage2_result.groups),
        ])
        save_dashboard_manifest_mock.assert_called_once()
        self.assertGreater(save_dashboard_stage_shard_mock.call_count, 0)
        self.assertEqual(save_preview_image_mock.call_count, len(gif_paths))
```

- [ ] **Step 2: Run the pipeline tests and confirm the old report expectations fail**

Run: `python3 -m unittest tests.test_pipeline -v`

Expected: FAIL because `pipeline.py` still imports and calls `save_html_report`, while the new dashboard writer mocks are never reached.

- [ ] **Step 3: Replace HTML report generation with dashboard stage/build/write calls**

```python
def run_pipeline(config: PipelineConfig) -> None:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    gif_paths = collect_gifs(config.input_dir)
    if not gif_paths:
        raise SystemExit("No GIF files found. Check --input path.")

    stage_groups: dict[str, dict[int, list[str]]] = {}

    if not config.skip_stage1:
        stage1_result = run_stage1(gif_paths, hash_threshold=config.hash_threshold)
        stage_groups["stage1_same_source"] = stage1_result.groups
        save_group_json(config.output_dir / "stage1_same_source_groups.json", stage1_result.groups)

    if not config.skip_stage2:
        cache_path = config.output_dir / "clip_embeddings_cache.npz"
        cache_data = load_embedding_cache(cache_path)
        stage2_result = run_stage2(
            gif_paths=gif_paths,
            n_frames=config.frames,
            batch_size=config.batch_size,
            min_cluster_size=config.min_cluster_size,
            device=config.device,
            cache_data=cache_data,
        )
        stage_groups["stage2_action_clusters"] = stage2_result.groups
        save_group_json(config.output_dir / "stage2_action_clusters.json", stage2_result.groups)
        if stage2_result.valid_paths:
            save_embedding_cache(
                cache_path,
                EmbeddingCacheData(paths=stage2_result.valid_paths, embeddings=stage2_result.embeddings),
            )
            save_hnsw_index(config.output_dir / "hnsw.index", stage2_result.embeddings)
            save_umap_visualization(config.output_dir, stage2_result.embeddings, stage2_result.labels)

    dashboard_stages = [
        build_dashboard_stage(stage_key=stage_key, groups=groups, preview_dir_name="previews")
        for stage_key, groups in stage_groups.items()
    ]
    for gif_path in gif_paths:
        preview_path = config.output_dir / "previews" / f"{stable_item_id(gif_path)}.webp"
        save_preview_image(gif_path, preview_path)
    for stage in dashboard_stages:
        for shard in split_stage_items(stage, shard_size=500):
            save_dashboard_stage_shard(config.output_dir / shard.file_name, stage.stage_key, [asdict(item) for item in shard.items])
    save_dashboard_manifest(config.output_dir / "dashboard_manifest.js", build_dashboard_manifest(config.output_dir, dashboard_stages))
```

- [ ] **Step 4: Re-run the pipeline tests**

Run: `python3 -m unittest tests.test_pipeline -v`

Expected: PASS with assertions proving fixed artifact paths are still used and no report HTML writer remains in the orchestration flow.

- [ ] **Step 5: Commit the pipeline rewiring**

```bash
git add gif_similarity_finder/pipeline.py tests/test_pipeline.py
git commit -m "refactor: emit dashboard data from pipeline" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 5: Build the single dashboard entry point and runtime

**Files:**
- Create: `dashboard/index.html`
- Create: `dashboard/dashboard.js`
- Create: `tests/test_dashboard_ui.py`

- [ ] **Step 1: Write the failing dashboard UI runtime tests**

```python
class DashboardUiTest(unittest.TestCase):
    def test_dashboard_shell_contains_tabs_and_detail_panel(self) -> None:
        html = Path("dashboard/index.html").read_text(encoding="utf-8")
        self.assertIn('data-stage-tab="stage1_same_source"', html)
        self.assertIn('data-stage-tab="stage2_action_clusters"', html)
        self.assertIn('id="selected-preview"', html)

    def test_dashboard_runtime_swaps_preview_to_gif_on_hover(self) -> None:
        state = self._run_dashboard_runtime(
            manifest={"stages": {"stage1_same_source": {"shards": ["dashboard_stage1_same_source_000.js"]}}},
            shards={"stage1_same_source:dashboard_stage1_same_source_000.js": [{
                "id": "abc",
                "name": "a.gif",
                "gif_path": "/tmp/a.gif",
                "preview_path": "previews/abc.webp",
                "group_id": "0",
                "group_size": 1,
                "is_noise": False,
                "stage": "stage1_same_source",
            }]},
        )

        self.assertEqual(state["cardImageSrcBeforeHover"], "../output/previews/abc.webp")
        self.assertEqual(state["cardImageSrcAfterHover"], "/tmp/a.gif")
        self.assertEqual(state["cardImageSrcAfterLeave"], "../output/previews/abc.webp")
```

- [ ] **Step 2: Run the dashboard UI tests**

Run: `python3 -m unittest tests.test_dashboard_ui -v`

Expected: FAIL because `dashboard/index.html`, `dashboard/dashboard.js`, and the Node-backed runtime harness do not exist yet.

- [ ] **Step 3: Create the HTML shell and runtime**

```html
<!-- dashboard/index.html -->
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>GIF Similarity Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
  </head>
  <body class="bg-slate-950 text-slate-100">
    <div class="flex min-h-screen">
      <aside class="w-80 border-r border-slate-800 p-4">
        <input id="search-input" class="w-full rounded bg-slate-900 px-3 py-2" placeholder="Search GIFs">
        <label class="mt-4 flex items-center gap-2"><input id="hide-noise" type="checkbox" checked>Hide noise</label>
      </aside>
      <main class="flex-1 p-4">
        <div class="mb-4 flex gap-2">
          <button data-stage-tab="stage1_same_source">Stage 1</button>
          <button data-stage-tab="stage2_action_clusters">Stage 2</button>
        </div>
        <section id="summary-cards"></section>
        <section id="grid-scroll" class="relative mt-4 h-[70vh] overflow-auto">
          <div id="grid-spacer"></div>
          <div id="card-grid" class="absolute inset-x-0 top-0 grid grid-cols-4 gap-3"></div>
        </section>
      </main>
      <aside id="selected-preview" class="w-96 border-l border-slate-800 p-4"></aside>
    </div>
    <script src="../output/dashboard_manifest.js"></script>
    <script src="./dashboard.js"></script>
  </body>
</html>
```

```javascript
// dashboard/dashboard.js
const state = { visibleStart: 0, visibleEnd: 24 };
const cardGrid = document.getElementById("card-grid");

function previewSrc(item) {
  return `../output/${item.preview_path}`;
}

function gifSrc(item) {
  return item.gif_path;
}

function attachHoverPlayback(card, item) {
  const image = card.querySelector("img");
  card.addEventListener("mouseenter", () => {
    image.src = gifSrc(item);
  });
  card.addEventListener("mouseleave", () => {
    image.src = previewSrc(item);
  });
}

function renderCard(item) {
  const card = document.createElement("button");
  const image = document.createElement("img");
  image.src = previewSrc(item);
  card.appendChild(image);
  attachHoverPlayback(card, item);
  return card;
}

function renderVirtualGrid(items) {
  const visibleItems = items.slice(state.visibleStart, state.visibleEnd);
  cardGrid.replaceChildren(...visibleItems.map(renderCard));
}
```

- [ ] **Step 4: Re-run the dashboard UI tests**

Run: `python3 -m unittest tests.test_dashboard_ui -v`

Expected: PASS for shell structure, tab bootstrapping, virtualization boundaries, and hover swap behavior.

- [ ] **Step 5: Commit the dashboard UI**

```bash
git add dashboard/index.html dashboard/dashboard.js tests/test_dashboard_ui.py
git commit -m "feat: add static dashboard ui" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 6: Remove obsolete report-shell code and refresh docs

**Files:**
- Delete: `gif_similarity_finder/report_data.py`
- Delete: `gif_similarity_finder/report_template.py`
- Delete: `tests/test_report_data.py`
- Delete: `tests/test_report_template.py`
- Modify: `README.md`

- [ ] **Step 1: Write the failing documentation/cleanup assertions**

```python
class ReadmeContractTest(unittest.TestCase):
    def test_readme_documents_dashboard_entry_and_no_report_html(self) -> None:
        readme = Path("README.md").read_text(encoding="utf-8")
        self.assertIn("dashboard/index.html", readme)
        self.assertNotIn("report_stage1_same_source.html", readme)
        self.assertNotIn("report_stage2_action_clusters.html", readme)
```

- [ ] **Step 2: Run the README contract test**

Run: `python3 -m unittest tests.test_dashboard_ui.ReadmeContractTest -v`

Expected: FAIL because the README still documents `report_*.html` outputs and the old report-shell tests still exist.

- [ ] **Step 3: Delete the old report modules/tests and update the README**

```markdown
output/
├── stage1_same_source_groups.json
├── stage2_action_clusters.json
├── clip_embeddings_cache.npz
├── hnsw.index
├── umap_clusters.png
├── dashboard_manifest.js
├── dashboard_stage1_same_source_000.js
├── dashboard_stage2_action_clusters_000.js
└── previews/

打开方式：
A. 先生成数据：`python gif_similarity.py --input /path/to/gifs`
B. 再打开页面：`open dashboard/index.html`
```

- [ ] **Step 4: Re-run the cleanup and documentation tests**

Run: `python3 -m unittest tests.test_dashboard_ui.ReadmeContractTest -v`

Expected: PASS, with README describing `dashboard/index.html` and no references to report HTML outputs.

- [ ] **Step 5: Commit the cleanup and docs refresh**

```bash
git add README.md dashboard/index.html dashboard/dashboard.js tests/test_dashboard_ui.py tests/test_artifacts.py tests/test_pipeline.py tests/test_dashboard_data.py tests/test_dashboard_artifacts.py
git rm gif_similarity_finder/report_data.py gif_similarity_finder/report_template.py tests/test_report_data.py tests/test_report_template.py
git commit -m "docs: document dashboard output flow" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 7: Run the full verification pass

**Files:**
- Modify: none
- Test: `tests/test_pipeline.py`
- Test: `tests/test_artifacts.py`
- Test: `tests/test_dashboard_data.py`
- Test: `tests/test_dashboard_artifacts.py`
- Test: `tests/test_dashboard_ui.py`

- [ ] **Step 1: Run the focused dashboard-related suites**

Run: `python3 -m unittest tests.test_pipeline tests.test_artifacts tests.test_dashboard_data tests.test_dashboard_artifacts tests.test_dashboard_ui -v`

Expected: PASS across pipeline, artifact, data-builder, and dashboard-runtime coverage.

- [ ] **Step 2: Run the full test suite**

Run: `python3 -m unittest discover -s tests -v`

Expected: PASS with the old report-shell suites removed and the new dashboard suites included.

- [ ] **Step 3: Inspect the git diff before the final commit**

Run: `git --no-pager diff --stat HEAD~6..HEAD`

Expected: shows changes in CLI path resolution, dashboard data/artifact builders, pipeline rewiring, dashboard UI, README, and test replacements.

- [ ] **Step 4: Commit the verification checkpoint**

```bash
git commit --allow-empty -m "test: verify dashboard redesign" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

- [ ] **Step 5: Hand off for execution**

Run: `git --no-pager log --oneline -7`

Expected: shows the sequence of task commits ready for either subagent-driven or inline execution.
