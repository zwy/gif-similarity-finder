# Output/Data Split and Dashboard Redesign

## Problem

The current reporting flow mixes data artifacts and presentation artifacts inside `output/`, generates multiple HTML report files, and embeds report payloads directly into those HTML files. That makes the output directory harder to reuse, makes repeated runs create presentation-oriented artifacts in the data directory, and does not scale well to very large GIF libraries where users need to visually inspect results without loading every GIF at once.

The project needs a clearer separation:

- `output/` should be the fixed data/artifact directory.
- The HTML presentation layer should live outside `output/`.
- The dashboard should be a single HTML entry point, not multiple report pages.
- The dashboard must let users visually inspect GIF results at large scale (up to ~100k GIFs) without eagerly loading all animated images.

## Goals

- Respect `--output` when provided; otherwise default to the repository-local `output/`.
- Keep `output/` free of HTML files.
- Use fixed artifact paths instead of per-run report copies.
- Introduce a single dashboard entry point under `dashboard/`.
- Render Stage 1 and Stage 2 in one dashboard with tabbed navigation.
- Make image-based browsing practical for very large datasets by using lightweight previews and on-demand GIF playback.

## Non-Goals

- Turning the dashboard into a local web application with a required backend service.
- Preserving the old multi-HTML report output flow.
- Autoplaying large numbers of visible GIFs simultaneously.

## Proposed Structure

### Data layer

The pipeline continues to write all reusable artifacts to a fixed output directory:

- If `--output` is provided, use that directory exactly.
- If `--output` is omitted, use `<repo>/output/`.

`output/` remains the canonical artifact location and no longer stores any HTML files.

### Presentation layer

The dashboard moves into a dedicated `dashboard/` directory with a single HTML entry point:

- `dashboard/index.html`

That entry point reads the fixed artifacts from `output/` and is responsible only for presentation and interaction.

## Output Directory Layout

The output directory should use stable filenames and overwrite/update them on rerun instead of creating historical presentation copies.

Core artifacts:

- `stage1_same_source_groups.json`
- `stage2_action_clusters.json`
- `clip_embeddings_cache.npz`
- `hnsw.index`
- `umap_clusters.png`

Dashboard-specific data artifacts:

- `dashboard_manifest.js`
- `dashboard_stage1_*.js`
- `dashboard_stage2_*.js`
- `previews/`

Notes:

- `dashboard_manifest.js` is a data script, not presentation HTML. Its role is to let a static dashboard load structured data from a fixed path even when opened directly from disk, where `fetch()` on JSON is not consistently reliable.
- Stage data is split into deterministic, fixed-path script shards so the dashboard does not need to preload all records up front.
- `previews/` stores lightweight preview assets generated from each GIF for browsing performance.

## Dashboard Data Model

The dashboard should not consume the raw clustering JSON directly as its only source. In addition to the existing algorithm-oriented artifacts, the pipeline should emit dashboard-oriented data with explicit metadata.

### Manifest contents

`dashboard_manifest.js` should define a single global payload describing:

- dataset/output metadata
- generation timestamp
- available stages
- summary metrics per stage
- shard file list per stage
- preview configuration
- optional warnings about missing data

### Record shape

Each dashboard item record should include at least:

- `id` — stable unique identifier
- `name`
- `gif_path`
- `preview_path`
- `group_id`
- `group_size`
- `is_noise`
- `stage`
- `width` / `height` when available

This gives the UI enough information to render, filter, sort, and preview items without inferring metadata from raw cluster JSON at runtime.

### Sharding strategy

Stage detail data should be emitted in fixed shards rather than one giant payload:

- shard by stage first
- then split into deterministic chunk files within that stage

The dashboard should only load:

- the manifest initially
- the active stage's required shard(s)
- additional shards only when the UI needs them

This keeps initial startup predictable even when the dataset is very large.

## Preview and GIF Loading Strategy

The dashboard must be image-first, not filename-first, but it also cannot load 100k animated GIFs.

### Default browsing mode

Each card displays a lightweight generated preview from `output/previews/`.

