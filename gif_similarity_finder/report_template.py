from dataclasses import asdict
from html import escape
import json

from gif_similarity_finder.report_data import ReportDataset

INITIAL_PREVIEW_LIMIT = 12
VISIBLE_SLICE_LIMIT = 24


def render_report_html(dataset: ReportDataset) -> str:
    """Render a lightweight offline HTML shell for the report.

    The output must embed the report data as JSON in window.__REPORT_DATA__ and
    provide a minimal virtualized grid. Do not pre-render one card per item.
    """
    # Safely convert dataclasses (including slots=True) to primitives
    payload = asdict(dataset)
    payload_json = json.dumps(payload).replace("</", "<\\/")
    stage_labels = {
        "stage1_same_source": "Same-source groups",
        "stage2_action_clusters": "Action clusters",
    }
    card_group_labels = {
        "stage1_same_source": "Source group",
        "stage2_action_clusters": "Cluster",
    }
    stage_label = stage_labels.get(dataset.summary.stage, dataset.summary.stage)
    card_group_label = card_group_labels.get(dataset.summary.stage, "Group")
    initial_items = [item for item in payload["items"] if not item["is_noise"]][:INITIAL_PREVIEW_LIMIT]
    initial_cards = "".join(
        (
            '<article class="report-card">'
            f'<div class="report-card-name">{escape(item["name"])}</div>'
            f'<div class="report-card-meta">{escape(card_group_label)} {escape(item["group_id"])} · {item["group_size"]} items</div>'
            f'<div class="report-card-path">{escape(item["path"])}</div>'
            "</article>"
        )
        for item in initial_items
    )

    html = f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>GIF Similarity Report</title>
  <style>
    /* Minimal styles for the offline shell */
    #report-app {{ font-family: sans-serif; }}
    #report-sidebar {{ width: 240px; float: left; border-right: 1px solid #ddd; padding: 8px; box-sizing: border-box; }}
    #report-main {{ margin-left: 250px; padding: 8px; }}
    #report-toolbar {{ margin-bottom: 8px; }}
    #report-grid {{ display: grid; gap: 8px; position: relative; min-height: 200px; background: #f9f9f9; }}
    .spacer {{ width: 100%; height: 100px; background: transparent; }}
    .report-card {{ border: 1px solid #ddd; background: #fff; padding: 8px; }}
    .report-card-name {{ font-weight: 600; }}
    .report-card-meta {{ color: #666; font-size: 12px; }}
    .report-card-path {{ color: #666; font-size: 12px; word-break: break-all; }}
  </style>
</head>
<body>
  <div id="report-app">
    <aside id="report-sidebar">
      <h1 id="report-title">GIF Similarity Report</h1>
      <p id="report-stage-label" data-stage-key="{escape(dataset.summary.stage)}"></p>
      <p id="report-stage">{escape(stage_label)}</p>
      <p id="report-summary"></p>
      <input id="report-search" placeholder="Search GIFs">
      <select id="report-sort">
        <option value="group-size-desc">Group size</option>
        <option value="name-asc">Name</option>
      </select>
      <label><input id="report-hide-noise" type="checkbox" checked> Hide noise</label>
    </aside>
    <main id="report-main">
      <div id="report-toolbar">Toolbar</div>
      <section id="report-grid" aria-live="polite">
        <!-- Virtualized grid ready -->
        {initial_cards}
      </section>
    </main>
  </div>

  <script>
    // Embedded report data for offline viewing
    window.__REPORT_DATA__ = {payload_json};
    const STAGE_LABEL = {json.dumps(stage_label)};
    const CARD_GROUP_LABEL = {json.dumps(card_group_label)};

    // Lightweight virtualization renderer: creates a spacer instead of rendering
    // every gif-card node. Real rendering will be implemented separately.
    function renderVisibleRange() {{
      var grid = document.getElementById('report-grid');
      if (!grid) return;
      var searchValue = document.getElementById('report-search').value.trim().toLowerCase();
      var sortValue = document.getElementById('report-sort').value;
      var hideNoise = document.getElementById('report-hide-noise').checked;
      var initialItems = window.__REPORT_DATA__.items.slice();
      if (hideNoise) {{
        initialItems = initialItems.filter((item) => !item.is_noise);
      }}
      if (searchValue) {{
        initialItems = initialItems.filter((item) => item.name.toLowerCase().includes(searchValue));
      }}
      if (sortValue === 'name-asc') {{
        initialItems.sort((left, right) => left.name.localeCompare(right.name));
      }} else {{
        initialItems.sort((left, right) => right.group_size - left.group_size);
      }}
      // Create a single spacer element to represent the total scrollable area
      var spacer = document.createElement('div');
      spacer.className = 'spacer';
      // height could be computed from data, but keep simple for the shell
      spacer.style.height = Math.max(200, initialItems.length * 2) + 'px';
      grid.innerHTML = '';
      const INITIAL_PREVIEW_LIMIT = {INITIAL_PREVIEW_LIMIT};
      const VISIBLE_SLICE_LIMIT = {VISIBLE_SLICE_LIMIT};
      initialItems.slice(0, VISIBLE_SLICE_LIMIT).forEach(function(item) {{
        var card = document.createElement('article');
        card.className = 'report-card';
        var name = document.createElement('div');
        name.className = 'report-card-name';
        name.textContent = item.name;
        var meta = document.createElement('div');
        meta.className = 'report-card-meta';
        meta.textContent = CARD_GROUP_LABEL + ' ' + item.group_id + ' · ' + item.group_size + ' items';
        var path = document.createElement('div');
        path.className = 'report-card-path';
        path.textContent = item.path;
        card.appendChild(name);
        card.appendChild(meta);
        card.appendChild(path);
        grid.appendChild(card);
      }});
      grid.appendChild(spacer);
    }}

    document.getElementById('report-search').addEventListener('input', renderVisibleRange);
    document.getElementById('report-sort').addEventListener('change', renderVisibleRange);
    document.getElementById('report-hide-noise').addEventListener('change', renderVisibleRange);
    document.getElementById('report-stage').textContent = STAGE_LABEL;
    document.getElementById('report-summary').textContent =
      'Total items: ' + window.__REPORT_DATA__.summary.total_items;

    // Auto-run renderer when loaded
    if (document.readyState === 'loading') {{
      document.addEventListener('DOMContentLoaded', renderVisibleRange);
    }} else {{
      renderVisibleRange();
    }}
  </script>
</body>
</html>
"""
    return html
