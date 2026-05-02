(function () {
  const STAGE_LABELS = {
    stage1_same_source: "Stage 1 · Same-source groups",
    stage2_action_clusters: "Stage 2 · Action clusters",
  };
  const STAGE_KEYS = ["stage1_same_source", "stage2_action_clusters"];
  const ACTIVE_STAGE_STORAGE_KEY = "gif-dashboard-active-stage";
  const ROW_HEIGHT_PX = 184;
  const GROUP_HEADER_HEIGHT_PX = 48;
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
      sortKey: "name_asc",
      minGroupSize: 1,
      filteredCount: 0,
      visibleCount: 0,
      selectedItem: null,
      selectedGifUnavailable: false,
      renderToken: 0,
      warnings: [],
      filterSortCacheKey: null,
      filterSortCacheItems: null,
      filterSortComputeCount: 0,
    };
    let elements = null;
    let manifestLoadPromise = null;
    const stageLoadState = {};

    function escapeText(value) {
      return String(value == null ? "" : value);
    }

    function escapeHtml(str) {
      return String(str == null ? "" : str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
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

    function readStoredActiveStage() {
      try {
        if (!win.localStorage || typeof win.localStorage.getItem !== "function") {
          return null;
        }
        const saved = win.localStorage.getItem(ACTIVE_STAGE_STORAGE_KEY);
        if (STAGE_KEYS.includes(saved)) {
          return saved;
        }
      } catch (error) {
      }
      return null;
    }

    function storeActiveStage(stageKey) {
      try {
        if (!win.localStorage || typeof win.localStorage.setItem !== "function") {
          return;
        }
        win.localStorage.setItem(ACTIVE_STAGE_STORAGE_KEY, stageKey);
      } catch (error) {
      }
    }

    function addWarning(message) {
      const text = escapeText(message).trim();
      if (!text) {
        return;
      }
      if (!state.warnings.includes(text)) {
        state.warnings.push(text);
      }
      if (elements && elements.warning) {
        elements.warning.className = "mb-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800";
        elements.warning.textContent = state.warnings.join(" ");
      }
    }

    function renderWarnings() {
      if (!elements || !elements.warning) {
        return;
      }
      if (!state.warnings.length) {
        elements.warning.className = "mb-4 hidden rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800";
        elements.warning.textContent = "";
        return;
      }
      elements.warning.className = "mb-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800";
      elements.warning.textContent = state.warnings.join(" ");
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
      const manifestWarnings = Array.isArray(state.manifestMeta.warnings) ? state.manifestMeta.warnings : [];
      manifestWarnings.forEach(addWarning);
      if (!state.manifest[state.activeStage]) {
        const firstKnownStage = STAGE_KEYS.find((key) => state.manifest[key]);
        if (firstKnownStage) {
          state.activeStage = firstKnownStage;
        } else {
          addWarning("Warning: manifest is missing required stage data.");
        }
      }
      STAGE_KEYS.forEach((stageKey) => {
        const stageConfig = state.manifest[stageKey];
        if (!stageConfig) {
          return;
        }
        if (!Array.isArray(stageConfig.shards)) {
          addWarning("Warning: " + stageKey + " shards are missing or malformed in manifest.");
          return;
        }
        if (stageConfig.shards.some((shard) => !shard || !shard.file_name)) {
          addWarning("Warning: " + stageKey + " has shard entries without file_name.");
        }
      });
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
      if (!fileName) {
        addWarning("Warning: missing shard file name for " + stageKey + ".");
        loadState.loadedShardCount += 1;
        loadState.fullyLoaded = loadState.loadedShardCount >= shardList.length;
        state.stageItems[stageKey] = loadState.items;
        return loadState.items;
      }
      const shardKey = stageKey + ":" + fileName;
      loadState.loadingPromise = (async function () {
        try {
          if (!shardStore[shardKey]) {
            await loadScript(resolveOutputAssetPath(fileName));
          }
        } catch (error) {
          addWarning("Warning: failed to load shard " + fileName + " for " + stageKey + ".");
          loadState.loadedShardCount += 1;
          loadState.fullyLoaded = loadState.loadedShardCount >= shardList.length;
          state.stageItems[stageKey] = loadState.items;
          return loadState.items;
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

      if (item.group_id) {
        const groupInfo = doc.createElement("p");
        groupInfo.className = "mt-2 text-xs text-slate-500";
        groupInfo.textContent = "Group: " + escapeText(item.group_id);
        elements.selectedPreview.appendChild(groupInfo);
      }

      if (item.group_size) {
        const sizeInfo = doc.createElement("p");
        sizeInfo.className = "mt-1 text-xs text-slate-500";
        sizeInfo.textContent = "Group size: " + escapeText(item.group_size);
        elements.selectedPreview.appendChild(sizeInfo);
      }

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
        const groupSize = Number(item.group_size) || 0;
        if (groupSize < state.minGroupSize) {
          return false;
        }
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

    function compareItems(leftItem, rightItem) {
      function compareText(leftText, rightText) {
        if (typeof leftText.localeCompare === "function") {
          return leftText.localeCompare(rightText, undefined, { numeric: true, sensitivity: "base" });
        }
        if (leftText < rightText) {
          return -1;
        }
        if (leftText > rightText) {
          return 1;
        }
        return 0;
      }
      // Sort by group first, then by name within group
      const leftGroup = escapeText(leftItem.group_id || "");
      const rightGroup = escapeText(rightItem.group_id || "");
      if (leftGroup !== rightGroup) {
        if (state.sortKey === "group_size_desc") {
          const leftGroupSize = Number(leftItem.group_size) || 0;
          const rightGroupSize = Number(rightItem.group_size) || 0;
          if (leftGroupSize !== rightGroupSize) {
            return rightGroupSize - leftGroupSize;
          }
        }
        const groupCmp = compareText(leftGroup, rightGroup);
        if (groupCmp !== 0) {
          return groupCmp;
        }
      }
      const leftName = escapeText(leftItem.name || leftItem.id);
      const rightName = escapeText(rightItem.name || rightItem.id);
      const nameComparison = compareText(leftName, rightName);
      if (nameComparison !== 0) {
        return nameComparison;
      }
      return compareText(escapeText(leftItem.id), escapeText(rightItem.id));
    }

    function buildFilterSortCacheKey(stageKey) {
      const loadState = getStageLoadState(stageKey);
      return [
        stageKey,
        state.search,
        state.sortKey,
        state.hideNoise ? "1" : "0",
        String(state.minGroupSize),
        String(loadState.loadedShardCount),
        String(loadState.items.length),
      ].join("|");
    }

    function filteredItemsForActiveStage() {
      const cacheKey = buildFilterSortCacheKey(state.activeStage);
      if (state.filterSortCacheKey === cacheKey && state.filterSortCacheItems) {
        return state.filterSortCacheItems;
      }
      const items = state.stageItems[state.activeStage] || [];
      const matcher = createItemMatcher();
      state.filterSortCacheItems = items.filter(matcher).sort(compareItems);
      state.filterSortCacheKey = cacheKey;
      state.filterSortComputeCount += 1;
      return state.filterSortCacheItems;
    }

    /**
     * Group sorted items by group_id.
     * Returns an array of { groupId, groupSize, items[] } objects,
     * preserving the sort order established by compareItems.
     */
    function groupItemsByGroupId(sortedItems) {
      const groups = [];
      const groupMap = new Map();
      for (let i = 0; i < sortedItems.length; i++) {
        const item = sortedItems[i];
        const gid = escapeText(item.group_id || "");
        if (!groupMap.has(gid)) {
          const group = { groupId: gid, groupSize: Number(item.group_size) || 0, items: [] };
          groupMap.set(gid, group);
          groups.push(group);
        }
        groupMap.get(gid).items.push(item);
      }
      return groups;
    }

    function readMinGroupSize(rawValue) {
      const parsed = Number.parseInt(String(rawValue || ""), 10);
      if (!Number.isFinite(parsed) || parsed < 1) {
        return 1;
      }
      return parsed;
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

    async function ensureItemsAvailableForWindow(windowEndIndex) {
      const loadState = getStageLoadState(state.activeStage);
      while (true) {
        const filteredCount = filteredItemsForActiveStage().length;
        if (filteredCount > windowEndIndex || loadState.fullyLoaded) {
          state.stageItems[state.activeStage] = loadState.items;
          return;
        }
        await loadNextShard(state.activeStage);
      }
    }

    function attachCardImageFallback(image, item, placeholder, onUnavailable) {
      const previewSrc = buildPreviewSrc(item);
      image.dataset.previewAttempted = image.src === previewSrc ? "true" : "false";
      image.onerror = function () {
        const previewAlreadyAttempted = image.dataset.previewAttempted === "true";
        if (!previewAlreadyAttempted && previewSrc) {
          image.dataset.previewAttempted = "true";
          image.src = previewSrc;
          return;
        }
        image.onerror = null;
        image.className = "hidden h-32 w-full rounded object-cover";
        if (placeholder) {
          placeholder.className = "dashboard-card-unavailable flex h-32 w-full items-center justify-center rounded border border-dashed border-slate-300 bg-slate-100 px-2 text-center text-xs text-slate-600";
          placeholder.textContent = "Preview unavailable";
        }
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

      const unavailable = doc.createElement("p");
      unavailable.className = "dashboard-card-unavailable hidden h-32 w-full items-center justify-center rounded border border-dashed border-slate-300 bg-slate-100 px-2 text-center text-xs text-slate-600";
      unavailable.textContent = "Preview unavailable";
      card.appendChild(unavailable);
      attachCardImageFallback(image, item, unavailable);

      card.addEventListener("mouseenter", () => {
        image.className = "h-32 w-full rounded object-cover";
        unavailable.className = "dashboard-card-unavailable hidden h-32 w-full items-center justify-center rounded border border-dashed border-slate-300 bg-slate-100 px-2 text-center text-xs text-slate-600";
        image.src = buildGifSrc(item) || buildPreviewSrc(item);
        attachCardImageFallback(image, item, unavailable);
      });
      card.addEventListener("mouseleave", () => {
        image.className = "h-32 w-full rounded object-cover";
        unavailable.className = "dashboard-card-unavailable hidden h-32 w-full items-center justify-center rounded border border-dashed border-slate-300 bg-slate-100 px-2 text-center text-xs text-slate-600";
        image.src = buildPreviewSrc(item);
        attachCardImageFallback(image, item, unavailable);
      });
      card.addEventListener("click", () => {
        state.selectedItem = item;
        state.selectedGifUnavailable = false;
        updateSelectedPanel(item);
      });
      return card;
    }

    /**
     * Render a full-width group header divider.
     * Shows group ID, item count, flanked by horizontal rules.
     */
    function renderGroupHeader(groupId, groupSize, itemCount) {
      const header = doc.createElement("div");
      header.className = "dashboard-group-header col-span-full flex items-center gap-3 pt-3 pb-1";

      const line1 = doc.createElement("div");
      line1.className = "h-px flex-1 bg-slate-200";

      const badge = doc.createElement("span");
      badge.className =
        "inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1 " +
        "text-xs font-medium text-slate-600 shadow-sm whitespace-nowrap";
      badge.innerHTML =
        '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
        '<rect x="2" y="7" width="20" height="14" rx="2"/>' +
        '<path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/></svg>' +
        '<span class="font-semibold text-slate-800">' + escapeHtml(groupId || "ungrouped") + "</span>" +
        '<span class="text-slate-400">·</span>' +
        '<span>' + itemCount + " item" + (itemCount !== 1 ? "s" : "") + "</span>";

      const line2 = doc.createElement("div");
      line2.className = "h-px flex-1 bg-slate-200";

      header.appendChild(line1);
      header.appendChild(badge);
      header.appendChild(line2);
      return header;
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
      const columns = getGridColumns();
      const clientHeight = elements.grid.clientHeight || (ROW_HEIGHT_PX * 4);
      const scrollTop = elements.grid.scrollTop || 0;
      const firstVisibleRow = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT_PX));
      const targetEndRow = firstVisibleRow + Math.ceil(clientHeight / ROW_HEIGHT_PX) + (OVERSCAN_ROWS * 2);
      const targetEndIndex = targetEndRow * columns;
      await ensureItemsAvailableForWindow(targetEndIndex);
      if (renderToken !== state.renderToken) {
        return;
      }

      const filtered = filteredItemsForActiveStage();
      state.filteredCount = filtered.length;
      elements.grid.innerHTML = "";
      renderWarnings();

      if (filtered.length === 0) {
        if (elements.emptyState) {
          elements.emptyState.className =
            "mt-4 rounded-lg border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-600";
          elements.emptyState.textContent = "No items found for this stage and current filters.";
        }
        return;
      }

      if (elements.emptyState) {
        elements.emptyState.className =
          "mt-4 hidden rounded-lg border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-600";
        elements.emptyState.textContent = "";
      }

      // Group items by group_id and render with section headers
      const groups = groupItemsByGroupId(filtered);
      let visibleCount = 0;

      for (let gi = 0; gi < groups.length; gi++) {
        const group = groups[gi];
        elements.grid.appendChild(
          renderGroupHeader(group.groupId, group.groupSize, group.items.length)
        );
        for (let ii = 0; ii < group.items.length; ii++) {
          elements.grid.appendChild(renderCard(group.items[ii]));
          visibleCount++;
        }
      }

      state.visibleCount = visibleCount;

      if (state.selectedItem) {
        updateSelectedPanel(state.selectedItem);
      }
    }

    function scheduleRender() {
      renderGrid().catch((error) => {
        addWarning("Warning: failed to render dashboard grid.");
        console.error(error);
      });
    }

    async function setStage(stageKey) {
      state.activeStage = stageKey;
      storeActiveStage(stageKey);
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
        sort: doc.getElementById("dashboard-sort"),
        minGroupSize: doc.getElementById("dashboard-min-group-size"),
        summary: doc.getElementById("dashboard-summary"),
        grid: doc.getElementById("dashboard-grid"),
        warning: doc.getElementById("dashboard-warning"),
        emptyState: doc.getElementById("dashboard-empty-state"),
        selectedPreview: doc.getElementById("selected-preview"),
        tabs: {
          stage1_same_source: doc.getElementById("stage-tab-stage1_same_source"),
          stage2_action_clusters: doc.getElementById("stage-tab-stage2_action_clusters"),
        },
      };

      state.hideNoise = !elements.hideNoise || elements.hideNoise.checked !== false;
      state.search = elements.search ? elements.search.value || "" : "";
      state.sortKey = elements.sort ? elements.sort.value || "name_asc" : "name_asc";
      state.minGroupSize = elements.minGroupSize ? readMinGroupSize(elements.minGroupSize.value) : 1;
      const storedStage = readStoredActiveStage();
      if (storedStage) {
        state.activeStage = storedStage;
      }
      updateSelectedPanel(null);
      renderWarnings();

      try {
        await ensureManifestLoaded();
      } catch (error) {
        addWarning("Warning: failed to load dashboard manifest.");
        state.manifest = { meta: {} };
        state.manifestMeta = {};
      }
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
      if (elements.sort) {
        elements.sort.addEventListener("change", () => {
          state.sortKey = elements.sort.value || "name_asc";
          scheduleRender();
        });
      }
      if (elements.minGroupSize) {
        elements.minGroupSize.addEventListener("input", () => {
          state.minGroupSize = readMinGroupSize(elements.minGroupSize.value);
          if (String(state.minGroupSize) !== String(elements.minGroupSize.value || "")) {
            elements.minGroupSize.value = String(state.minGroupSize);
          }
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
      getFilterSortComputeCount: () => state.filterSortComputeCount,
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
