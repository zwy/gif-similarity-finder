# Report UI Redesign Design

## Problem

The current `report_stage1_same_source.html` and `report_stage2_action_clusters.html` outputs are simple linear HTML listings. They are acceptable for tiny runs, but they break down quickly as result size grows: the pages are visually weak, hard to scan, lack search/filter/sort behavior, and do not scale toward the project's stated 100k-GIF target.

The redesign needs to improve visual quality and browsing experience, but the primary constraint is performance at very large scale. The reports must remain fully offline-capable.

## Goals

1. Redesign Stage 1 and Stage 2 reports with a shared UI framework.
2. Keep the reports fully offline-capable with no runtime dependency on a backend service or CDN.
3. Default to a GIF-first browsing experience, not a text-only summary view.
4. Make the reports usable at very large result sizes by limiting DOM size and computation cost.
5. Preserve the current JSON outputs while upgrading HTML reports into a structured static report application.

## Non-Goals

1. Add backend search services or server-side pagination.
2. Introduce a runtime web framework.
3. Add advanced analytics dashboards in the first version.
4. Build pre-generated thumbnail pipelines in the first version.
5. Replace the existing Stage 1 or Stage 2 clustering logic.

## Recommended Approach

Use a shared offline report shell backed by structured report data and client-side virtualized rendering.

This approach keeps report generation static and portable, while moving presentation from a giant pre-rendered HTML document to a lightweight HTML shell plus structured data and targeted client-side rendering logic.

## Alternatives Considered

### 1. Summary-first expandable report

Render compact group summaries first and only show GIF grids after opening a group.

**Pros**
- Lower default render cost.
- Simple mental model for Stage 1.

**Cons**
- Conflicts with the preferred default of seeing GIFs immediately.
- Adds extra navigation friction when scanning many groups quickly.

### 2. Dashboard plus drill-down pages

Generate an overview landing page and separate drill-down views for Stage 1 and Stage 2.

**Pros**
- Clear information hierarchy.
- Good long-term extensibility.

**Cons**
- Too heavy for the first redesign.
- Adds more page transitions and more generator complexity than needed right now.

## Target Experience

Both Stage 1 and Stage 2 reports should feel like the same application:

- Shared top bar with title, high-level stats, search, and sort.
- Shared filter rail for lightweight filters and toggles.
- Shared main content area using a virtualized GIF grid.
- Shared details panel or modal for inspecting a selected group and its members.

The difference is the default semantic view:

- **Stage 1:** browse by same-source groups.
- **Stage 2:** browse by action/scene clusters.

## Report Structure

### Shared shell

The generated HTML should contain:

- Local CSS only.
- Local JavaScript only.
- A root application container.
- Embedded or linked structured report data.

The shared shell is responsible for layout, theming, rendering, filtering, sorting, and virtualization.

### Shared controls

Every report should include:

- Search input
- Sort control
- Toggle for noise/ungrouped items
- Minimum group-size filter
- Result count summary

These controls should be lightweight and operate on precomputed report metadata.

### Main grid

The default main area is a GIF-first grid view.

Requirements:

- Render only the visible slice of items plus a small overscan buffer.
- Support smooth scrolling without inserting all items into the DOM.
- Show enough metadata on each card to orient the user without opening details.

Recommended card content:

- GIF preview
- file name
- group/cluster label
- group size badge

### Details view

Selecting a card or group should open a detail surface that shows:

- Group/cluster label
- Group size
- Member list or secondary virtualized grid
- Key metadata relevant to that stage

This lets the main screen stay fast while still providing full inspection when needed.

## Stage-Specific Behavior

### Stage 1

Primary use case: inspect likely same-source matches.

Stage 1 should emphasize:

- Group size
- Clear same-source grouping
- Noise visibility toggle
- Fast confirmation of whether a group is a true duplicate/source family

### Stage 2

Primary use case: inspect semantic action/scene clusters.

Stage 2 should emphasize:

- Cluster size
- Similar-looking group previews
- Noise filtering
- Quick scanning of large clusters

## Performance Design

The redesign must explicitly optimize for the 100k-GIF target.

### Hard performance rules

1. **Do not pre-render all GIF cards into the HTML.**
2. **Do not keep all cards mounted in the DOM.**
3. **Do not perform expensive filtering or regrouping on raw DOM nodes.**
4. **Do not eagerly expand large noise groups.**

### Required strategies

- Virtualized main grid
- Structured data model separate from DOM
- Precomputed group metadata during report generation
- Progressive initial render
- On-demand detail expansion
- Default hidden or collapsed noise/ungrouped sections

### Data model

The report generator should produce a structured dataset containing:

- global summary
- report stage
- group index
- item index
- lightweight card metadata
- small preview subset per group

At minimum, each group record should include:

- group ID
- size
- noise flag
- preview item references

At minimum, each item record should include:

- file path
- file name
- group ID
- ordering keys used by the UI

## Generator Changes

The current `save_html_report()` implementation writes a single pre-rendered HTML string. That must be replaced by a data-and-template approach.

### New model

Split report generation into:

1. **Report data builder**
   - Converts raw group output into a structured UI dataset.

2. **Report template writer**
   - Writes the HTML shell, local styles, local scripts, and serialized data payload.

### Output direction

The first version should keep the existing report filenames:

- `report_stage1_same_source.html`
- `report_stage2_action_clusters.html`

The existing JSON files remain unchanged and continue to serve as machine-readable artifacts.

## Styling Approach

The reports may use a Tailwind-style design language, but they must remain fully offline-capable.

That means:

- no Tailwind CDN at runtime
- no external JS dependencies required by the browser
- if Tailwind is used, it must be compiled into local static CSS before report output

The first version can also use hand-authored local CSS if that is simpler and keeps the output lighter.

## First-Version Scope

The first implementation should include:

- shared offline report shell
- shared layout and styling system
- virtualized GIF grid
- search
- sort
- basic filters
- Stage 1 / Stage 2 shared components with different default labels and metadata emphasis
- current JSON outputs preserved

The first implementation should exclude:

- server-backed search
- pre-generated thumbnails
- advanced dashboard analytics
- multi-page navigation system
- heavy charting

## Testing Strategy

### Generator-level tests

- Structured report data shape
- HTML shell generation
- Stage 1 and Stage 2 report metadata correctness

### UI behavior tests

- Search/filter/sort state transformations
- Virtualization range calculation
- Noise toggle behavior
- Group detail open/close behavior

### Large-scale safety checks

- Generated report does not pre-render the full item list into HTML
- DOM/windowing logic is exercised with synthetic large datasets
- Large noise groups do not render eagerly by default

## Risks

1. A visually richer report could accidentally become slower if it still renders too much DOM.
2. A generic shared shell could blur the differences between Stage 1 and Stage 2 if metadata emphasis is not handled carefully.
3. Embedding too much raw data directly in one HTML file may create output-size issues if not structured carefully.

The implementation should control these risks by treating virtualization and data separation as non-negotiable constraints.

## Expected Outcome

After this redesign, both report pages should look substantially better, be easier to scan, and remain usable against very large GIF result sets. The result should feel like a lightweight offline static application rather than a raw HTML dump.