Recommended preview format:

- static first-frame image such as WebP or JPG

Reasoning:

- much smaller transfer/decode cost than full GIFs
- good enough for dense visual scanning
- works well with virtualized grid rendering

### Hover behavior

When a card becomes hovered:

- replace the preview with the original GIF for that card only

When hover ends:

- revert back to the lightweight preview
- release the full GIF source so many animated images do not remain active in memory

This preserves quick visual inspection while keeping decode pressure bounded to a small number of actively inspected cards.

### Selected item behavior

Hover is useful for quick inspection, but the UI should also support a stable selected state. Clicking a card should pin it in a detail panel where users can inspect metadata and optionally keep the real GIF visible without relying on hover alone.

## Dashboard UI Design

The dashboard follows the approved "dataset-first" layout.

### Layout

Left sidebar:

- output/dataset status
- last generated timestamp
- search input
- sort controls
- hide-noise toggle
- group-size filtering

Main content:

- top summary cards (`total items`, `groups`, `noise`, `largest group`)
- tab switcher for `Stage 1` and `Stage 2`
- virtualized result grid

Optional supporting panel:

- selection detail panel on the right or bottom
- full path
- group metadata
- fixed real-GIF preview for the selected item

### Shared rendering model

Stage 1 and Stage 2 should share the same card/grid renderer and filtering shell. The primary thing that changes across tabs is the data source and stage-specific labels, not the rendering architecture.

### State behavior

- remember the last active tab with `localStorage`
- keep search/sort/noise filtering stage-aware
- avoid resetting the entire application state on minor interactions

## Performance Strategy

The dashboard should explicitly optimize for very large datasets.

### Rendering

- use a virtualized list/grid
- render only the visible range plus a small overscan buffer
- never mount all cards into the DOM

### Image loading

- preview images load lazily for visible cards only
- full GIFs load only on hover or explicit selection
- full GIF playback is bounded to the user's current focus

### Data loading

- load manifest first
- load stage shards on demand
- avoid a design that requires parsing all item records before the first usable screen appears

## Error Handling and Empty States

The dashboard should degrade explicitly rather than silently.

- If required files are missing from `output/`, show a visible warning banner describing which artifacts are missing.
- If preview assets are missing, render a placeholder card state and keep the item browsable by metadata.
- If the original GIF path is invalid, the hover/selected preview should show an "unavailable" state for that item instead of breaking the grid.
- If one stage has no data, its tab should render a clear empty state while the other stage remains usable.

## Testing and Verification Scope

### Pipeline/output behavior

- verify default output path remains `<repo>/output/` when `--output` is not provided
- verify custom `--output` is honored exactly
- verify no HTML report files are written to `output/`
- verify reruns update fixed artifact paths instead of creating new report copies

### Artifact generation

- verify dashboard manifest and stage shards are generated at expected fixed paths
- verify preview assets are generated and referenced correctly
- verify missing optional artifacts still produce a coherent dashboard state

### Dashboard behavior

- verify there is a single HTML entry point under `dashboard/`
- verify Stage 1 / Stage 2 tab switching
- verify search, sorting, and hide-noise behavior
- verify hover swaps preview image to the real GIF and back
- verify selection detail view can hold a stable real-GIF preview

### Large dataset safety

- verify the initial DOM does not contain all result cards
- verify image loading remains limited to visible cards and active hover/selection states

## Implementation Notes

- Tailwind should be used for the dashboard presentation layer.
- The dashboard remains presentation-only and does not write artifacts back into `output/`.
- Existing raw JSON artifacts should remain available for algorithmic/debugging use, while dashboard-oriented data is generated alongside them.

## Recommended Direction

Implement the redesign as a data/presentation split:

1. stabilize `output/` as the fixed artifact directory
2. remove HTML generation from pipeline outputs
3. emit dashboard-specific manifest/shard/preview artifacts into `output/`
4. build a single `dashboard/index.html` with a Tailwind-based dataset-first layout
5. use virtualization plus preview-first browsing so the UI stays useful at 100k GIF scale
