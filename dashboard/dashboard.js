(function () {
  const STAGE_LABELS = {
    stage1_same_source: "Stage 1 · Same-source groups",
    stage2_action_clusters: "Stage 2 · Action clusters",
  };
  const STAGE_KEYS = ["stage1_same_source", "stage2_action_clusters"];
  const ROW_HEIGHT_PX = 184;
  const OVERSCAN_ROWS = 2;
  const MIN_GRID_COLUMNS = 1;

  function createRuntime(overrides) {
    const deps = overrides || {};
    const win = deps.window || window;
    const doc = deps.document || document;
    const DEFAULT_OUTPUT_BASE = "../output";
    const state = {
      manifest: null,
      manifestMeta: {},
      activeStage: "stage1_same_source",
      stageItems: {},
      hideNoise: true,
      search: "",
      filteredCount: 0,
      visibleCount: 0,
      selectedItem: null,
      selectedGifUnavailable: false,
      renderToken: 0,
    };
    let elements = null;
    let manifestLoadPromise = null;
    const stageLoadState = {};

    function escapeText(value) {
      return String(value == null ? "" : value);
    }

    function trimTrailingSlash(path) {
      return String(path || "").replace(/\/+$/, "");
    }

    function isAbsolutePathOrUrl(path) {
      return /^[a-zA-Z][a-zA-Z\d+\-.]*:/.test(path) || path.startsWith("//") || path.startsWith("/");
    }

    function joinPath(basePath, relativePath) {
      const normalizedBase = trimTrailingSlash(basePath);
      const normalizedRelative = String(relativePath || "").replace(/^\/+/, "");
      if (!normalizedBase) {
        return normalizedRelative;
      }
      if (!normalizedRelative) {
        return normalizedBase;
      }
      return normalizedBase + "/" + normalizedRelative;
    }

    function resolveOutputBasePath() {
      if (typeof deps.outputBasePath === "string" && deps.outputBasePath.trim()) {
        return trimTrailingSlash(deps.outputBasePath.trim()) || DEFAULT_OUTPUT_BASE;
      }
      try {
        const search = (win.location && win.location.search) || "";
        const ParamParser =
          (win && win.URLSearchParams) || (typeof URLSearchParams !== "undefined" ? URLSearchParams : null);
        let outputParam = null;
        if (ParamParser) {
          const params = new ParamParser(search);
          outputParam = params.get("output");
        }
        if (outputParam && outputParam.trim()) {
          return trimTrailingSlash(outputParam.trim()) || DEFAULT_OUTPUT_BASE;
        }
      } catch (error) {
      }
      return DEFAULT_OUTPUT_BASE;
    }

    const outputBasePath = resolveOutputBasePath();

    function resolveOutputAssetPath(path) {
      const assetPath = escapeText(path || "");
      if (!assetPath) {
        return "";
      }
      if (isAbsolutePathOrUrl(assetPath)) {
        return assetPath;
      }
      return joinPath(outputBasePath, assetPath);
    }

    function buildPreviewSrc(item) {
      return resolveOutputAssetPath(item.preview_path || "");
    }

    function buildGifSrc(item) {
      const gifPath = escapeText(item.gif_path || "");
      if (!gifPath || isAbsolutePathOrUrl(gifPath)) {
        return gifPath;
      }
      const manifestOutputDir = escapeText(state.manifestMeta.output_dir || "");
      if (manifestOutputDir) {
        return joinPath(manifestOutputDir, gifPath);
      }
      return gifPath;
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
      if (!manifestLoadPromise) {
        manifestLoadPromise = Promise.resolve(loadScript(resolveOutputAssetPath("dashboard_manifest.js")));
      }
      await manifestLoadPromise;
      state.manifest = win.__GIF_DASHBOARD_MANIFEST__ || {};
      state.manifestMeta = state.manifest.meta || {};
      if (!state.manifest[state.activeStage]) {
        const firstKnownStage = STAGE_KEYS.find((key) => state.manifest[key]);
        if (firstKnownStage) {
          state.activeStage = firstKnownStage;
        }
      }
    }

    function getStageLoadState(stageKey) {
      if (!stageLoadState[stageKey]) {
        stageLoadState[stageKey] = {
          items: [],
          loadedShardCount: 0,
          fullyLoaded: false,
          loadingPromise: null,
        };
      }
      return stageLoadState[stageKey];
    }

    async function loadNextShard(stageKey) {
      const stageConfig = getStageManifest(stageKey);
      const shardList = Array.isArray(stageConfig.shards) ? stageConfig.shards : [];
      const loadState = getStageLoadState(stageKey);
      if (loadState.loadingPromise) {
        await loadState.loadingPromise;
      }
      if (loadState.loadedShardCount >= shardList.length) {
        loadState.fullyLoaded = true;
        state.stageItems[stageKey] = loadState.items;
        return loadState.items;
      }
      const shardStore = (win.__GIF_DASHBOARD_STAGE_SHARDS__ = win.__GIF_DASHBOARD_STAGE_SHARDS__ || {});
      const nextShard = shardList[loadState.loadedShardCount];
      const fileName = nextShard.file_name;
      const shardKey = stageKey + ":" + fileName;
      loadState.loadingPromise = (async function () {
        if (!shardStore[shardKey]) {
          await loadScript(resolveOutputAssetPath(fileName));
        }
        const shardItems = shardStore[shardKey] || [];
        for (let itemIndex = 0; itemIndex < shardItems.length; itemIndex += 1) {
          loadState.items.push(shardItems[itemIndex]);
        }
        loadState.loadedShardCount += 1;
        loadState.fullyLoaded = loadState.loadedShardCount >= shardList.length;
        state.stageItems[stageKey] = loadState.items;
        return loadState.items;
      })();
      try {
        await loadState.loadingPromise;
      } finally {
        loadState.loadingPromise = null;
      }
      return loadState.items;
    }

    async function ensureStageLoaded(stageKey) {
      if (!state.stageItems[stageKey]) {
        state.stageItems[stageKey] = getStageLoadState(stageKey).items;
      }
      if (!getStageLoadState(stageKey).items.length) {
        await loadNextShard(stageKey);
      }
      return state.stageItems[stageKey];
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
      image.src = state.selectedGifUnavailable ? buildPreviewSrc(item) : (buildGifSrc(item) || buildPreviewSrc(item));
      image.alt = escapeText(item.name || item.id);
      image.className = "mt-3 w-full rounded border border-slate-200";
      if (!state.selectedGifUnavailable) {
        image.onerror = function () {
          state.selectedGifUnavailable = true;
          image.onerror = null;
          image.src = buildPreviewSrc(item);
          updateSelectedPanel(item);
        };
      }
      elements.selectedPreview.appendChild(image);

      const meta = doc.createElement("p");
      meta.className = "mt-2 text-sm text-slate-700";
      meta.textContent = escapeText(item.name || item.id);
      elements.selectedPreview.appendChild(meta);

      const path = doc.createElement("p");
      path.className = "mt-1 break-all text-xs text-slate-500";
      path.textContent = buildGifSrc(item);
      elements.selectedPreview.appendChild(path);

      if (state.selectedGifUnavailable) {
        const unavailable = doc.createElement("p");
        unavailable.className = "mt-2 text-xs text-amber-700";
        unavailable.textContent = "GIF unavailable. Showing static preview.";
        elements.selectedPreview.appendChild(unavailable);
      }
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

    function createItemMatcher() {
      const searchNeedle = state.search.trim().toLowerCase();
      return function (item) {
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
      };
    }

    function filteredItemsForActiveStage() {
      const items = state.stageItems[state.activeStage] || [];
      const matcher = createItemMatcher();
      return items.filter(matcher);
    }

    function countTemplateColumns(template) {
      const normalized = escapeText(template).trim();
      if (!normalized || normalized === "none") {
        return 0;
      }
      const repeatMatch = normalized.match(/^repeat\(\s*(\d+)\s*,[\s\S]+\)$/);
      if (repeatMatch) {
        return Number(repeatMatch[1]) || 0;
      }
      let depth = 0;
      let token = "";
      let count = 0;
      for (let i = 0; i < normalized.length; i += 1) {
        const ch = normalized[i];
        if (ch === "(") {
          depth += 1;
        } else if (ch === ")" && depth > 0) {
          depth -= 1;
        }
        if (/\s/.test(ch) && depth === 0) {
          if (token) {
            count += 1;
            token = "";
          }
          continue;
        }
        token += ch;
      }
      if (token) {
        count += 1;
      }
      return count;
    }

    function getGridColumns() {
      if (!elements.grid) {
        return MIN_GRID_COLUMNS;
      }
      if (typeof deps.gridColumnCount === "number" && Number.isFinite(deps.gridColumnCount)) {
        return Math.max(MIN_GRID_COLUMNS, Math.floor(deps.gridColumnCount));
      }
      let templateColumns = "";
      if (typeof win.getComputedStyle === "function") {
        const computedStyle = win.getComputedStyle(elements.grid);
        templateColumns =
          (computedStyle && computedStyle.getPropertyValue && computedStyle.getPropertyValue("grid-template-columns")) ||
          (computedStyle && computedStyle.gridTemplateColumns) ||
          "";
      }
      const derivedColumns = countTemplateColumns(templateColumns);
      if (derivedColumns >= MIN_GRID_COLUMNS) {
        return derivedColumns;
      }
      return MIN_GRID_COLUMNS;
    }

    function getVirtualWindow(totalItems) {
      const columns = getGridColumns();
      const clientHeight = (elements.grid && elements.grid.clientHeight) || (ROW_HEIGHT_PX * 4);
      const scrollTop = (elements.grid && elements.grid.scrollTop) || 0;
      const totalRows = Math.ceil(totalItems / columns);
      const firstVisibleRow = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT_PX));
      const startRow = Math.max(0, firstVisibleRow - OVERSCAN_ROWS);
      const visibleRows = Math.ceil(clientHeight / ROW_HEIGHT_PX) + (OVERSCAN_ROWS * 2);
      const endRow = Math.min(totalRows, startRow + visibleRows);
      const startIndex = Math.min(totalItems, startRow * columns);
      const endIndex = Math.min(totalItems, endRow * columns);
      return { columns, startRow, endRow, totalRows, startIndex, endIndex };
    }

    async function ensureItemsAvailableForWindow(windowEndIndex, matcher) {
      const loadState = getStageLoadState(state.activeStage);
      while (true) {
        const filteredCount = loadState.items.filter(matcher).length;
        if (filteredCount > windowEndIndex || loadState.fullyLoaded) {
          state.stageItems[state.activeStage] = loadState.items;
          return;
        }
        await loadNextShard(state.activeStage);
      }
    }

    function attachCardImageFallback(image, item, onUnavailable) {
      image.onerror = function () {
        image.onerror = null;
        image.src = buildPreviewSrc(item);
        if (typeof onUnavailable === "function") {
          onUnavailable();
        }
      };
    }

    function renderCard(item) {
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
        attachCardImageFallback(image, item);
      });
      card.addEventListener("mouseleave", () => {
        image.src = buildPreviewSrc(item);
        attachCardImageFallback(image, item);
      });
      card.addEventListener("click", () => {
        state.selectedItem = item;
        state.selectedGifUnavailable = false;
        updateSelectedPanel(item);
      });
      return card;
    }

    function createSpacer(heightPx) {
      const spacer = doc.createElement("div");
      spacer.className = "dashboard-spacer col-span-full";
      spacer.style.height = Math.max(0, heightPx) + "px";
      return spacer;
    }

    async function renderGrid() {
      if (!elements.grid) {
        return;
      }
      const renderToken = ++state.renderToken;
      const matcher = createItemMatcher();
      const columns = getGridColumns();
      const clientHeight = elements.grid.clientHeight || (ROW_HEIGHT_PX * 4);
      const scrollTop = elements.grid.scrollTop || 0;
      const firstVisibleRow = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT_PX));
      const targetEndRow = firstVisibleRow + Math.ceil(clientHeight / ROW_HEIGHT_PX) + (OVERSCAN_ROWS * 2);
      const targetEndIndex = targetEndRow * columns;
      await ensureItemsAvailableForWindow(targetEndIndex, matcher);
      if (renderToken !== state.renderToken) {
        return;
      }
      const filtered = filteredItemsForActiveStage();
      const window = getVirtualWindow(filtered.length);
      const visible = filtered.slice(window.startIndex, window.endIndex);
      state.filteredCount = filtered.length;
      state.visibleCount = visible.length;
      elements.grid.innerHTML = "";

      elements.grid.appendChild(createSpacer(window.startRow * ROW_HEIGHT_PX));
      for (let index = 0; index < visible.length; index += 1) {
        elements.grid.appendChild(renderCard(visible[index]));
      }
      elements.grid.appendChild(createSpacer((window.totalRows - window.endRow) * ROW_HEIGHT_PX));

      if (state.selectedItem) {
        updateSelectedPanel(state.selectedItem);
      }
    }

    function scheduleRender() {
      renderGrid().catch((error) => {
        console.error(error);
      });
    }

    async function setStage(stageKey) {
      state.activeStage = stageKey;
      state.selectedItem = null;
      state.selectedGifUnavailable = false;
      if (elements && elements.grid) {
        elements.grid.scrollTop = 0;
      }
      await ensureStageLoaded(stageKey);
      updateTabStyles();
      updateSummary();
      scheduleRender();
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
          scheduleRender();
        });
      }
      if (elements.hideNoise) {
        elements.hideNoise.addEventListener("change", () => {
          state.hideNoise = elements.hideNoise.checked !== false;
          scheduleRender();
        });
      }
      if (elements.grid) {
        elements.grid.addEventListener("scroll", () => {
          scheduleRender();
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
