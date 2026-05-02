(function () {
  const STAGE_LABELS = {
    stage1_same_source: "Stage 1 · Same-source groups",
    stage2_action_clusters: "Stage 2 · Action clusters",
  };
  const STAGE_KEYS = ["stage1_same_source", "stage2_action_clusters"];
  const VISIBLE_SLICE_SIZE = 80;

  function createRuntime(overrides) {
    const deps = overrides || {};
    const win = deps.window || window;
    const doc = deps.document || document;
    const state = {
      manifest: null,
      activeStage: "stage1_same_source",
      stageItems: {},
      hideNoise: true,
      search: "",
      filteredCount: 0,
      visibleCount: 0,
      selectedItem: null,
    };
    let elements = null;

    function escapeText(value) {
      return String(value == null ? "" : value);
    }

    function buildPreviewSrc(item) {
      return "../output/" + escapeText(item.preview_path || "");
    }

    function buildGifSrc(item) {
      return escapeText(item.gif_path || "");
    }

    function getStageManifest(stageKey) {
      if (!state.manifest || !state.manifest[stageKey]) {
        return { summary: {}, shards: [] };
      }
      return state.manifest[stageKey];
    }

    function loadScript(src) {
      if (typeof deps.loadScript === "function") {
        return Promise.resolve(deps.loadScript(src));
      }
      return new Promise((resolve, reject) => {
        const script = doc.createElement("script");
        script.src = src;
        script.onload = resolve;
        script.onerror = function () {
          reject(new Error("Failed to load script: " + src));
        };
        doc.head.appendChild(script);
      });
    }

    async function ensureManifestLoaded() {
      if (state.manifest) {
        return;
      }
      if (!win.__GIF_DASHBOARD_MANIFEST__) {
        await loadScript("../output/dashboard_manifest.js");
      }
      state.manifest = win.__GIF_DASHBOARD_MANIFEST__ || {};
      if (!state.manifest[state.activeStage]) {
        const firstKnownStage = STAGE_KEYS.find((key) => state.manifest[key]);
        if (firstKnownStage) {
          state.activeStage = firstKnownStage;
        }
      }
    }

    async function ensureStageLoaded(stageKey) {
      if (state.stageItems[stageKey]) {
        return state.stageItems[stageKey];
      }
      const stageConfig = getStageManifest(stageKey);
      const shardList = Array.isArray(stageConfig.shards) ? stageConfig.shards : [];
      const shardStore = (win.__GIF_DASHBOARD_STAGE_SHARDS__ = win.__GIF_DASHBOARD_STAGE_SHARDS__ || {});
      const combined = [];
      for (let index = 0; index < shardList.length; index += 1) {
        const shard = shardList[index];
        const fileName = shard.file_name;
        const shardKey = stageKey + ":" + fileName;
        if (!shardStore[shardKey]) {
          await loadScript("../output/" + fileName);
        }
        const shardItems = shardStore[shardKey] || [];
        for (let itemIndex = 0; itemIndex < shardItems.length; itemIndex += 1) {
          combined.push(shardItems[itemIndex]);
        }
      }
      state.stageItems[stageKey] = combined;
      return combined;
    }

    function updateSelectedPanel(item) {
      if (!elements.selectedPreview) {
        return;
      }
      elements.selectedPreview.innerHTML = "";
      const title = doc.createElement("h2");
      title.className = "text-base font-semibold";
      title.textContent = "Selected Item";
      elements.selectedPreview.appendChild(title);
      if (!item) {
        const empty = doc.createElement("p");
        empty.className = "mt-2 text-sm text-slate-600";
        empty.textContent = "Choose a card to inspect details.";
        elements.selectedPreview.appendChild(empty);
        return;
      }
      const image = doc.createElement("img");
      image.src = buildGifSrc(item) || buildPreviewSrc(item);
      image.alt = escapeText(item.name || item.id);
      image.className = "mt-3 w-full rounded border border-slate-200";
      elements.selectedPreview.appendChild(image);

      const meta = doc.createElement("p");
      meta.className = "mt-2 text-sm text-slate-700";
      meta.textContent = escapeText(item.name || item.id);
      elements.selectedPreview.appendChild(meta);

      const path = doc.createElement("p");
      path.className = "mt-1 break-all text-xs text-slate-500";
      path.textContent = buildGifSrc(item);
      elements.selectedPreview.appendChild(path);
    }

    function updateSummary() {
      if (!elements.summary) {
        return;
      }
      const stageConfig = getStageManifest(state.activeStage);
      const summary = stageConfig.summary || {};
      elements.summary.textContent =
        (STAGE_LABELS[state.activeStage] || state.activeStage) +
        " · Total items: " + (summary.total_items || 0) +
        " · Groups: " + (summary.total_groups || 0) +
        " · Noise: " + (summary.noise_items || 0) +
        " · Largest group: " + (summary.largest_group_size || 0);
    }

    function updateTabStyles() {
      for (let index = 0; index < STAGE_KEYS.length; index += 1) {
        const stageKey = STAGE_KEYS[index];
        const tab = elements.tabs[stageKey];
        if (!tab) {
          continue;
        }
        const isActive = stageKey === state.activeStage;
        tab.setAttribute("aria-selected", isActive ? "true" : "false");
        tab.className = isActive
          ? "rounded-md border border-indigo-500 bg-indigo-50 px-3 py-1.5 text-sm font-medium text-indigo-700"
          : "rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium";
      }
    }

    function filteredItemsForActiveStage() {
      const items = state.stageItems[state.activeStage] || [];
      const searchNeedle = state.search.trim().toLowerCase();
      return items.filter((item) => {
        if (state.hideNoise && item.is_noise) {
          return false;
        }
        if (!searchNeedle) {
          return true;
        }
        const text = [
          item.name,
          item.gif_path,
          item.group_id,
          item.id,
        ]
          .map((value) => escapeText(value).toLowerCase())
          .join(" ");
        return text.includes(searchNeedle);
      });
    }

    function renderGrid() {
      if (!elements.grid) {
        return;
      }
      const filtered = filteredItemsForActiveStage();
      const visible = filtered.slice(0, VISIBLE_SLICE_SIZE);
      state.filteredCount = filtered.length;
      state.visibleCount = visible.length;
      elements.grid.innerHTML = "";

      for (let index = 0; index < visible.length; index += 1) {
        const item = visible[index];
        const card = doc.createElement("article");
        card.className = "dashboard-card";

        const image = doc.createElement("img");
        image.className = "h-32 w-full rounded object-cover";
        image.src = buildPreviewSrc(item);
        image.alt = escapeText(item.name || item.id);
        card.appendChild(image);

        const label = doc.createElement("p");
        label.className = "mt-2 truncate text-sm text-slate-700";
        label.textContent = escapeText(item.name || item.id);
        card.appendChild(label);

        card.addEventListener("mouseenter", () => {
          image.src = buildGifSrc(item) || buildPreviewSrc(item);
        });
        card.addEventListener("mouseleave", () => {
          image.src = buildPreviewSrc(item);
        });
        card.addEventListener("click", () => {
          state.selectedItem = item;
          updateSelectedPanel(item);
        });
        elements.grid.appendChild(card);
      }

      const spacer = doc.createElement("div");
      spacer.className = "dashboard-spacer col-span-full h-1";
      elements.grid.appendChild(spacer);

      if (state.selectedItem) {
        updateSelectedPanel(state.selectedItem);
      }
    }

    async function setStage(stageKey) {
      state.activeStage = stageKey;
      await ensureStageLoaded(stageKey);
      updateTabStyles();
      updateSummary();
      renderGrid();
    }

    async function init() {
      elements = {
        search: doc.getElementById("dashboard-search"),
        hideNoise: doc.getElementById("dashboard-hide-noise"),
        summary: doc.getElementById("dashboard-summary"),
        grid: doc.getElementById("dashboard-grid"),
        selectedPreview: doc.getElementById("selected-preview"),
        tabs: {
          stage1_same_source: doc.getElementById("stage-tab-stage1_same_source"),
          stage2_action_clusters: doc.getElementById("stage-tab-stage2_action_clusters"),
        },
      };

      state.hideNoise = !elements.hideNoise || elements.hideNoise.checked !== false;
      state.search = elements.search ? elements.search.value || "" : "";
      updateSelectedPanel(null);

      await ensureManifestLoaded();
      await setStage(state.activeStage);

      if (elements.search) {
        elements.search.addEventListener("input", () => {
          state.search = elements.search.value || "";
          renderGrid();
        });
      }
      if (elements.hideNoise) {
        elements.hideNoise.addEventListener("change", () => {
          state.hideNoise = elements.hideNoise.checked !== false;
          renderGrid();
        });
      }
      STAGE_KEYS.forEach((stageKey) => {
        const tab = elements.tabs[stageKey];
        if (!tab) {
          return;
        }
        tab.addEventListener("click", () => {
          setStage(stageKey);
        });
      });
    }

    return {
      init,
      setStage,
      getVisibleCount: () => state.visibleCount,
      getFilteredCount: () => state.filteredCount,
    };
  }

  const api = {
    createRuntime,
    init: function () {
      const runtime = createRuntime();
      runtime.init();
      return runtime;
    },
  };
  window.GifDashboard = api;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", api.init);
  } else {
    api.init();
  }
})();
