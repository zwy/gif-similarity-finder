from dataclasses import asdict
import json

from gif_similarity_finder.report_data import ReportDataset


def render_report_html(dataset: ReportDataset) -> str:
    """Render a lightweight offline HTML shell for the report.

    The output must embed the report data as JSON in window.__REPORT_DATA__ and
    provide a minimal virtualized grid. Do not pre-render one card per item.
    """
    # Safely convert dataclasses (including slots=True) to primitives
    payload = asdict(dataset)
    payload_json = json.dumps(payload).replace("</", "<\\/")

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
    #report-grid {{ display: block; position: relative; min-height: 200px; background: #f9f9f9; }}
    .spacer {{ width: 100%; height: 100px; background: transparent; }}
  </style>
</head>
<body>
  <div id="report-app">
    <aside id="report-sidebar">
      <input id="report-search" placeholder="Search GIFs">
      <select id="report-sort">
        <option value="group-size-desc">Group size</option>
        <option value="name-asc">Name</option>
      </select>
      <label><input id="report-hide-noise" type="checkbox"> Hide noise</label>
    </aside>
    <main id="report-main">
      <div id="report-toolbar">Toolbar</div>
      <section id="report-grid" aria-live="polite">
        <!-- Virtualized grid ready -->
      </section>
    </main>
  </div>

  <script>
    // Embedded report data for offline viewing
    window.__REPORT_DATA__ = {payload_json};

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
      grid.appendChild(spacer);
    }}

    document.getElementById('report-search').addEventListener('input', renderVisibleRange);
    document.getElementById('report-sort').addEventListener('change', renderVisibleRange);
    document.getElementById('report-hide-noise').addEventListener('change', renderVisibleRange);

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
