const state = {
  data: null,
  appId: null,
  country: "us",
  device: "iphone",
  tab: "rankings",
  filter: "",
  rankSortField: "rank",
  rankSortDirection: "asc",
  selectedTarget: null,
  pendingDeactivateTarget: null,
  pendingDeleteApp: null,
  localization: null,
  coverageStep: 1,
  coverageCountry: null,
  coverageDraft: null,
  coverageAnalysis: null,
  coverageStrategy: null,
  coverageGoal: null,
  coverageBrand: "",
  coverageSaveTimer: null,
  coverageSaveRevision: 0,
  niche: null,
  nicheLoaded: false,
  nicheView: false,
  syncPollTimer: null,
  syncWasRunning: false,
  appleAds: null,
  appleAdsLoaded: false,
  appleAdsLoading: false,
  appleAdsShowPaused: false,
  appleAdsCountryFilter: "all",
  appleAdsSortField: "keyword",
  appleAdsSortDirection: "asc",
  competitorMatrix: null,
  competitorMatrixLoaded: false,
  competitorMatrixLoading: false,
  pendingTopApp: null,
  checkingTargets: new Set(),
  queuedCheckTargets: new Set(),
  checkInProgress: false,
};

const el = (selector) => document.querySelector(selector);
const all = (selector) => [...document.querySelectorAll(selector)];
const customSelects = new WeakMap();
let activeCustomSelect = null;
let customSelectSequence = 0;
let customSelectRefreshFrame = 0;

document.addEventListener("DOMContentLoaded", () => {
  refreshCustomSelects();
  observeDynamicSelects();
  bindEvents();
  loadDashboard();
});

function bindEvents() {
  bindOnboardingEvents();
  el("#countrySelect").addEventListener("change", (event) => {
    state.country = event.target.value;
    state.selectedTarget = null;
    state.filter = "";
    resetCoverage();
    el("#keywordFilter").value = "";
    loadDashboard();
  });
  el("#deviceSelect").addEventListener("change", (event) => {
    state.device = event.target.value;
    state.selectedTarget = null;
    state.selectedTarget = null;
    state.filter = "";
    if (state.coverageStep === 3) {
      state.coverageStep = 2;
      state.coverageAnalysis = null;
      state.coverageStrategy = null;
    }
    el("#keywordFilter").value = "";
    renderHero();
    renderCountryVisibility();
    renderRankings();
    renderListingCoverage();
    if (state.tab === "paid") loadAppleAds();
    if (state.tab === "compare") loadCompetitorMatrix();
  });
  el("#keywordFilter").addEventListener("input", (event) => {
    state.filter = event.target.value.trim().toLowerCase();
    renderRankings();
  });
  el("#rankingsHeader").addEventListener("click", rankingHeaderClick);
  el("#metrics").addEventListener("click", metricCardClick);
  el("#runCheckButton").addEventListener("click", runCheck);
  el("#addKeywordButton").addEventListener("click", openKeywordModal);
  el("#localizeKeywordsButton").addEventListener("click", localizeKeywordInput);
  el("#selectAllCountries").addEventListener("click", toggleAllCountries);
  el("#keywordInput").addEventListener("input", resetLocalization);
  el("#countryChecks").addEventListener("change", resetLocalization);
  el("#addAppButton").addEventListener("click", () => el("#appModal").showModal());
  el("#keywordForm").addEventListener("submit", addKeyword);
  el("#appForm").addEventListener("submit", addApp);
  el("#compareButton").addEventListener("click", compareApps);
  el("#confirmDeactivateButton").addEventListener("click", confirmDeactivate);
  el("#confirmDeleteApp").addEventListener("click", confirmDeleteApp);
  el("#appList").addEventListener("click", appListClick);
  el("#menuButton").addEventListener("click", () => el("#sidebar").classList.toggle("open"));
  el("#rankingsBody").addEventListener("click", rankingClick);
  el("#rankingsBody").addEventListener("pointerover", showTopAppTooltip);
  el("#rankingsBody").addEventListener("pointerout", hideTopAppTooltip);
  el("#rankingsBody").addEventListener("focusin", showTopAppTooltip);
  el("#rankingsBody").addEventListener("focusout", hideTopAppTooltip);
  el("#competitorMatrix").addEventListener("click", competitorMatrixAction);
  el("#topAppMenuClose").addEventListener("click", hideTopAppMenu);
  el("#addTopAppCompetitor").addEventListener("click", addPendingTopAppCompetitor);
  el("#countryVisibility").addEventListener("click", countryVisibilityClick);
  el("#appleAdsContent").addEventListener("click", appleAdsAction);
  el("#appleAdsContent").addEventListener("change", appleAdsChange);
  window.addEventListener("resize", () => {
    hideTopAppTooltip();
    closeCustomSelect();
  });
  window.addEventListener("scroll", (event) => {
    hideTopAppTooltip();
    if (!(event.target instanceof Element) || !event.target.closest(".custom-select-menu")) {
      closeCustomSelect();
    }
  }, true);
  document.addEventListener("pointerdown", (event) => {
    if (!el("#topAppMenu").hidden && !event.target.closest("#topAppMenu") && !event.target.closest(".top-app-preview")) hideTopAppMenu();
    if (
      activeCustomSelect
      && !event.target.closest(".custom-select")
      && !event.target.closest(".custom-select-menu")
    ) {
      closeCustomSelect({ restoreFocus: false });
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      hideTopAppMenu();
      closeCustomSelect({ restoreFocus: true });
    }
  });
  all("[data-tab], [data-tab-target]").forEach((button) => {
    button.addEventListener("click", () => {
      closeNicheWorkspace();
      const target = button.dataset.tab || button.dataset.tabTarget;
      switchTab(target);
      if (target === "paid") loadAppleAds();
      if (target === "compare") loadCompetitorMatrix();
    });
  });
  el("#nicheNavButton").addEventListener("click", openNicheWorkspace);
  el("#nicheCreateForm").addEventListener("submit", createNicheBoard);
  el("#nicheAgentForm").addEventListener("submit", addNicheKeywordsWithAgent);
  el("#nicheCheckNowButton").addEventListener("click", checkNicheBoard);
  el("#nicheAddCountryButton").addEventListener("click", addNicheCountry);
  el("#nicheBoardSelect").addEventListener("change", (event) => {
    loadNicheWorkspace(Number(event.target.value));
  });
  all("[data-close-modal]").forEach((button) => {
    button.addEventListener("click", () => {
      const dialog = button.closest("dialog");
      if (dialog.id === "confirmModal") state.pendingDeactivateTarget = null;
      if (dialog.id === "deleteAppModal") state.pendingDeleteApp = null;
      if (dialog.id === "keywordModal") resetLocalization();
      dialog.close();
    });
  });
}

function observeDynamicSelects() {
  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => cleanupRemovedSelects(mutation.removedNodes));
    const relevant = mutations.some((mutation) => {
      if (mutation.target instanceof HTMLSelectElement) return true;
      return [...mutation.addedNodes].some((node) => (
        node instanceof Element
        && (node.matches("select") || Boolean(node.querySelector("select")))
      ));
    });
    if (relevant) scheduleCustomSelectRefresh();
  });
  observer.observe(document.body, { childList: true, subtree: true });
}

function cleanupRemovedSelects(nodes) {
  [...nodes].forEach((node) => {
    if (!(node instanceof Element)) return;
    const removed = node.matches("select") ? [node] : [...node.querySelectorAll("select")];
    removed.forEach((select) => {
      const instance = customSelects.get(select);
      if (!instance) return;
      if (activeCustomSelect === instance) closeCustomSelect();
      instance.menu.remove();
    });
  });
}

function scheduleCustomSelectRefresh() {
  if (customSelectRefreshFrame) return;
  customSelectRefreshFrame = window.requestAnimationFrame(() => {
    customSelectRefreshFrame = 0;
    refreshCustomSelects();
  });
}

function refreshCustomSelects(root = document) {
  if (activeCustomSelect && !activeCustomSelect.trigger.isConnected) closeCustomSelect();
  root.querySelectorAll("select").forEach((select) => {
    if (!customSelects.has(select)) enhanceSelect(select);
    else syncCustomSelect(select);
  });
}

function enhanceSelect(select) {
  if (customSelects.has(select) || select.closest(".custom-select")) return;
  const label = select.closest("label");
  const labelText = select.getAttribute("aria-label")
    || label?.querySelector(":scope > span")?.textContent?.trim()
    || label?.querySelector(":scope > .field > span")?.textContent?.trim()
    || "Choose an option";
  const wrapper = document.createElement("span");
  wrapper.className = "custom-select";
  select.parentNode.insertBefore(wrapper, select);
  wrapper.appendChild(select);
  select.classList.add("custom-select-native");
  select.tabIndex = -1;
  select.setAttribute("aria-hidden", "true");

  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "custom-select-trigger";
  trigger.setAttribute("role", "combobox");
  trigger.setAttribute("aria-haspopup", "listbox");
  trigger.setAttribute("aria-expanded", "false");
  trigger.setAttribute("aria-label", labelText);
  trigger.innerHTML = `<span class="custom-select-value"></span><span class="custom-select-chevron" aria-hidden="true"></span>`;
  wrapper.appendChild(trigger);

  const menu = document.createElement("div");
  menu.className = "custom-select-menu";
  menu.hidden = true;
  menu.id = `custom-select-menu-${++customSelectSequence}`;
  menu.setAttribute("role", "listbox");
  menu.setAttribute("aria-label", labelText);
  trigger.setAttribute("aria-controls", menu.id);

  const instance = { select, wrapper, trigger, menu, labelText };
  customSelects.set(select, instance);
  trigger.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    toggleCustomSelect(instance);
  });
  trigger.addEventListener("keydown", (event) => handleCustomSelectTriggerKeydown(event, instance));
  menu.addEventListener("click", (event) => handleCustomSelectMenuClick(event, instance));
  menu.addEventListener("keydown", (event) => handleCustomSelectMenuKeydown(event, instance));
  select.addEventListener("change", () => syncCustomSelect(select));
  const optionObserver = new MutationObserver(scheduleCustomSelectRefresh);
  optionObserver.observe(select, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["disabled"],
  });
  const dialog = select.closest("dialog");
  if (dialog && !dialog.dataset.customSelectBound) {
    dialog.dataset.customSelectBound = "true";
    dialog.addEventListener("close", () => closeCustomSelect());
  }
  syncCustomSelect(select);
}

function syncCustomSelect(select) {
  const instance = customSelects.get(select);
  if (!instance) return;
  const selected = select.selectedIndex >= 0 ? select.options[select.selectedIndex] : null;
  const valueText = selected?.textContent?.replace(/\s+/g, " ").trim() || "Select an option";
  instance.trigger.querySelector(".custom-select-value").textContent = valueText;
  instance.trigger.disabled = select.disabled || !select.options.length;
  instance.trigger.classList.toggle("is-empty", !selected);
  if (!activeCustomSelect || activeCustomSelect !== instance) {
    renderCustomSelectMenu(instance);
    return;
  }
  renderCustomSelectMenu(instance);
  positionCustomSelect(instance);
}

function renderCustomSelectMenu(instance) {
  const { select, menu } = instance;
  const selectedIndex = select.selectedIndex;
  const options = [...select.options].map((option, index) => {
    const selected = index === selectedIndex;
    const disabled = option.disabled || option.parentElement?.disabled;
    const label = option.dataset.selectLabel || option.textContent.replace(/\s+/g, " ").trim();
    return `<button type="button" class="custom-select-option ${selected ? "selected" : ""}" data-option-index="${index}" role="option" aria-selected="${selected}" tabindex="-1" ${disabled ? "disabled" : ""}><span class="custom-select-option-label">${escapeHtml(label)}</span><span class="custom-select-option-check" aria-hidden="true">✓</span></button>`;
  }).join("");
  menu.innerHTML = options || `<p class="custom-select-empty">No options available</p>`;
}

function toggleCustomSelect(instance) {
  if (activeCustomSelect === instance) {
    closeCustomSelect();
    return;
  }
  closeCustomSelect();
  const host = instance.select.closest("dialog") || document.body;
  host.appendChild(instance.menu);
  instance.menu.hidden = false;
  instance.trigger.setAttribute("aria-expanded", "true");
  activeCustomSelect = instance;
  renderCustomSelectMenu(instance);
  positionCustomSelect(instance);
  const chosen = instance.menu.querySelector(`.custom-select-option.selected:not(:disabled)`)
    || instance.menu.querySelector(".custom-select-option:not(:disabled)");
  focusCustomSelectOption(instance, chosen);
}

function closeCustomSelect({ restoreFocus = false } = {}) {
  if (!activeCustomSelect) return;
  const instance = activeCustomSelect;
  activeCustomSelect = null;
  instance.menu.hidden = true;
  instance.trigger.setAttribute("aria-expanded", "false");
  if (restoreFocus) instance.trigger.focus({ preventScroll: true });
}

function positionCustomSelect(instance) {
  const { trigger, menu } = instance;
  const rect = trigger.getBoundingClientRect();
  const edge = 12;
  const gap = 6;
  const viewportWidth = document.documentElement.clientWidth;
  const viewportHeight = document.documentElement.clientHeight;
  const width = Math.min(Math.max(rect.width, 192), viewportWidth - edge * 2);
  const below = viewportHeight - rect.bottom - edge;
  const above = rect.top - edge;
  const opensUp = below < 168 && above > below;
  const available = Math.max(128, (opensUp ? above : below) - gap);
  menu.style.width = `${width}px`;
  menu.style.left = `${Math.min(Math.max(rect.left, edge), viewportWidth - width - edge)}px`;
  menu.style.top = `${opensUp ? Math.max(edge, rect.top - Math.min(available, 320) - gap) : rect.bottom + gap}px`;
  menu.style.maxHeight = `${Math.min(320, available)}px`;
  menu.classList.toggle("opens-up", opensUp);
}

function handleCustomSelectTriggerKeydown(event, instance) {
  if (!["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) return;
  event.preventDefault();
  if (activeCustomSelect !== instance) toggleCustomSelect(instance);
  const options = [...instance.menu.querySelectorAll(".custom-select-option:not(:disabled)")];
  const target = event.key === "ArrowUp" ? options.at(-1) : options[0];
  focusCustomSelectOption(instance, target);
}

function handleCustomSelectMenuClick(event, instance) {
  const option = event.target.closest("[data-option-index]");
  if (!option || option.disabled) return;
  chooseCustomSelectOption(instance, Number(option.dataset.optionIndex));
}

function handleCustomSelectMenuKeydown(event, instance) {
  if (event.key === "Escape") {
    event.preventDefault();
    closeCustomSelect({ restoreFocus: true });
    return;
  }
  if (!["ArrowDown", "ArrowUp", "Home", "End", "Enter", " "].includes(event.key)) return;
  event.preventDefault();
  const options = [...instance.menu.querySelectorAll(".custom-select-option:not(:disabled)")];
  const current = options.indexOf(document.activeElement);
  if (event.key === "Enter" || event.key === " ") {
    if (document.activeElement?.dataset.optionIndex != null) {
      chooseCustomSelectOption(instance, Number(document.activeElement.dataset.optionIndex));
    }
    return;
  }
  let next = current;
  if (event.key === "Home") next = 0;
  else if (event.key === "End") next = options.length - 1;
  else next = current < 0 ? 0 : (current + (event.key === "ArrowUp" ? -1 : 1) + options.length) % options.length;
  focusCustomSelectOption(instance, options[next]);
}

function focusCustomSelectOption(instance, option) {
  if (!option) return;
  option.focus({ preventScroll: true });
  const optionRect = option.getBoundingClientRect();
  const menuRect = instance.menu.getBoundingClientRect();
  if (optionRect.top < menuRect.top + 4) {
    instance.menu.scrollTop -= menuRect.top - optionRect.top + 4;
  } else if (optionRect.bottom > menuRect.bottom - 4) {
    instance.menu.scrollTop += optionRect.bottom - menuRect.bottom + 4;
  }
  option.scrollIntoView({ block: "nearest", inline: "nearest" });
}

function chooseCustomSelectOption(instance, index) {
  const option = instance.select.options[index];
  if (!option || option.disabled) return;
  closeCustomSelect({ restoreFocus: true });
  instance.select.selectedIndex = index;
  instance.select.dispatchEvent(new Event("change", { bubbles: true }));
  syncCustomSelect(instance.select);
}

async function loadDashboard({ quiet = false } = {}) {
  if (!quiet) setBusy(true);
  try {
    const query = new URLSearchParams();
    if (state.appId) query.set("appId", state.appId);
    query.set("country", state.country);
    state.data = await request(`/api/bootstrap?${query}`);
    state.appId = state.data.selectedAppId;
    state.country = state.data.selectedCountry || state.country;
    renderAll();
    maybeOpenOnboarding();
    monitorAutomaticSync();
  } catch (error) {
    toast(error.message, true);
  } finally {
    if (!quiet) setBusy(false);
  }
}

function renderAll() {
  renderSidebar();
  renderCountryControls();
  renderHero();
  renderCountryVisibility();
  renderRankings();
  renderHealth();
  renderCompetitorPicker();
  switchTab(state.tab, false);
  if (state.tab === "paid" && state.appId) loadAppleAds();
  if (state.tab === "compare" && state.appId) loadCompetitorMatrix();
}

function monitorAutomaticSync() {
  window.clearTimeout(state.syncPollTimer);
  state.syncPollTimer = window.setTimeout(async () => {
    try {
      const result = await request("/api/sync-status");
      const sync = result.sync || {};
      if (sync.state === "running") {
        state.syncWasRunning = true;
        el("#syncIndicator").hidden = false;
        el("#syncIndicatorText").textContent = "Syncing keywords that have not been checked in the last 24 hours…";
        monitorAutomaticSync();
        return;
      }
      el("#syncIndicator").hidden = true;
      if (state.syncWasRunning) {
        state.syncWasRunning = false;
        await loadDashboard({ quiet: true });
        if (sync.state === "error") toast(`Automatic sync failed: ${sync.error || "unknown error"}`, true);
        else toast(`Automatic sync complete: ${sync.searches || 0} searches${sync.failures ? `, ${sync.failures} failed` : ""}${sync.skipped ? `, ${sync.skipped} skipped as fresh` : ""}.`, Boolean(sync.failures));
      }
    } catch {
      state.syncPollTimer = window.setTimeout(monitorAutomaticSync, 15000);
    }
  }, state.syncWasRunning ? 5000 : 2500);
}

function renderSidebar() {
  el("#setupButton").disabled = false;
  const apps = (state.data.apps || []).filter((app) => app.active);
  el("#appList").innerHTML = apps.map((app, index) => {
    const selected = app.appleAppId === state.appId;
    const icon = app.artworkUrl
      ? `<img src="${escapeAttr(app.artworkUrl)}" alt="">`
      : escapeHtml(initials(app.name));
    return `<div class="app-list-row ${selected ? "selected" : ""}">
      <button class="app-list-item ${selected ? "active" : ""}" data-app-id="${app.appleAppId}">
        <span class="app-avatar ${index % 2 ? "alt" : ""}">${icon}</span>
        <span><span class="app-name">${escapeHtml(app.name)}</span><span class="app-meta">Tracking active</span></span>
        <span class="country-badge">${countryFlag(state.country)} ${escapeHtml(state.country.toUpperCase())}</span>
      </button>
      <button class="app-delete-button" data-delete-app-id="${app.appleAppId}" aria-label="Remove ${escapeAttr(app.name)}" title="Remove app">×</button>
    </div>`;
  }).join("") || `<div class="empty-state"><p>Add your first app to begin.</p></div>`;
  all(".app-list-item").forEach((button) => button.addEventListener("click", () => {
    closeNicheWorkspace();
    state.appId = Number(button.dataset.appId);
    state.selectedTarget = null;
    state.filter = "";
    resetCoverage();
    el("#keywordFilter").value = "";
    el("#sidebar").classList.remove("open");
    state.appleAds = null;
    state.appleAdsLoaded = false;
    state.competitorMatrix = null;
    state.competitorMatrixLoaded = false;
    loadDashboard();
  }));
}

function appListClick(event) {
  const button = event.target.closest("[data-delete-app-id]");
  if (!button) return;
  event.preventDefault();
  event.stopPropagation();
  const appId = Number(button.dataset.deleteAppId);
  const app = (state.data.apps || []).find((item) => item.appleAppId === appId);
  if (!app) return;
  state.pendingDeleteApp = appId;
  el("#deleteAppMessage").textContent = `Remove “${app.name}” from this workspace? Its ranking targets and history will remain recoverable in the local database.`;
  el("#deleteAppModal").showModal();
}

async function confirmDeleteApp() {
  if (!state.pendingDeleteApp) return;
  const appId = state.pendingDeleteApp;
  const app = (state.data.apps || []).find((item) => item.appleAppId === appId);
  state.pendingDeleteApp = null;
  el("#deleteAppModal").close();
  setBusy(true);
  try {
    await request("/api/apps/deactivate", { method: "POST", body: { appleId: appId } });
    if (state.appId === appId) state.appId = null;
    state.selectedTarget = null;
    state.filter = "";
    el("#keywordFilter").value = "";
    toast(`${app?.name || "App"} removed. Its tracking history was preserved.`);
    await loadDashboard({ quiet: true });
  } catch (error) { toast(error.message, true); }
  finally { setBusy(false); }
}

function renderCountryControls() {
  const countries = (state.data.countries || []).filter((country) => country.active);
  const compactOptions = countries.map((country) => {
    const shortLabel = `${countryFlag(country.code)} ${country.code.toUpperCase()}`;
    const menuLabel = `${shortLabel} · ${country.name}`;
    return `<option value="${country.code}" data-select-label="${escapeAttr(menuLabel)}" ${country.code === state.country ? "selected" : ""}>${shortLabel}</option>`;
  }).join("");
  const fullOptions = countries.map((country) => `<option value="${country.code}" ${country.code === state.country ? "selected" : ""}>${countryFlag(country.code)} ${country.code.toUpperCase()} · ${escapeHtml(country.name)}</option>`).join("");
  el("#countrySelect").innerHTML = compactOptions;
  el("#appCountrySelect").innerHTML = fullOptions;
  el("#deviceSelect").value = state.device;
  el("#countryChecks").innerHTML = countries.map((country) => `<label class="country-check"><input type="checkbox" name="country" value="${country.code}" ${country.code === state.country ? "checked" : ""}><span>${countryFlag(country.code)} <strong>${country.code.toUpperCase()}</strong> · ${escapeHtml(country.name)}</span></label>`).join("");
}

function openKeywordModal() {
  all('#deviceChecks input[name="device"]').forEach((input) => {
    input.checked = input.value === state.device;
  });
  resetLocalization();
  el("#keywordModal").showModal();
}

function toggleAllCountries() {
  const countries = all('#countryChecks input[name="country"]');
  const selectAll = countries.some((input) => !input.checked);
  countries.forEach((input) => { input.checked = selectAll; });
  el("#selectAllCountries").textContent = selectAll ? "Clear all" : "Select all";
  resetLocalization();
}

function resetLocalization() {
  state.localization = null;
  el("#localizationPreview").hidden = true;
  el("#localizationPreview").innerHTML = "";
  el("#keywordSubmit").textContent = "Add keywords";
}

async function localizeKeywordInput() {
  const countries = all('#countryChecks input:checked').map((input) => input.value);
  const keywords = el("#keywordInput").value.trim();
  if (!keywords) { toast("Enter at least one keyword.", true); return; }
  if (!countries.length) { toast("Select at least one storefront.", true); return; }
  const button = el("#localizeKeywordsButton");
  button.disabled = true;
  try {
    const result = await request("/api/keywords/localize", { method: "POST", body: { keywords, countries } });
    if (!result.groups.length) {
      resetLocalization();
      toast("No curated translations were found for the selected languages.", true);
      return;
    }
    state.localization = result;
    renderLocalizationPreview(result);
    el("#keywordSubmit").textContent = "Add localized keywords";
  } catch (error) { toast(error.message, true); }
  finally { button.disabled = false; }
}

function renderLocalizationPreview(result) {
  const groups = result.groups.map((group) => `<div class="localization-group">
    <div class="localization-group-head"><strong>${escapeHtml(group.language)}</strong><span>${group.countries.map(countryFlag).join(" ")}</span></div>
    <div class="translation-chips">${group.keywords.map((keyword) => `<span class="translation-chip">${escapeHtml(keyword)}</span>`).join("")}</div>
  </div>`).join("");
  const warning = result.warnings.length
    ? `<p class="localization-warning">${result.warnings.length} uncurated phrase${result.warnings.length === 1 ? "" : "s"} skipped outside English: ${[...new Set(result.warnings.map((item) => escapeHtml(item.keyword)))].join(", ")}.</p>`
    : "";
  el("#localizationPreview").innerHTML = `<div class="localization-preview-head"><strong>Localization preview</strong><span>Review before adding</span></div>${groups}${warning}`;
  el("#localizationPreview").hidden = false;
}

function renderHero() {
  const listing = state.data.listing;
  if (!state.appId || !listing) {
    el("#appHero").innerHTML = `<div class="empty-state"><div class="empty-icon">+</div><h3>No app selected</h3><p>Add an App Store app by numerical ID.</p></div>`;
    return;
  }
  const health = state.data.health;
  const auditConfigured = keywordCoverageConfigured();
  const scoreAvailable = auditConfigured && health?.score != null;
  const updated = listing.updatedAt ? relativeDate(listing.updatedAt) : "No update date";
  const ratingLabel = listing.ratingCount === 1 ? "rating" : "ratings";
  const rating = listing.averageRating ? `${listing.averageRating.toFixed(1)} (${formatCompact(listing.ratingCount)} ${ratingLabel})` : "No rating yet";
  el("#appHero").innerHTML = `<div class="hero-grid">
    <div class="hero-identity"><div class="hero-icon">${listing.artworkUrl ? `<img src="${escapeAttr(listing.artworkUrl)}" alt="">` : escapeHtml(initials(listing.name))}</div><div class="hero-copy"><h1>${escapeHtml(listing.name)}</h1><p>${escapeHtml(listing.seller || listing.bundleId || "Apple App Store")}</p></div></div>
    <div class="hero-stat"><span>Genre</span><strong>${escapeHtml(listing.genre || "—")}</strong></div>
    <div class="hero-stat"><span>Version</span><strong>${escapeHtml(listing.version || "—")}</strong></div>
    <div class="hero-stat optional"><span>Size</span><strong>${formatBytes(listing.fileSizeBytes)}</strong></div>
    <div class="hero-stat optional"><span>Price</span><strong>${escapeHtml(listing.price || "—")}</strong></div>
    <button class="score-ring ${scoreAvailable ? "" : "score-ring-setup"}" style="--score:${scoreAvailable ? health.score : 0}" id="heroHealthButton" aria-label="${scoreAvailable ? "Open listing strategy audit" : "Complete the listing audit to unlock the score"}"><strong>${scoreAvailable ? health.score : "Audit"}</strong></button>
  </div>
  <div class="hero-foot"><div class="hero-foot-group"><span>★ ${escapeHtml(rating)}</span><span>${escapeHtml(updated)}</span></div><div class="hero-foot-group"><span>${countryFlag(state.country)} ${state.country.toUpperCase()} · ${deviceName(state.device)} rankings</span>${listing.url ? `<a href="${escapeAttr(listing.url)}" target="_blank" rel="noreferrer">View on App Store ↗</a>` : ""}</div></div>`;
  el("#heroHealthButton")?.addEventListener("click", () => switchTab("health"));
}

function renderCountryVisibility() {
  const container = el("#countryVisibility");
  if (!state.data || !state.data.listing) {
    container.hidden = true;
    container.innerHTML = "";
    return;
  }
  const rankings = state.data.rankings || [];
  const cards = (state.data.countries || []).map((country) => {
    const tracked = Number(state.data.targetCounts?.[`${country.code}:${state.device}`] || 0);
    const top10 = rankings.filter((row) => row.country === country.code && row.device === state.device && row.found && row.rank != null && row.rank <= 10).length;
    return { ...country, tracked, top10 };
  }).filter((country) => country.tracked > 0).sort((a, b) => (
    Number(b.code === state.country) - Number(a.code === state.country)
    || b.top10 - a.top10
    || b.tracked - a.tracked
    || a.name.localeCompare(b.name)
  ));
  container.hidden = cards.length === 0;
  if (!cards.length) {
    container.innerHTML = "";
    return;
  }
  container.innerHTML = cards.map((country) => {
    const percent = Math.round((country.top10 / country.tracked) * 100);
    const tone = country.top10 === 0 ? "zero" : percent >= 50 ? "strong" : "some";
    return `<button class="country-rank-card ${tone} ${country.code === state.country ? "selected" : ""}" data-country-card="${escapeAttr(country.code)}" ${country.active ? "" : "disabled"} aria-pressed="${country.code === state.country}" aria-label="${escapeAttr(country.name)}: ${country.top10} of ${country.tracked} ${deviceName(state.device)} keywords in the Top 10">
      <span class="country-rank-head"><span class="country-rank-flag">${countryFlag(country.code)}</span><strong>${escapeHtml(country.name)}</strong></span>
      <span class="country-rank-count"><strong>${country.top10}</strong><span>/${country.tracked}</span></span>
      <span class="country-rank-note">in the Top 10</span>
      <span class="country-rank-progress" aria-hidden="true"><i style="width:${percent}%"></i></span>
    </button>`;
  }).join("");
}

async function countryVisibilityClick(event) {
  const button = event.target.closest("[data-country-card]");
  if (!button || button.disabled) return;
  if (button.dataset.countryCard === state.country) {
    state.tab = "rankings";
    switchTab("rankings", false);
    el("#rankingsPanel").scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  state.country = button.dataset.countryCard;
  state.selectedTarget = null;
  state.filter = "";
  state.tab = "rankings";
  resetCoverage();
  el("#keywordFilter").value = "";
  renderCountryControls();
  renderHero();
  renderCountryVisibility();
  renderRankings();
  switchTab("rankings", false);
  el("#rankingsPanel").scrollIntoView({ behavior: "smooth", block: "start" });
  await loadDashboard({ quiet: true });
}

function filteredRows() {
  return countryRows().filter((row) => !state.filter || row.keyword.toLowerCase().includes(state.filter));
}

function countryRows() {
  return (state.data.rankings || []).filter((row) => row.country === state.country && row.device === state.device);
}

function rankingHeaderClick(event) {
  const button = event.target.closest("[data-rank-sort]");
  if (!button) return;
  const field = button.dataset.rankSort;
  if (state.rankSortField === field) {
    state.rankSortDirection = state.rankSortDirection === "asc" ? "desc" : "asc";
  } else {
    state.rankSortField = field;
    state.rankSortDirection = "asc";
  }
  renderRankings();
}

function rankingSortValue(row, field) {
  if (field === "keyword") return row.keyword.toLocaleLowerCase();
  if (field === "country") return row.country;
  if (field === "device") return row.device;
  if (field === "rank") return row.rank ?? null;
  if (field === "volume") return row.volumeEstimate ?? null;
  if (field === "difficulty") return row.difficultyEstimate ?? null;
  if (field === "top5") return (row.topApps || []).map((app) => app.name).join(" ").toLocaleLowerCase();
  if (field === "change") {
    if (row.change === "NEW") return Number.POSITIVE_INFINITY;
    if (row.change === "LOST") return Number.NEGATIVE_INFINITY;
    const value = Number.parseFloat(row.change);
    return Number.isFinite(value) ? value : 0;
  }
  if (field === "signal") return row.opportunity.toLocaleLowerCase();
  if (field === "updated") return new Date(row.checkedAt).getTime();
  return row.keyword.toLocaleLowerCase();
}

function sortRankingRows(rows) {
  const field = state.rankSortField;
  const direction = state.rankSortDirection === "desc" ? -1 : 1;
  return [...rows].sort((left, right) => {
    const leftValue = rankingSortValue(left, field);
    const rightValue = rankingSortValue(right, field);
    if (leftValue == null && rightValue == null) return left.keyword.localeCompare(right.keyword);
    if (leftValue == null) return 1;
    if (rightValue == null) return -1;
    const comparison = typeof leftValue === "number"
      ? leftValue - rightValue
      : String(leftValue).localeCompare(String(rightValue), undefined, { numeric: true });
    return comparison === 0
      ? left.keyword.localeCompare(right.keyword)
      : comparison * direction;
  });
}

function updateRankSortHeaders() {
  all("#rankingsHeader [data-rank-sort-column]").forEach((cell) => {
    const field = cell.dataset.rankSortColumn;
    const active = field === state.rankSortField;
    const direction = active ? state.rankSortDirection : null;
    cell.setAttribute("aria-sort", direction === "asc" ? "ascending" : direction === "desc" ? "descending" : "none");
    const button = cell.querySelector("[data-rank-sort]");
    if (!button) return;
    button.classList.toggle("active", active);
    button.querySelector("span").textContent = direction === "asc" ? "↑" : direction === "desc" ? "↓" : "↕";
    button.title = active
      ? `Sort ${button.textContent.replace(/[↕↑↓]/g, "").trim()} ${direction === "asc" ? "descending" : "ascending"}`
      : `Sort by ${button.textContent.replace(/[↕↑↓]/g, "").trim()}`;
  });
}

function renderRankings() {
  if (!state.data) return;
  const rows = sortRankingRows(filteredRows());
  updateRankSortHeaders();
  const metricRows = countryRows();
  const found = metricRows.filter((row) => row.found && row.rank != null);
  const ranks = found.map((row) => row.rank);
  const trackedCount = state.data.targetCounts?.[`${state.country}:${state.device}`] || 0;
  const trends = state.data.metricTrends?.[`${state.country}:${state.device}`] || {};
  const trends30d = state.data.metricTrends30d?.[`${state.country}:${state.device}`] || {};
  const metrics = [
    { label: "Top 10", value: ranks.filter((rank) => rank <= 10).length, note: "Defend visibility", icon: "↑", trend: trends.top10, trend30d: trends30d.top10, threshold: 10 },
    { label: "Top 50", value: ranks.filter((rank) => rank <= 50).length, note: "Growth range", icon: "◎", trend: trends.top50, trend30d: trends30d.top50, threshold: 50 },
    { label: "Average rank", value: ranks.length ? (ranks.reduce((a, b) => a + b, 0) / ranks.length).toFixed(1) : "—", note: "Found keywords only", icon: "∿", trend: trends.averageRank, trend30d: trends30d.averageRank, series: "averageRank" },
  ];
  el("#metrics").innerHTML = metrics.map((metric) => {
    const interactive = Boolean(metric.threshold || metric.series);
    const tag = interactive ? "button" : "article";
    const attributes = interactive
      ? ` type="button" data-metric-series="${metric.threshold ? `top${metric.threshold}` : metric.series}" aria-label="View ${metric.label} rank history"`
      : "";
    return `<${tag} class="metric ${interactive ? "metric-clickable" : ""}"${attributes}><span class="metric-label">${metric.label}<b>${metric.icon}</b></span><div class="metric-value-row"><strong class="metric-value">${metric.value}</strong><span class="metric-trend-stack">${metricTrend(metric.trend, metric.label, 7)}${metricTrend(metric.trend30d, metric.label, 30)}</span></div><span class="metric-note">${metric.note}</span></${tag}>`;
  }).join("");

  el("#rankingsBody").innerHTML = rows.map((row) => {
    const changeClass = row.change === "NEW" ? "new" : row.change === "LOST" ? "lost" : row.change.startsWith("+") ? "up" : row.change.startsWith("-") ? "down" : "flat";
    const signalClass = row.opportunity.startsWith("Defend") ? "defend" : row.opportunity.includes("Growth") ? "growth" : row.opportunity.includes("visible") ? "absent" : "";
    const volumeTone = row.volumeEstimate == null ? "" : row.volumeEstimate >= 35 ? " volume-strong" : row.volumeEstimate >= 15 ? " volume-mid" : " volume-low";
    const difficultyTone = row.difficultyEstimate == null ? "" : row.difficultyEstimate >= 67 ? " difficulty-hard" : row.difficultyEstimate >= 34 ? " difficulty-mid" : " difficulty-low";
    const checkState = state.checkingTargets.has(row.targetId) ? "checking" : state.queuedCheckTargets.has(row.targetId) ? "queued" : "";
    const rankMarkup = checkState === "checking"
      ? `<span class="row-check-state checking"><i></i>Checking</span>`
      : checkState === "queued"
        ? `<span class="row-check-state queued">Queued</span>`
        : row.status === "error"
          ? `<span class="row-check-state error" title="${escapeAttr(row.error || "Apple check failed")}">Check failed</span>`
          : `<span class="rank-number ${row.rank && row.rank <= 10 ? "top" : ""}">${row.found ? `#${row.rank}` : `>${row.resultLimit}`}</span>`;
    return `<tr data-target-id="${row.targetId}" class="${row.targetId === state.selectedTarget ? "selected" : ""} ${checkState ? `row-${checkState}` : ""}">
      <td class="keyword-cell" title="${escapeAttr(row.keyword)}">${escapeHtml(row.keyword)}</td><td class="country-cell"><span class="country-badge">${countryFlag(row.country)} ${row.country.toUpperCase()}</span></td><td class="device-cell"><span class="device-badge ${escapeAttr(row.device)}">${deviceIcon(row.device)} ${deviceName(row.device)}</span></td>
      <td class="rank-cell">${rankMarkup}</td>
      <td class="estimate-cell volume-cell${volumeTone}">${estimateCell(row.volumeEstimate, "volume", row.estimateSampleSize)}</td>
      <td class="estimate-cell difficulty-cell${difficultyTone}">${estimateCell(row.difficultyEstimate, "difficulty", row.estimateSampleSize)}</td>
      <td class="top-apps-cell">${topAppsCell(row.topApps)}</td>
      <td class="movement-cell"><span class="movement ${changeClass}">${escapeHtml(row.change)}</span></td><td class="signal-cell"><span class="signal ${signalClass}">${escapeHtml(shortOpportunity(row.opportunity))}</span></td>
      <td class="updated-cell">${formatDate(row.checkedAt)}</td><td class="action-cell"><button class="row-action" data-delete-target="${row.targetId}" title="Stop tracking">×</button></td>
    </tr>`;
  }).join("");
  hideTopAppTooltip();
  const emptyTitle = el("#rankingsEmpty h3");
  const emptyCopy = el("#rankingsEmpty p");
  if (state.filter) {
    emptyTitle.textContent = "No matching keywords";
    emptyCopy.textContent = "Try a different keyword filter.";
  } else if (trackedCount > 0) {
    emptyTitle.textContent = "No checks yet";
    emptyCopy.textContent = "Run a check to retrieve the first rankings for this storefront.";
  } else {
    emptyTitle.textContent = "No tracking targets";
    emptyCopy.textContent = "Add a keyword to start tracking this storefront.";
  }
  el("#rankingsEmpty").hidden = rows.length > 0;
  el("#rankingsBody").closest(".table-scroll").hidden = rows.length === 0;
  if (state.selectedTarget && rows.some((row) => row.targetId === state.selectedTarget)) renderHistory();
  else el("#historyCard").hidden = true;
  renderOverallRankHistory();
  renderLosingTo();
}

function topAppsCell(apps = []) {
  if (!apps.length) return `<span class="top-apps-empty">—</span>`;
  const icons = apps.map((app) => {
    const fallback = escapeHtml(initials(app.name));
    const image = app.artworkUrl
      ? `<img src="${escapeAttr(app.artworkUrl)}" alt="" loading="lazy">`
      : "";
    return `<button type="button" class="top-app-preview" aria-label="Top result ${app.position}: ${escapeAttr(app.name)}. Open competitor actions." data-app-id="${app.appId}" data-app-name="${escapeAttr(app.name)}" data-artwork-url="${escapeAttr(app.artworkUrl || "")}"><span class="top-app-avatar">${fallback}${image}</span></button>`;
  }).join("");
  return `<span class="top-app-stack"><span class="top-apps-label">Top 5</span>${icons}</span>`;
}

function topAppPreviewFromEvent(event) {
  const preview = event.target.closest(".top-app-preview");
  return preview && el("#rankingsBody").contains(preview) ? preview : null;
}

function showTopAppTooltip(event) {
  const preview = topAppPreviewFromEvent(event);
  if (!preview) return;
  const tooltip = el("#appTooltip");
  tooltip.textContent = preview.dataset.appName;
  tooltip.hidden = false;
  const rect = preview.getBoundingClientRect();
  const width = tooltip.offsetWidth;
  const left = Math.max(8, Math.min(window.innerWidth - width - 8, rect.left + rect.width / 2 - width / 2));
  const above = rect.top - tooltip.offsetHeight - 8;
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${above >= 8 ? above : rect.bottom + 8}px`;
}

function hideTopAppTooltip(event) {
  if (event?.relatedTarget && event.currentTarget?.contains?.(event.relatedTarget)) return;
  el("#appTooltip").hidden = true;
}

function openTopAppMenu(preview) {
  hideTopAppTooltip();
  const appId = Number(preview.dataset.appId);
  const name = preview.dataset.appName;
  const artworkUrl = preview.dataset.artworkUrl;
  state.pendingTopApp = { appleAppId: appId, name, artworkUrl };
  el("#topAppMenuName").textContent = name;
  el("#topAppMenuArtwork").innerHTML = artworkUrl
    ? `<img src="${escapeAttr(artworkUrl)}" alt="">`
    : escapeHtml(initials(name));
  const addButton = el("#addTopAppCompetitor");
  const isPrimary = appId === state.appId;
  addButton.disabled = isPrimary;
  addButton.textContent = isPrimary ? "Current primary app" : "+ Add to competitors";
  const menu = el("#topAppMenu");
  menu.hidden = false;
  const rect = preview.getBoundingClientRect();
  const width = menu.offsetWidth;
  const left = Math.max(8, Math.min(window.innerWidth - width - 8, rect.left + rect.width / 2 - width / 2));
  const below = rect.bottom + 8;
  const top = below + menu.offsetHeight <= window.innerHeight - 8
    ? below
    : Math.max(8, rect.top - menu.offsetHeight - 8);
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
}

function hideTopAppMenu() {
  el("#topAppMenu").hidden = true;
  state.pendingTopApp = null;
}

async function addPendingTopAppCompetitor() {
  const competitor = state.pendingTopApp;
  if (!competitor || !state.appId) return;
  hideTopAppMenu();
  setBusy(true);
  try {
    await request("/api/competitors/add", {
      method: "POST",
      body: {
        appId: state.appId,
        competitorAppId: competitor.appleAppId,
        name: competitor.name,
        artworkUrl: competitor.artworkUrl || null,
      },
    });
    state.tab = "compare";
    state.competitorMatrixLoaded = false;
    switchTab("compare", false);
    await loadCompetitorMatrix();
    toast(`${competitor.name} added to the competitor matrix. Use Refresh rankings to load its positions.`);
  } catch (error) {
    toast(error.message, true);
  } finally {
    setBusy(false);
  }
}

async function rankingClick(event) {
  const remove = event.target.closest("[data-delete-target]");
  if (remove) {
    event.stopPropagation();
    state.pendingDeactivateTarget = Number(remove.dataset.deleteTarget);
    el("#confirmModal").showModal();
    return;
  }
  const topApp = event.target.closest(".top-app-preview");
  if (topApp) {
    event.stopPropagation();
    openTopAppMenu(topApp);
    return;
  }
  const row = event.target.closest("tr[data-target-id]");
  if (!row) return;
  state.selectedTarget = Number(row.dataset.targetId);
  renderRankings();
  renderHistory();
  el("#historyCard").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function confirmDeactivate() {
  if (!state.pendingDeactivateTarget) return;
  const targetId = state.pendingDeactivateTarget;
  state.pendingDeactivateTarget = null;
  el("#confirmModal").close();
  await mutate("/api/targets/deactivate", { targetId }, "Tracking target deactivated");
}

function renderHistory() {
  const ranking = (state.data.rankings || []).find((row) => row.targetId === state.selectedTarget);
  const points = (state.data.history || []).filter((point) => point.targetId === state.selectedTarget && point.found && point.rank != null);
  if (!ranking) { el("#historyCard").hidden = true; return; }
  el("#historyCard").hidden = false;
  el("#historyTitle").textContent = `${ranking.keyword} · ${countryFlag(ranking.country)} ${ranking.country.toUpperCase()} · ${deviceName(ranking.device)}`;
  const host = el("#historyChart");
  if (!points.length) { host.innerHTML = `<div class="chart-empty">Run another check later to build a rank history.</div>`; return; }
  const width = 920, height = 250, left = 48, right = 18, top = 22, bottom = 34;
  const maxRank = Math.max(10, ...points.map((point) => point.rank));
  const minTime = Math.min(...points.map((point) => +new Date(point.checkedAt)));
  const maxTime = Math.max(...points.map((point) => +new Date(point.checkedAt)));
  const x = (value, index) => points.length === 1 ? width / 2 : left + ((+new Date(value) - minTime) / Math.max(maxTime - minTime, 1)) * (width - left - right);
  const y = (rank) => top + ((rank - 1) / Math.max(maxRank - 1, 1)) * (height - top - bottom);
  const coords = points.map((point, index) => `${x(point.checkedAt, index)},${y(point.rank)}`).join(" ");
  const guides = [1, Math.ceil(maxRank / 2), maxRank].map((rank) => `<line x1="${left}" y1="${y(rank)}" x2="${width-right}" y2="${y(rank)}" stroke="#e5e5de"/><text x="${left-10}" y="${y(rank)+4}" text-anchor="end" fill="#777872" font-size="10">#${rank}</text>`).join("");
  const dots = points.map((point, index) => `<g><circle cx="${x(point.checkedAt,index)}" cy="${y(point.rank)}" r="5" fill="#ff5b2e" stroke="#fff" stroke-width="3"><title>${formatDate(point.checkedAt)} · #${point.rank}</title></circle></g>`).join("");
  const labels = points.length > 1 ? `<text x="${left}" y="${height-7}" fill="#777872" font-size="10">${formatDate(points[0].checkedAt)}</text><text x="${width-right}" y="${height-7}" text-anchor="end" fill="#777872" font-size="10">${formatDate(points.at(-1).checkedAt)}</text>` : "";
  host.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Rank history; higher is better">${guides}<polyline points="${coords}" fill="none" stroke="#ff5b2e" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>${dots}${labels}</svg>`;
}

function resetCoverage() {
  window.clearTimeout(state.coverageSaveTimer);
  state.coverageSaveRevision += 1;
  state.coverageStep = 1;
  state.coverageCountry = null;
  state.coverageDraft = null;
  state.coverageAnalysis = null;
  state.coverageStrategy = null;
  state.coverageGoal = null;
  state.coverageBrand = "";
}

function renderListingCoverage() {
  const card = el("#coverageCard");
  if (!state.appId || !state.data?.listing) {
    card.innerHTML = `<div class="empty-state"><h3>Choose an app to analyse listing coverage.</h3></div>`;
    return;
  }
  const savedMetadata = state.data.listingMetadata;
  if (!state.coverageGoal) {
    state.coverageGoal = savedMetadata?.channelGoal || "aso_seo_aeo";
  }
  if (!state.coverageBrand) {
    state.coverageBrand = savedMetadata?.brandTerm || inferCoverageBrand(savedMetadata?.name || state.data.listing.name || "");
  }
  if (!state.coverageCountry) state.coverageCountry = state.country;
  if (state.coverageStep >= 2 && !state.coverageDraft) {
    state.coverageDraft = {
      name: savedMetadata?.name || state.data.listing.name || "",
      subtitle: savedMetadata?.subtitle || "",
      keywords: savedMetadata?.keywords || "",
    };
  }
  const progress = [1, 2, 3].map((step) => `<li class="${state.coverageStep === step ? "current" : state.coverageStep > step ? "complete" : ""}"><span>${state.coverageStep > step ? "✓" : step}</span>${["Goal & market", "Listing metadata", "Strategy audit"][step - 1]}</li>`).join("");
  let body = "";
  if (state.coverageStep === 1) {
    const options = (state.data.countries || []).filter((country) => country.active).map((country) => `<option value="${country.code}" ${country.code === state.coverageCountry ? "selected" : ""}>${countryFlag(country.code)} ${country.code.toUpperCase()} · ${escapeHtml(country.name)}</option>`).join("");
    body = `<div class="coverage-setup">
      <div class="coverage-setup-copy"><p class="section-kicker">Step 1 · Strategy</p><h3>What is your primary growth strategy?</h3><p>Choose how discovery should influence the title and the terms you prioritize.</p></div>
      <div class="coverage-goal-list" role="radiogroup" aria-label="Primary distribution strategy">
        ${coverageGoalOption("aso_seo_aeo", "ASO / SEO / AEO", "Lead with a generic keyword phrase, then close with the brand.", "Discovery-led")}
        ${coverageGoalOption("ugc_ads", "UGC / Ads", "Lead with the brand and prioritize ranking for branded searches.", "Brand-led")}
      </div>
      <div class="coverage-setup-fields">
        <label class="field"><span>Brand term or branded phrase</span><input id="coverageBrandTerm" maxlength="255" required value="${escapeAttr(state.coverageBrand)}" placeholder="AstroLingo"><small>Used only to verify title ordering. Punctuation and case are ignored.</small></label>
        <label class="field coverage-country-field"><span>Main listing storefront</span><select id="coverageCountrySelect">${options}</select></label>
      </div>
      <div class="coverage-actions"><button type="button" class="button button-primary" id="coverageLoadButton">Continue to metadata</button></div>`;
  } else if (state.coverageStep === 2) {
    const draft = state.coverageDraft;
    body = `<div class="coverage-intro"><div class="coverage-step-number">2</div><div><h3>Review the indexed listing fields</h3><p>Apple’s public API supplies the app name. Subtitle and keyword field are not exposed publicly, so paste them from App Store Connect. They stay in your local SQLite database.</p></div><span class="coverage-goal-badge">${escapeHtml(state.coverageGoal === "ugc_ads" ? "UGC / Ads" : "ASO / SEO / AEO")}</span></div>
      <form id="coverageForm" class="coverage-form">
        <label class="field"><span class="coverage-field-label">Name <small id="coverageNameCount">${draft.name.length}/30</small></span><input id="coverageName" maxlength="30" required value="${escapeAttr(draft.name)}"></label>
        <label class="field"><span class="coverage-field-label">Subtitle <small id="coverageSubtitleCount">${draft.subtitle.length}/30</small></span><input id="coverageSubtitle" maxlength="30" value="${escapeAttr(draft.subtitle)}" placeholder="Paste the localized subtitle"></label>
        <label class="field"><span class="coverage-field-label">Keyword field <small id="coverageKeywordsCount">${draft.keywords.length}/100</small></span><input id="coverageKeywords" maxlength="100" value="${escapeAttr(draft.keywords)}" placeholder="keyword one, keyword two, keyword three"><small>Comma-separated. This is the App Store keyword field, not Apple search volume.</small></label>
        <div class="coverage-actions"><button type="button" class="button button-ghost" id="coverageBackButton">Back</button><button type="submit" class="button button-primary" id="coverageAnalyzeButton">Analyse strategy</button></div>
      </form>`;
  } else {
    const analysis = state.coverageAnalysis;
    const strategy = state.coverageStrategy;
    const matches = analysis.matched || [];
    body = `<div class="coverage-intro"><div class="coverage-step-number">3</div><div><h3>Listing strategy audit</h3><p>${escapeHtml(strategy.goal_label)} · ${countryFlag(state.coverageCountry)} ${escapeHtml(state.coverageCountry.toUpperCase())} · ${deviceName(state.device)}</p></div><span class="coverage-goal-badge" id="coverageSaveStatus">Saved</span></div>
      ${coverageLiveForm(state.coverageDraft, strategy)}
      <div id="coverageLiveResults">${coverageResultsMarkup(analysis, strategy)}</div>
      <div class="coverage-actions"><button type="button" class="button button-ghost" id="coverageEditButton">Edit metadata</button></div>`;
  }
  card.innerHTML = `<div class="coverage-head"><div><h2>Keyword coverage</h2><p>Compare the metadata you plan to target with keywords already tracked for this app.</p></div></div><ol class="coverage-progress">${progress}</ol>${body}`;
  if (state.coverageStep === 1) {
    el("#coverageLoadButton").addEventListener("click", continueCoverageGoal);
    all('input[name="coverageGoal"]').forEach((input) => {
      input.addEventListener("change", () => {
        all(".coverage-goal-option").forEach((option) => {
          option.classList.toggle("selected", Boolean(option.querySelector("input:checked")));
        });
      });
    });
  } else if (state.coverageStep === 2) {
    el("#coverageBackButton").addEventListener("click", () => {
      state.coverageStep = 1;
      renderListingCoverage();
    });
    el("#coverageForm").addEventListener("submit", analyseCoverage);
    bindCoverageCounter("#coverageName", "#coverageNameCount");
    bindCoverageCounter("#coverageSubtitle", "#coverageSubtitleCount");
    bindCoverageCounter("#coverageKeywords", "#coverageKeywordsCount");
  } else {
    bindLiveCoverageEditor();
    el("#coverageEditButton").addEventListener("click", () => {
      window.clearTimeout(state.coverageSaveTimer);
      syncCoverageDraftFromLiveForm();
      state.coverageStep = 2;
      renderListingCoverage();
    });
  }
}

function coverageLiveForm(draft, strategy) {
  const context = coverageHighlightContext(
    draft.name,
    draft.subtitle,
    draft.keywords,
    strategy.brand_term || state.coverageBrand,
  );
  return `<form id="coverageLiveForm" class="coverage-form coverage-live-form">
    <label class="field coverage-token-field"><span class="coverage-field-label">Name <small id="coverageLiveNameCount">${draft.name.length}/30</small></span><span class="coverage-token-shell"><span class="coverage-token-mirror" id="coverageLiveNameMirror" aria-hidden="true">${coverageFieldHighlightMarkup(draft.name, context)}</span><input id="coverageLiveName" maxlength="30" required value="${escapeAttr(draft.name)}"></span></label>
    <label class="field coverage-token-field"><span class="coverage-field-label">Subtitle <small id="coverageLiveSubtitleCount">${draft.subtitle.length}/30</small></span><span class="coverage-token-shell"><span class="coverage-token-mirror" id="coverageLiveSubtitleMirror" aria-hidden="true">${coverageFieldHighlightMarkup(draft.subtitle, context)}</span><input id="coverageLiveSubtitle" maxlength="30" value="${escapeAttr(draft.subtitle)}" placeholder="Paste the localized subtitle"></span></label>
    <label class="field coverage-token-field"><span class="coverage-field-label">Keyword field <small id="coverageLiveKeywordsCount">${draft.keywords.length}/100</small></span><span class="coverage-token-shell"><span class="coverage-token-mirror" id="coverageLiveKeywordsMirror" aria-hidden="true">${coverageKeywordFieldHighlightMarkup(draft.keywords, context)}</span><input id="coverageLiveKeywords" maxlength="100" value="${escapeAttr(draft.keywords)}" placeholder="keyword one, keyword two"></span><small>Changes recalculate the audit automatically and save locally after a short pause.</small></label>
    <div class="coverage-highlight-legend coverage-input-legend"><span class="coverage-token-unique">Unique keyword</span><span class="coverage-token-brand">Brand term</span><span class="coverage-token-repeated">Repeated</span></div>
  </form>`;
}

function coverageResultsMarkup(analysis, strategy) {
  const matches = analysis.matched || [];
  const untrackedMatches = analysis.untracked_matches || [];
  return `<div class="coverage-principles">
      ${coveragePrincipleCard(strategy.no_repetition)}
      ${coveragePrincipleCard(strategy.title_order)}
    </div>
    <div class="coverage-summary">
      <div><span>Targeted terms</span><strong>${analysis.target_terms}</strong><small>${analysis.keyword_field_terms} keyword-field entries</small></div>
      <div><span>Tracked in listing</span><strong>${analysis.tracked_matches}</strong><small>keywords found in metadata</small></div>
      <div><span>Already ranking</span><strong>${analysis.ranked_keywords}</strong><small>with a returned position</small></div>
      <div><span>Not ranking</span><strong>${analysis.unranked_keywords}</strong><small>outside the result window</small></div>
    </div>
    <div class="coverage-match-sections">
      <section class="coverage-matched coverage-match-group"><strong>Tracked keyword matches <span>${matches.length}</span></strong>${matches.length ? matches.map((item) => `<div class="coverage-match ${item.found ? "ranked" : "unranked"}"><span>${escapeHtml(item.keyword)}</span><small>${item.sources.map(escapeHtml).join(" · ")}</small><b>${item.found ? `#${item.rank}` : `>${item.result_limit}`}</b></div>`).join("") : `<p>No currently tracked keywords appear in this metadata.</p>`}</section>
      <section class="coverage-untracked coverage-match-group"><strong>Untracked keyword matches <span>${untrackedMatches.length}</span></strong>${untrackedMatches.length ? untrackedMatches.map((item) => `<div class="coverage-match untracked"><span>${escapeHtml(item.keyword)}</span><small>${item.sources.map(escapeHtml).join(" · ")}</small><b>Untracked</b></div>`).join("") : `<p>Every detected metadata term is already tracked.</p>`}</section>
    </div>`;
}

function coverageHighlightContext(name, subtitle, keywords, brandTerm) {
  const counts = new Map();
  [name, subtitle, keywords].forEach((value) => {
    coverageAnalysisTokens(value).forEach((token) => counts.set(token, (counts.get(token) || 0) + 1));
  });
  return {
    counts,
    brandWords: new Set(coverageAnalysisTokens(brandTerm)),
  };
}

function coverageFieldHighlightMarkup(value, context) {
  const source = String(value || "");
  const parts = [];
  let cursor = 0;
  for (const match of source.matchAll(/[^\W_]+(?:['’][^\W_]+)?/gu)) {
    const index = match.index ?? cursor;
    parts.push(escapeHtml(source.slice(cursor, index)));
    const tokens = coverageAnalysisTokens(match[0]);
    if (!tokens.length) {
      parts.push(escapeHtml(match[0]));
    } else {
      const tone = tokens.some((token) => (context.counts.get(token) || 0) > 1)
        ? "repeated"
        : tokens.some((token) => context.brandWords.has(token))
          ? "brand"
          : "unique";
      parts.push(`<mark class="coverage-token-${tone}">${escapeHtml(match[0])}</mark>`);
    }
    cursor = index + match[0].length;
  }
  parts.push(escapeHtml(source.slice(cursor)));
  return parts.join("");
}

function coverageKeywordFieldHighlightMarkup(value, context) {
  return String(value || "").split(/([,\n]+)/).map((part) => {
    if (!part || /^[,\n]+$/.test(part)) return escapeHtml(part);
    const tokens = coverageAnalysisTokens(part);
    if (!tokens.length) return escapeHtml(part);
    const leading = part.match(/^\s*/)?.[0] || "";
    const trailing = part.match(/\s*$/)?.[0] || "";
    const content = part.slice(leading.length, part.length - trailing.length);
    const tone = tokens.some((token) => (context.counts.get(token) || 0) > 1)
      ? "repeated"
      : tokens.some((token) => context.brandWords.has(token))
        ? "brand"
        : "unique";
    return `${escapeHtml(leading)}<mark class="coverage-token-${tone}">${escapeHtml(content)}</mark>${escapeHtml(trailing)}`;
  }).join("");
}

function renderCoverageInputHighlights(strategy = state.coverageStrategy) {
  if (!el("#coverageLiveForm")) return;
  const context = coverageHighlightContext(
    el("#coverageLiveName").value,
    el("#coverageLiveSubtitle").value,
    el("#coverageLiveKeywords").value,
    strategy?.brand_term || state.coverageBrand,
  );
  el("#coverageLiveNameMirror").innerHTML = coverageFieldHighlightMarkup(el("#coverageLiveName").value, context);
  el("#coverageLiveSubtitleMirror").innerHTML = coverageFieldHighlightMarkup(el("#coverageLiveSubtitle").value, context);
  el("#coverageLiveKeywordsMirror").innerHTML = coverageKeywordFieldHighlightMarkup(el("#coverageLiveKeywords").value, context);
  syncCoverageInputScrolls();
}

function syncCoverageInputScrolls() {
  ["#coverageLiveName", "#coverageLiveSubtitle", "#coverageLiveKeywords"].forEach((selector) => {
    const input = el(selector);
    const mirror = input.closest(".coverage-token-shell").querySelector(".coverage-token-mirror");
    mirror.scrollLeft = input.scrollLeft;
  });
}

function coverageAnalysisTokens(value) {
  const stopWords = new Set(["a", "an", "and", "app", "de", "des", "du", "el", "en", "et", "for", "la", "le", "les", "of", "para", "por", "the", "to", "un", "une", "your"]);
  return String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .match(/[a-z0-9]+/g)?.filter((token) => token.length > 1 && !stopWords.has(token)) || [];
}

function bindLiveCoverageEditor() {
  const fields = [
    ["#coverageLiveName", "#coverageLiveNameCount"],
    ["#coverageLiveSubtitle", "#coverageLiveSubtitleCount"],
    ["#coverageLiveKeywords", "#coverageLiveKeywordsCount"],
  ];
  fields.forEach(([inputSelector, countSelector]) => {
    const input = el(inputSelector);
    input.addEventListener("input", () => {
      el(countSelector).textContent = `${input.value.length}/${input.maxLength}`;
      renderCoverageInputHighlights();
      window.requestAnimationFrame(syncCoverageInputScrolls);
      scheduleCoverageLiveSave();
    });
    ["scroll", "keydown", "keyup", "click", "select", "focus"].forEach((eventName) => {
      input.addEventListener(eventName, () => window.requestAnimationFrame(syncCoverageInputScrolls));
    });
  });
  renderCoverageInputHighlights();
}

function scheduleCoverageLiveSave() {
  window.clearTimeout(state.coverageSaveTimer);
  state.coverageSaveTimer = window.setTimeout(saveLiveListingMetadata, 550);
}

function syncCoverageDraftFromLiveForm() {
  if (!el("#coverageLiveForm")) return;
  state.coverageDraft = {
    name: el("#coverageLiveName").value.trim(),
    subtitle: el("#coverageLiveSubtitle").value.trim(),
    keywords: el("#coverageLiveKeywords").value.trim(),
  };
}

async function saveLiveListingMetadata() {
  if (!el("#coverageLiveForm")) return;
  const revision = ++state.coverageSaveRevision;
  const draft = {
    name: el("#coverageLiveName").value.trim(),
    subtitle: el("#coverageLiveSubtitle").value.trim(),
    keywords: el("#coverageLiveKeywords").value.trim(),
  };
  if (!draft.name) {
    el("#coverageSaveStatus").textContent = "Name required";
    return;
  }
  el("#coverageSaveStatus").textContent = "Saving…";
  try {
    const result = await request("/api/listing-metadata", {
      method: "POST",
      body: {
        appId: state.appId,
        country: state.coverageCountry,
        device: state.device,
        ...draft,
        goal: state.coverageGoal,
        brandTerm: state.coverageBrand,
      },
    });
    if (revision !== state.coverageSaveRevision) return;
    state.coverageDraft = draft;
    state.coverageAnalysis = result.analysis;
    state.coverageStrategy = result.strategy;
    state.data.listingMetadata = result.metadata;
    if (result.health) {
      state.data.health = result.health;
      renderHero();
      renderHealthScore();
      renderHealthSuggestions();
    }
    renderCoverageInputHighlights(result.strategy);
    el("#coverageLiveResults").innerHTML = coverageResultsMarkup(result.analysis, result.strategy);
    el("#coverageSaveStatus").textContent = "Saved live";
  } catch (error) {
    if (revision === state.coverageSaveRevision) {
      el("#coverageSaveStatus").textContent = "Save failed";
      toast(error.message, true);
    }
  }
}

function coverageGoalOption(value, label, detail, routeLabel) {
  const checked = state.coverageGoal === value;
  return `<label class="coverage-goal-option ${checked ? "selected" : ""}"><input type="radio" name="coverageGoal" value="${value}" ${checked ? "checked" : ""}><span class="coverage-goal-radio" aria-hidden="true"></span><span class="coverage-goal-copy"><strong>${escapeHtml(label)}</strong><small>${escapeHtml(detail)}</small></span><span class="coverage-goal-route">${escapeHtml(routeLabel)}</span></label>`;
}

function coveragePrincipleCard(principle) {
  const tone = principle.passed === true ? "pass" : principle.passed === false ? "fail" : "pending";
  const label = principle.passed === true ? "Pass" : principle.passed === false ? "Review" : "Needs input";
  return `<article class="coverage-principle ${tone}"><div><span>${tone === "pass" ? "✓" : tone === "fail" ? "!" : "?"}</span><strong>${escapeHtml(principle.label)}</strong></div><p>${escapeHtml(principle.detail)}</p><small>${label}</small></article>`;
}

function inferCoverageBrand(value) {
  const parts = value.split(/\s*[:|–—-]\s*/).filter(Boolean);
  return parts.length > 1 ? parts.at(-1) : "";
}

function bindCoverageCounter(inputSelector, counterSelector) {
  const input = el(inputSelector);
  const counter = el(counterSelector);
  input.addEventListener("input", () => {
    counter.textContent = `${input.value.length}/${input.maxLength}`;
  });
}

async function continueCoverageGoal() {
  const goal = el('input[name="coverageGoal"]:checked')?.value || "aso_seo_aeo";
  const brand = el("#coverageBrandTerm").value.trim();
  if (!brand) {
    toast("Enter the app’s brand term before continuing.", true);
    return;
  }
  const selected = el("#coverageCountrySelect").value;
  state.coverageGoal = goal;
  state.coverageBrand = brand;
  state.coverageCountry = selected;
  state.coverageStep = 2;
  state.coverageDraft = null;
  state.coverageAnalysis = null;
  state.coverageStrategy = null;
  if (selected !== state.country) {
    state.country = selected;
    await loadDashboard({ quiet: true });
  } else {
    renderListingCoverage();
  }
}

async function analyseCoverage(event) {
  event.preventDefault();
  const name = el("#coverageName").value.trim();
  const subtitle = el("#coverageSubtitle").value.trim();
  const keywords = el("#coverageKeywords").value.trim();
  if (!name) { toast("Enter the listing name.", true); return; }
  setBusy(true);
  try {
    const result = await request("/api/listing-metadata", {
      method: "POST",
      body: { appId: state.appId, country: state.coverageCountry, device: state.device, name, subtitle, keywords, goal: state.coverageGoal, brandTerm: state.coverageBrand },
    });
    state.coverageDraft = {
      name: result.metadata.name,
      subtitle: result.metadata.subtitle,
      keywords: result.metadata.keywords,
    };
    state.data.listingMetadata = result.metadata;
    state.coverageAnalysis = result.analysis;
    state.coverageStrategy = result.strategy;
    state.coverageGoal = result.metadata.channelGoal;
    state.coverageBrand = result.metadata.brandTerm;
    if (result.health) state.data.health = result.health;
    state.coverageStep = 3;
    renderHero();
    renderHealth();
  } catch (error) { toast(error.message, true); }
  finally { setBusy(false); }
}

function dailyKeywordSnapshots() {
  const checks = (state.data.history || []).filter((point) => point.country === state.country && point.device === state.device);
  const byDate = new Map();
  for (const check of checks) {
    const key = localDateKey(check.checkedAt);
    if (!byDate.has(key)) byDate.set(key, new Map());
    const latest = byDate.get(key).get(check.targetId);
    if (!latest || new Date(check.checkedAt) > new Date(latest.checkedAt)) {
      byDate.get(key).set(check.targetId, check);
    }
  }
  return [...byDate.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([dateKey, targetChecks]) => {
      const latest = [...targetChecks.values()];
      const ranks = latest.filter((check) => check.found && check.rank != null).map((check) => check.rank);
      return {
        dateKey,
        timestamp: new Date(`${dateKey}T12:00:00`).getTime(),
        tracked: latest.length,
        found: ranks.length,
        top10: ranks.filter((rank) => rank <= 10).length,
        top50: ranks.filter((rank) => rank <= 50).length,
        averageRank: ranks.length ? ranks.reduce((sum, rank) => sum + rank, 0) / ranks.length : null,
      };
    });
}

function renderOverallRankHistory() {
  const host = el("#overallRankChart");
  const points = dailyKeywordSnapshots().filter((point) => point.averageRank != null);

  el("#overallAverageRank").textContent = points.length ? `#${points.at(-1).averageRank.toFixed(1)}` : "—";
  if (!points.length) {
    host.innerHTML = `<div class="chart-empty">Run checks on more than one day to build an overall rank trend.</div>`;
    return;
  }
  const width = 920, height = 250, left = 50, right = 18, top = 22, bottom = 34;
  const maxRank = Math.max(10, ...points.map((point) => Math.ceil(point.averageRank)));
  const minTime = Math.min(...points.map((point) => point.timestamp));
  const maxTime = Math.max(...points.map((point) => point.timestamp));
  const x = (timestamp) => points.length === 1 ? width / 2 : left + ((timestamp - minTime) / Math.max(maxTime - minTime, 1)) * (width - left - right);
  const y = (rank) => top + ((rank - 1) / Math.max(maxRank - 1, 1)) * (height - top - bottom);
  const guides = [1, Math.ceil(maxRank / 2), maxRank].map((rank) => `<line x1="${left}" y1="${y(rank)}" x2="${width-right}" y2="${y(rank)}" stroke="#e5e5de"/><text x="${left-10}" y="${y(rank)+4}" text-anchor="end" fill="#777872" font-size="10">#${rank}</text>`).join("");
  const coords = points.map((point) => `${x(point.timestamp)},${y(point.averageRank)}`).join(" ");
  const dots = points.map((point) => `<circle cx="${x(point.timestamp)}" cy="${y(point.averageRank)}" r="4.5" fill="#15966a" stroke="#fff" stroke-width="3"><title>${formatDate(point.dateKey)} · Avg #${point.averageRank.toFixed(1)} · ${point.found}/${point.tracked} found</title></circle>`).join("");
  const labels = points.length > 1 ? `<text x="${left}" y="${height-7}" fill="#777872" font-size="10">${formatDate(points[0].dateKey)}</text><text x="${width-right}" y="${height-7}" text-anchor="end" fill="#777872" font-size="10">${formatDate(points.at(-1).dateKey)}</text>` : "";
  host.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Average rank across tracked keywords; higher is better">${guides}<polyline points="${coords}" fill="none" stroke="#15966a" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>${dots}${labels}</svg>`;
}

function metricCardClick(event) {
  const card = event.target.closest("[data-metric-series]");
  if (!card) return;
  openMetricHistory(card.dataset.metricSeries);
}

function openMetricHistory(series) {
  const rankSeries = series === "averageRank";
  const threshold = series === "top10" ? 10 : series === "top50" ? 50 : null;
  const points = rankSeries
    ? dailyKeywordSnapshots().filter((point) => point.averageRank != null)
    : dailyKeywordSnapshots();
  const color = rankSeries ? "#d88738" : threshold === 10 ? "#15966a" : "#7258cc";
  const latestValue = points.length ? points.at(-1)[series] : null;
  el("#metricHistoryTitle").textContent = rankSeries ? "Average rank evolution" : `Top ${threshold} evolution`;
  el("#metricHistoryLatest").textContent = latestValue == null ? "—" : rankSeries ? `#${latestValue.toFixed(1)}` : String(latestValue);
  el("#metricHistoryCaption").textContent = rankSeries ? "average rank" : `keywords in Top ${threshold}`;
  el("#metricHistoryPeriod").textContent = points.length
    ? `${points.length} daily data point${points.length === 1 ? "" : "s"}`
    : "";
  el("#metricHistoryMethodology").textContent = rankSeries
    ? `Daily average rank of found keywords for ${countryFlag(state.country)} ${state.country.toUpperCase()} · ${deviceName(state.device)}. Missing apps are excluded. Each keyword contributes its latest successful check that day.`
    : `Daily count of tracked keywords ranking in the Top ${threshold} for ${countryFlag(state.country)} ${state.country.toUpperCase()} · ${deviceName(state.device)}. Each keyword contributes its latest successful check that day.`;
  renderMetricHistoryChart(points, series, threshold, color);
  el("#metricHistoryModal").showModal();
}

function renderMetricHistoryChart(points, valueKey, threshold, color) {
  const host = el("#metricHistoryChart");
  if (!points.length) {
    host.innerHTML = `<div class="chart-empty">Run checks over multiple days to build this trend.</div>`;
    return;
  }
  const width = 920, height = 290, left = 48, right = 18, top = 22, bottom = 34;
  const rankSeries = valueKey === "averageRank";
  const maxValue = rankSeries ? Math.max(10, ...points.map((point) => Math.ceil(point[valueKey]))) : Math.max(1, ...points.map((point) => point[valueKey]));
  const minTime = Math.min(...points.map((point) => point.timestamp));
  const maxTime = Math.max(...points.map((point) => point.timestamp));
  const x = (timestamp) => points.length === 1 ? width / 2 : left + ((timestamp - minTime) / Math.max(maxTime - minTime, 1)) * (width - left - right);
  const y = rankSeries
    ? (value) => top + ((value - 1) / Math.max(maxValue - 1, 1)) * (height - top - bottom)
    : (value) => height - bottom - (value / maxValue) * (height - top - bottom);
  const guideValues = rankSeries ? [1, Math.ceil(maxValue / 2), maxValue] : [...new Set([0, Math.ceil(maxValue / 2), maxValue])];
  const guides = guideValues.map((value) => `<line x1="${left}" y1="${y(value)}" x2="${width-right}" y2="${y(value)}" stroke="#e5e5de"/><text x="${left-10}" y="${y(value)+4}" text-anchor="end" fill="#777872" font-size="10">${rankSeries ? "#" : ""}${value}</text>`).join("");
  const coords = points.map((point) => `${x(point.timestamp)},${y(point[valueKey])}`).join(" ");
  const dots = points.map((point) => `<circle cx="${x(point.timestamp)}" cy="${y(point[valueKey])}" r="4.5" fill="${color}" stroke="#fff" stroke-width="3"><title>${formatDate(point.dateKey)} · ${rankSeries ? `Avg #${point[valueKey].toFixed(1)}` : `${point[valueKey]} keyword${point[valueKey] === 1 ? "" : "s"} in Top ${threshold}`}</title></circle>`).join("");
  const labels = points.length > 1 ? `<text x="${left}" y="${height-7}" fill="#777872" font-size="10">${formatDate(points[0].dateKey)}</text><text x="${width-right}" y="${height-7}" text-anchor="end" fill="#777872" font-size="10">${formatDate(points.at(-1).dateKey)}</text>` : "";
  const label = rankSeries ? "Average keyword rank over time; higher is better" : `Top ${threshold} keyword count over time; higher is better`;
  host.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${label}">${guides}<polyline points="${coords}" fill="none" stroke="${color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>${dots}${labels}</svg>`;
}

function renderLosingTo() {
  el("#losingMarket").textContent = `${countryFlag(state.country)} ${state.country.toUpperCase()} · ${deviceName(state.device)}`;
  const competitors = new Map();
  for (const row of countryRows()) {
    const trackedRank = row.found && row.rank != null ? row.rank : Number.POSITIVE_INFINITY;
    for (const app of row.topApps || []) {
      if (app.appId === state.appId || app.position >= trackedRank) continue;
      const existing = competitors.get(app.appId) || {
        appId: app.appId,
        name: app.name,
        artworkUrl: app.artworkUrl,
        averageRating: null,
        ratingCount: null,
        ratingCheckedAt: Number.NEGATIVE_INFINITY,
        count: 0,
        keywords: [],
      };
      const checkedAt = +new Date(row.checkedAt);
      if (
        (app.averageRating != null || app.ratingCount != null)
        && Number.isFinite(checkedAt)
        && checkedAt >= existing.ratingCheckedAt
      ) {
        existing.averageRating = app.averageRating;
        existing.ratingCount = app.ratingCount;
        existing.ratingCheckedAt = checkedAt;
      }
      existing.count += 1;
      existing.keywords.push(row.keyword);
      competitors.set(app.appId, existing);
    }
  }
  const ranked = [...competitors.values()].sort((left, right) => right.count - left.count || left.name.localeCompare(right.name));
  el("#losingCount").textContent = String(ranked.length);
  el("#losingGrid").innerHTML = ranked.slice(0, 6).map((app) => {
    const keywords = app.keywords.sort((left, right) => left.localeCompare(right));
    const artwork = app.artworkUrl
      ? `<img src="${escapeAttr(app.artworkUrl)}" alt="" loading="lazy">`
      : escapeHtml(initials(app.name));
    return `<article class="losing-item" title="${escapeAttr(`${app.name} — Ahead in: ${keywords.join(", ")}`)}">
      <span class="losing-icon">${artwork}</span>
      <span class="losing-copy"><strong>${escapeHtml(app.name)}</strong>${losingRatingMarkup(app)}</span>
      <span class="losing-value"><strong>${app.count}</strong><small>ahead</small></span>
    </article>`;
  }).join("") || `<div class="losing-empty">No Top 5 competitors are currently ahead of this app in the selected market.</div>`;
}

function losingRatingMarkup(app) {
  const rating = Number(app.averageRating);
  const ratingCount = Number(app.ratingCount);
  const hasRating = app.averageRating != null && Number.isFinite(rating);
  const hasCount = app.ratingCount != null && Number.isFinite(ratingCount);
  if (!hasRating && !hasCount) {
    return `<small class="losing-rating unavailable"><span>★</span><span>Rating unavailable</span></small>`;
  }
  const ratingLabel = hasRating ? rating.toFixed(1) : "—";
  const countLabel = hasCount
    ? `${formatCompact(ratingCount)} ${ratingCount === 1 ? "rating" : "ratings"}`
    : "rating count unavailable";
  return `<small class="losing-rating"><span>★ ${ratingLabel}</span><span>${countLabel}</span></small>`;
}

function renderHealth() {
  renderListingCoverage();
  renderScreenshots();
  renderHealthScore();
  renderHealthSuggestions();
}

function renderHealthScore() {
  const health = state.data.health;
  const healthLayout = el("#healthScoreCard").closest(".health-layout");
  const breakdownCard = el("#healthBreakdown").closest(".breakdown-card");
  const auditConfigured = keywordCoverageConfigured();
  healthLayout.classList.toggle("audit-locked", !auditConfigured);
  breakdownCard.hidden = !auditConfigured;
  if (!auditConfigured) {
    el("#healthScoreCard").innerHTML = `<div class="health-audit-gate"><span class="health-audit-icon">⌕</span><p class="section-kicker">Listing health</p><h2>Complete Keyword coverage to unlock scoring</h2><p>Set your growth strategy, brand term, title, subtitle, and keyword field in the listing audit above. The health score stays hidden until your audit is saved.</p><button type="button" class="button button-primary" id="healthAuditButton">Set up listing audit ↑</button></div>`;
    el("#healthBreakdown").innerHTML = "";
    el("#healthAuditButton").addEventListener("click", () => {
      el("#coverageCard").scrollIntoView({ behavior: "smooth", block: "start" });
      el("#coverageBrandTerm")?.focus();
    });
    return;
  }
  if (!health) {
    el("#healthScoreCard").innerHTML = `<div class="empty-state"><div class="empty-icon">!</div><h3>Listing unavailable</h3><p>${escapeHtml(state.data.listingError || "Apple did not return listing metadata.")}</p></div>`;
    el("#healthBreakdown").innerHTML = "";
    return;
  }
  if (health.score == null) {
    el("#healthScoreCard").innerHTML = `<div class="empty-state"><div class="empty-icon">⌕</div><h3>Complete the strategy audit</h3><p>The score is calculated only from saved keyword repetition and title-order checks.</p></div>`;
    el("#healthBreakdown").innerHTML = "";
    return;
  }
  el("#healthScoreCard").innerHTML = `<p class="section-kicker">Strategy audit score</p><div class="score-ring" style="--score:${health.score}"><strong>${health.score}</strong></div><h2>${escapeHtml(health.label)}</h2><p>Calculated only from the saved listing strategy audit for ${state.country.toUpperCase()}. Public listing fields are shown separately and do not affect this score.</p>`;
  el("#healthBreakdown").innerHTML = health.items.map((item) => {
    const available = item.available !== false;
    const percent = Math.round(item.score / item.maximum * 100);
    const band = percent < 40 ? "low" : percent < 75 ? "mid" : "";
    const progress = available ? `<div class="progress"><i class="${band}" style="width:${percent}%"></i></div>` : `<div class="progress unavailable"><span>Not exposed</span></div>`;
    return `<div class="health-row ${available ? "" : "unavailable"}"><span class="health-row-icon">${healthIcon(item.key)}</span><div><strong>${escapeHtml(item.label)}</strong><small>${escapeHtml(item.detail)}</small></div>${progress}<div class="score-fraction">${available ? `${item.score}/${item.maximum}` : "N/A"}</div></div>`;
  }).join("");
}

function renderHealthSuggestions() {
  const health = state.data.health;
  if (!health) {
    el("#healthSuggestions").innerHTML = "";
    el("#healthMethodology").textContent = "";
    return;
  }
  el("#healthSuggestions").innerHTML = `<div class="suggestion-list">${health.suggestions.map((item) => `<article class="suggestion"><i></i><p>${escapeHtml(item)}</p></article>`).join("")}</div>`;
  el("#healthMethodology").textContent = health.methodology;
}

function keywordCoverageConfigured() {
  const metadata = state.data?.listingMetadata;
  return Boolean(metadata?.name?.trim() && metadata?.brandTerm?.trim() && metadata?.channelGoal);
}

function renderScreenshots() {
  const listing = state.data.listing || {};
  const screenshots = listing.screenshots || [];
  const availability = el("#screenshotAvailability");
  if (screenshots.length) {
    availability.textContent = `${screenshots.length} returned`;
    availability.className = "availability-badge available";
    el("#screenshotGallery").innerHTML = `<div class="screenshot-strip">${screenshots.map((url, index) => `<figure><img src="${escapeAttr(url)}" loading="lazy" alt="App Store screenshot ${index + 1} for ${escapeAttr(listing.name || "this app")}"><figcaption>Screenshot ${index + 1}</figcaption></figure>`).join("")}</div>`;
    return;
  }
  availability.textContent = listing.screenshotStatus === "not_exposed" ? "Not exposed by API" : "Unavailable";
  availability.className = "availability-badge unavailable";
  const listingLink = listing.url ? `<a class="button button-ghost" href="${escapeAttr(listing.url)}" target="_blank" rel="noreferrer">Verify on App Store ↗</a>` : "";
  el("#screenshotGallery").innerHTML = `<div class="screenshot-unavailable"><div class="empty-icon">▣</div><div><h3>Screenshot data is not publicly exposed</h3><p>Apple's public iTunes API returned no screenshot URLs. This does <strong>not</strong> mean the listing has no screenshots, and it is not scored as zero.</p></div>${listingLink}</div>`;
}

async function loadCompetitorMatrix() {
  if (!state.appId || state.competitorMatrixLoading) return;
  state.competitorMatrixLoading = true;
  if (!state.competitorMatrixLoaded) {
    el("#competitorMatrix").innerHTML = `<div class="paid-search-empty"><div class="empty-icon">⇄</div><h2>Competitor matrix</h2><p>Loading keyword rankings…</p></div>`;
  }
  try {
    const query = new URLSearchParams({
      appId: String(state.appId),
      country: state.country,
      device: state.device,
    });
    state.competitorMatrix = await request(`/api/competitors?${query}`);
    state.competitorMatrixLoaded = true;
    renderCompetitorMatrix();
  } catch (error) {
    el("#competitorMatrix").innerHTML = `<div class="paid-search-empty"><div class="empty-icon">!</div><h2>Competitor matrix unavailable</h2><p>${escapeHtml(error.message)}</p></div>`;
  } finally {
    state.competitorMatrixLoading = false;
  }
}

function renderCompetitorMatrix() {
  const data = state.competitorMatrix;
  if (!data) return;
  const apps = data.apps || [];
  const keywords = data.keywords || [];
  const lastChecked = data.lastCheckedAt ? `Checked ${formatDate(data.lastCheckedAt)}` : "Not checked yet";
  el("#competitorMatrix").innerHTML = `
    <div class="competitor-matrix-head">
      <div><p class="section-kicker">Keyword competitor matrix</p><h2>${escapeHtml(data.app.name)} vs competitors</h2><p>${countryFlag(state.country)} ${escapeHtml(state.country.toUpperCase())} · ${deviceName(state.device)} · ${keywords.length} tracked keywords</p></div>
      <div class="competitor-matrix-actions"><span class="availability-badge">${lastChecked}</span><button type="button" class="button button-primary" data-competitor-action="refresh" ${data.competitorCount ? "" : "disabled"}>↻ Refresh rankings</button></div>
    </div>
    <div class="competitor-matrix-hint">Click any app icon in the Top 5 rows under Keywords to add it here.</div>
    <div class="competitor-matrix-scroll"><table class="competitor-matrix-table"><thead><tr><th class="matrix-keyword-head">Keyword</th>${apps.map(competitorAppHeader).join("")}</tr></thead><tbody>${keywords.map((row) => competitorKeywordRow(row, apps)).join("") || `<tr><td colspan="${Math.max(1, apps.length + 1)}">No tracked keywords for this storefront and device.</td></tr>`}</tbody></table></div>`;
}

function competitorAppHeader(app) {
  const icon = app.artworkUrl
    ? `<img src="${escapeAttr(app.artworkUrl)}" alt="">`
    : escapeHtml(initials(app.name));
  const remove = app.isPrimary
    ? `<small>Primary app</small>`
    : `<button type="button" class="competitor-remove" data-competitor-action="remove" data-competitor-app-id="${app.appleAppId}" title="Remove from competitor view" aria-label="Remove ${escapeAttr(app.name)} from competitor view">×</button>`;
  return `<th class="matrix-app-head ${app.isPrimary ? "primary" : ""}"><div class="matrix-app-avatar">${icon}</div><strong title="${escapeAttr(app.name)}">${escapeHtml(app.name)}</strong>${remove}</th>`;
}

function competitorKeywordRow(row, apps) {
  return `<tr><th scope="row" class="matrix-keyword">${escapeHtml(row.keyword)}</th>${(row.cells || []).map((cell) => matrixRankCell(cell, apps)).join("")}</tr>`;
}

function matrixRankCell(cell, apps) {
  const app = apps.find((item) => item.appleAppId === cell.appleAppId);
  const appName = app?.name || `App ${cell.appleAppId}`;
  if (cell.status === "pending") {
    return `<td class="matrix-rank pending" title="${escapeAttr(appName)} has not been checked for this keyword">—</td>`;
  }
  if (cell.status === "error") {
    return `<td class="matrix-rank error" title="${escapeAttr(cell.error || `${appName} check failed`)}">!</td>`;
  }
  if (cell.found && cell.rank != null) {
    const tone = cell.rank <= 10 ? "top" : cell.rank <= 50 ? "middle" : "low";
    return `<td class="matrix-rank ${tone}" title="${escapeAttr(appName)} rank #${cell.rank}">#${cell.rank}</td>`;
  }
  return `<td class="matrix-rank absent" title="${escapeAttr(appName)} is outside the retrieved top ${cell.resultLimit}">>${cell.resultLimit}</td>`;
}

async function competitorMatrixAction(event) {
  const button = event.target.closest("[data-competitor-action]");
  if (!button || !state.appId) return;
  const action = button.dataset.competitorAction;
  setBusy(true);
  try {
    if (action === "refresh") {
      const result = await request("/api/competitors/refresh", {
        method: "POST",
        body: { appId: state.appId, country: state.country, device: state.device },
      });
      state.competitorMatrix = result;
      state.competitorMatrixLoaded = true;
      renderCompetitorMatrix();
      const failures = result.refresh?.failures || 0;
      toast(
        `Competitor rankings refreshed: ${result.refresh?.searches || 0} searches${failures ? `, ${failures} failed` : ""}.`,
        failures > 0,
      );
    } else if (action === "remove") {
      await request("/api/competitors/remove", {
        method: "POST",
        body: { competitorAppId: Number(button.dataset.competitorAppId) },
      });
      state.competitorMatrixLoaded = false;
      await loadCompetitorMatrix();
      toast("Competitor removed from the matrix.");
    }
  } catch (error) {
    toast(error.message, true);
  } finally {
    setBusy(false);
  }
}

function renderCompetitorPicker() {
  const apps = (state.data.apps || []).filter((app) => app.appleAppId !== state.appId && app.active);
  el("#competitorSelect").innerHTML = apps.length ? apps.map((app) => `<option value="${app.appleAppId}">${escapeHtml(app.name)} · ${app.appleAppId}</option>`).join("") : `<option value="">Add another app first</option>`;
  el("#compareButton").disabled = !apps.length;
}

async function compareApps() {
  const competitorId = Number(el("#competitorSelect").value);
  if (!competitorId) return;
  setBusy(true);
  try {
    const query = new URLSearchParams({ appId: state.appId, competitorId, country: state.country });
    const data = await request(`/api/compare?${query}`);
    renderComparison(data);
  } catch (error) { toast(error.message, true); }
  finally { setBusy(false); }
}

function renderComparison(data) {
  const fields = [
    ["Health score", healthValue(data.primaryHealth), healthValue(data.competitorHealth)],
    ["Title", escapeHtml(data.primary.name), escapeHtml(data.competitor.name)],
    ["Bundle ID", escapeHtml(data.primary.bundleId || "—"), escapeHtml(data.competitor.bundleId || "—")],
    ["Genre", escapeHtml(data.primary.genre || "—"), escapeHtml(data.competitor.genre || "—")],
    ["Version", escapeHtml(data.primary.version || "—"), escapeHtml(data.competitor.version || "—")],
    ["Rating", ratingValue(data.primary), ratingValue(data.competitor)],
    ["Screenshots returned", screenshotValue(data.primary), screenshotValue(data.competitor)],
    ["Description length", `${formatCompact(data.primary.descriptionLength)} characters`, `${formatCompact(data.competitor.descriptionLength)} characters`],
    ["Languages returned", String(data.primary.languages.length), String(data.competitor.languages.length)],
    ["Last update", formatDate(data.primary.updatedAt), formatDate(data.competitor.updatedAt)],
    ["Description", `<div class="description-snippet">${escapeHtml(data.primary.description || "—")}</div>`, `<div class="description-snippet">${escapeHtml(data.competitor.description || "—")}</div>`],
  ];
  el("#comparisonCard").innerHTML = `<div class="compare-head"><div></div>${compareAppHead(data.primary)}${compareAppHead(data.competitor)}</div>${fields.map(([label, primary, competitor]) => `<div class="compare-row"><div>${label}</div><div>${primary}</div><div>${competitor}</div></div>`).join("")}`;
}

function compareAppHead(app) {
  return `<div class="compare-app">${app.artworkUrl ? `<img src="${escapeAttr(app.artworkUrl)}" alt="">` : `<span class="app-avatar">${escapeHtml(initials(app.name))}</span>`}<div><h3>${escapeHtml(app.name)}</h3><p>${escapeHtml(app.seller || app.bundleId || "Apple App Store")}</p></div></div>`;
}

async function runCheck() {
  if (!state.appId || state.checkInProgress) return;
  const currentRows = countryRows();
  const rows = currentRows.filter((row) => !keywordCheckedWithinDay(row));
  const skipped = currentRows.length - rows.length;
  if (!rows.length) {
    toast(
      currentRows.length
        ? `All ${currentRows.length} keyword rows were checked within the last 24 hours.`
        : "No checked keyword rows are available to refresh.",
      !currentRows.length,
    );
    return;
  }
  const button = el("#runCheckButton");
  state.checkInProgress = true;
  state.checkingTargets = new Set();
  state.queuedCheckTargets = new Set(rows.map((row) => row.targetId));
  button.disabled = true;
  renderRankings();
  let completed = 0;
  let checkedCount = 0;
  let failures = 0;
  try {
    for (const row of rows) {
      state.queuedCheckTargets.delete(row.targetId);
      state.checkingTargets.add(row.targetId);
      button.innerHTML = `<span class="sync-icon">↻</span> Checking ${completed + 1}/${rows.length}`;
      renderRankings();
      try {
        const result = await request("/api/check", {
          method: "POST",
          body: {
            appId: state.appId,
            country: row.country,
            device: row.device,
            keyword: row.keyword,
          },
        });
        failures += Number(result.failures || 0);
        skipped += Number(result.skipped || 0);
        checkedCount += Number(result.checks || 0);
        const updated = result.rankings?.[0];
        if (updated) {
          const index = (state.data.rankings || []).findIndex(
            (item) => item.targetId === updated.targetId,
          );
          if (index >= 0) state.data.rankings[index] = updated;
        }
      } catch (error) {
        failures += 1;
        const index = (state.data.rankings || []).findIndex(
          (item) => item.targetId === row.targetId,
        );
        if (index >= 0) {
          state.data.rankings[index] = {
            ...state.data.rankings[index],
            status: "error",
            error: error.message,
          };
        }
      }
      state.checkingTargets.delete(row.targetId);
      completed += 1;
      renderRankings();
    }
    await loadDashboard({ quiet: true });
    const skippedText = skipped
      ? ` ${skipped} row${skipped === 1 ? " was" : "s were"} skipped because data already exists from the last 24 hours.`
      : "";
    toast(
      `Checked ${checkedCount} keyword row${checkedCount === 1 ? "" : "s"}${failures ? `; ${failures} failed` : ""}.${skippedText}`,
      failures > 0,
    );
  } finally {
    state.checkingTargets.clear();
    state.queuedCheckTargets.clear();
    state.checkInProgress = false;
    button.disabled = false;
    button.innerHTML = `<span class="sync-icon">↻</span> Run check`;
    renderRankings();
  }
}

function keywordCheckedWithinDay(row) {
  if (row.status !== "success" || !row.checkedAt) return false;
  const checkedAt = +new Date(row.checkedAt);
  return Number.isFinite(checkedAt) && Date.now() - checkedAt < 24 * 60 * 60 * 1000;
}

async function addKeyword(event) {
  event.preventDefault();
  const countries = all('#countryChecks input:checked').map((input) => input.value);
  if (!countries.length) { toast("Select at least one storefront.", true); return; }
  const devices = all('#deviceChecks input:checked').map((input) => input.value);
  if (!devices.length) { toast("Select at least one device.", true); return; }
  setBusy(true);
  try {
    const body = state.localization
      ? { appId: state.appId, groups: state.localization.groups, devices }
      : { appId: state.appId, keywords: el("#keywordInput").value, countries, devices };
    const result = await request("/api/keywords", { method: "POST", body });
    el("#keywordModal").close();
    el("#keywordForm").reset();
    resetLocalization();
    const changed = result.targetsCreated + result.targetsReactivated;
    const details = [result.targetsReactivated ? `${result.targetsReactivated} reactivated` : "", result.targetsUnchanged ? `${result.targetsUnchanged} already tracked` : ""].filter(Boolean);
    const suffix = details.length ? ` (${details.join(", ")})` : "";
    const checked = result.automaticCheck;
    const checkSummary = checked.failures
      ? ` Automatic check stored ${checked.checks} result${checked.checks === 1 ? "" : "s"}; ${checked.failures} of ${checked.searches} Apple search${checked.searches === 1 ? "" : "es"} failed.`
      : ` Automatic check stored ${checked.checks} result${checked.checks === 1 ? "" : "s"} from ${checked.searches} Apple search${checked.searches === 1 ? "" : "es"}.`;
    toast(`${result.keywordsRequested} keyword${result.keywordsRequested === 1 ? "" : "s"}: ${changed} tracking target${changed === 1 ? "" : "s"} ready${suffix}.${checkSummary}`, checked.failures > 0);
    await loadDashboard({ quiet: true });
  } catch (error) { toast(error.message, true); }
  finally { setBusy(false); }
}

async function addApp(event) {
  event.preventDefault();
  setBusy(true);
  try {
    const result = await request("/api/apps", { method: "POST", body: { appleId: Number(el("#appleIdInput").value), country: el("#appCountrySelect").value } });
    el("#appModal").close();
    el("#appForm").reset();
    state.appId = result.app.appleAppId;
    state.filter = "";
    toast(`${result.app.name} ${result.created ? "added" : "already exists"}.`);
    await loadDashboard({ quiet: true });
  } catch (error) { toast(error.message, true); }
  finally { setBusy(false); }
}

async function mutate(url, body, success) {
  setBusy(true);
  try { await request(url, { method: "POST", body }); toast(success); state.selectedTarget = null; await loadDashboard({ quiet: true }); }
  catch (error) { toast(error.message, true); }
  finally { setBusy(false); }
}

async function openNicheWorkspace() {
  state.nicheView = true;
  el("#appContentWrap").hidden = true;
  el("#nicheWorkspace").hidden = false;
  el("#nicheNavButton").classList.add("active");
  all("[data-tab-target]").forEach((button) => button.classList.remove("active"));
  el("#sidebar").classList.remove("open");
  if (!state.nicheLoaded) await loadNicheWorkspace();
}

function closeNicheWorkspace() {
  state.nicheView = false;
  el("#nicheWorkspace").hidden = true;
  el("#appContentWrap").hidden = false;
  el("#nicheNavButton").classList.remove("active");
}

async function loadNicheWorkspace(boardId) {
  setBusy(true);
  try {
    const query = boardId ? `?boardId=${boardId}` : "";
    state.niche = await request(`/api/niche${query}`);
    state.nicheLoaded = true;
    renderNicheWorkspace();
  } catch (error) {
    toast(error.message, true);
  } finally {
    setBusy(false);
  }
}

function renderNicheWorkspace() {
  if (!state.niche) return;
  const providers = state.niche.providers || [];
  const available = providers.filter((provider) => provider.available);
  el("#nicheAgentStatus").textContent = available.length
    ? `${available.map((provider) => provider.label).join(" + ")} available`
    : "No local agent found";
  renderNicheProviderSelect("#nicheProvider", providers, state.niche.defaultProvider);
  renderNicheProviderSelect("#nicheAgentProvider", providers, state.niche.defaultProvider);
  el("#nicheBoardSelect").innerHTML = (state.niche.boards || []).map((board) => `<option value="${board.id}" ${board.id === state.niche.selectedBoardId ? "selected" : ""}>${escapeHtml(board.name)}</option>`).join("");
  const board = state.niche.board;
  el("#nicheEmpty").hidden = Boolean(board);
  el("#nicheContent").hidden = !board;
  if (!board) return;
  el("#nicheBoardKicker").textContent = `${board.keywords.length} keyword${board.keywords.length === 1 ? "" : "s"} · ${board.countries.length} market${board.countries.length === 1 ? "" : "s"}`;
  el("#nicheBoardTitle").textContent = board.name;
  el("#nicheBoardBrief").textContent = board.brief;
  const checkedTimes = board.keywords.flatMap((keyword) => keyword.metrics.map((metric) => metric.checkedAt)).filter(Boolean);
  el("#nicheChecked").textContent = checkedTimes.length
    ? `Checked ${formatDate(checkedTimes.sort().at(-1))}`
    : "Not checked yet";
  const usedCountries = new Set(board.countries.map((country) => country.code));
  const availableCountries = (state.niche.availableCountries || []).filter((country) => !usedCountries.has(country.code));
  el("#nicheCountrySelect").innerHTML = availableCountries.length
    ? availableCountries.map((country) => `<option value="${country.code}">${countryFlag(country.code)} ${country.code.toUpperCase()} · ${escapeHtml(country.name)}</option>`).join("")
    : `<option value="">All storefronts added</option>`;
  el("#nicheAddCountryButton").disabled = !availableCountries.length;
  const headers = board.countries.map((country) => `<th class="niche-country-head"><span>${countryFlag(country.code)}</span><strong>${escapeHtml(country.code.toUpperCase())}</strong><button class="niche-country-remove" data-remove-niche-country="${country.code}" title="Remove ${escapeAttr(country.name)}">×</button></th>`).join("");
  const rows = board.keywords.map((keyword) => `<tr><td>${escapeHtml(keyword.keyword)}</td>${keyword.metrics.map((metric) => nicheMetricCell(metric)).join("")}</tr>`).join("");
  el("#nicheBoardScroll").innerHTML = `<table class="niche-table"><thead><tr><th>Keyword</th>${headers}</tr></thead><tbody>${rows}</tbody></table>`;
  all("[data-remove-niche-country]").forEach((button) => button.addEventListener("click", () => removeNicheCountry(button.dataset.removeNicheCountry)));
}

function renderNicheProviderSelect(selector, providers, defaultProvider) {
  const select = el(selector);
  const current = select.value || defaultProvider || "auto";
  select.innerHTML = `<option value="auto">Auto-detect</option>${providers.map((provider) => `<option value="${provider.id}" ${provider.available ? "" : "disabled"}>${escapeHtml(provider.label)}${provider.available ? "" : " · unavailable"}</option>`).join("")}`;
  select.value = current;
}

function nicheMetricCell(metric) {
  if (metric.status === "error") {
    return `<td class="niche-cell"><div class="niche-cell-inner pending" title="${escapeAttr(metric.error || "Apple search failed")}"><span>Check failed</span></div></td>`;
  }
  if (metric.status === "success" && (metric.volume == null || metric.difficulty == null)) {
    return `<td class="niche-cell"><div class="niche-cell-inner pending" title="Apple returned matching apps, but none exposed public rating signals. No 0–100 estimate can be calculated."><span>No rated matches</span></div></td>`;
  }
  if (metric.status !== "success") {
    return `<td class="niche-cell"><div class="niche-cell-inner pending" title="This keyword-market pair has not been checked yet."><span>Not checked</span></div></td>`;
  }
  const volumeTone = metric.volume >= 35 ? "good" : metric.volume >= 15 ? "mid" : "low";
  const difficultyTone = metric.difficulty <= 33 ? "good" : metric.difficulty <= 66 ? "mid" : "high";
  const cellTone = volumeTone === "good" && difficultyTone === "good"
    ? "good"
    : volumeTone === "good" && difficultyTone === "high"
      ? "mixed"
      : difficultyTone === "high"
        ? "hard"
        : volumeTone === "low"
          ? "low"
          : "mid";
  const title = `Volume estimate ${metric.volume}/100; difficulty estimate ${metric.difficulty}/100; ${metric.sampleSize || 0} rated app matches.${cellTone === "mixed" ? " Mixed opportunity: good audience signal with strong competition." : ""}`;
  return `<td class="niche-cell"><div class="niche-cell-inner ${cellTone}" title="${escapeAttr(title)}"><span class="niche-metric volume-${volumeTone}"><span>Vol</span><strong>${metric.volume}</strong></span><span class="niche-metric difficulty-${difficultyTone}"><span>Diff</span><strong>${metric.difficulty}</strong></span></div></td>`;
}

function nicheCheckSummary(check) {
  const searches = Number(check?.searches || 0);
  const failures = Number(check?.failures || 0);
  const noun = searches === 1 ? "combination" : "combinations";
  return failures
    ? `Checked ${searches} keyword-market ${noun}; ${failures} failed.`
    : `Checked ${searches} keyword-market ${noun}.`;
}

async function createNicheBoard(event) {
  event.preventDefault();
  const brief = el("#nicheBrief").value.trim();
  if (!brief) { toast("Describe the niche first.", true); return; }
  setBusy(true);
  try {
    const result = await request("/api/niche/generate", {
      method: "POST",
      body: { brief, provider: el("#nicheProvider").value },
    });
    state.niche = result;
    el("#nicheBrief").value = "";
    el("#nicheContent").hidden = false;
    renderNicheWorkspace();
    const failures = Number(result.generation.check?.failures || 0);
    toast(
      `${result.generation.keywords.length} keywords generated with ${result.generation.provider}, then checked across ${result.board.countries.length} markets${failures ? `; ${failures} checks failed` : ""}.`,
      failures > 0,
    );
  } catch (error) {
    toast(error.message, true);
  } finally {
    setBusy(false);
  }
}

async function addNicheKeywordsWithAgent(event) {
  event.preventDefault();
  const instruction = el("#nicheAgentInput").value.trim();
  if (!instruction || !state.niche?.board) return;
  setBusy(true);
  try {
    const result = await request("/api/niche/agent-keywords", {
      method: "POST",
      body: {
        boardId: state.niche.board.id,
        instruction,
        provider: el("#nicheAgentProvider").value,
      },
    });
    state.niche = result;
    el("#nicheAgentInput").value = "";
    renderNicheWorkspace();
    const failures = Number(result.agent.check?.failures || 0);
    toast(
      `${result.agent.keywords.length} keyword${result.agent.keywords.length === 1 ? "" : "s"} added with ${result.agent.provider}${failures ? `; ${failures} checks failed` : ""}.`,
      failures > 0,
    );
  } catch (error) {
    toast(error.message, true);
  } finally {
    setBusy(false);
  }
}

async function checkNicheBoard() {
  if (!state.niche?.board) return;
  setBusy(true);
  try {
    const boardId = state.niche.board.id;
    state.niche = await request("/api/niche/check", { method: "POST", body: { boardId } });
    renderNicheWorkspace();
    toast(nicheCheckSummary(state.niche.check), Number(state.niche.check?.failures || 0) > 0);
  } catch (error) {
    toast(error.message, true);
  } finally {
    setBusy(false);
  }
}

async function addNicheCountry() {
  const country = el("#nicheCountrySelect").value;
  if (!country || !state.niche?.board) return;
  setBusy(true);
  try {
    state.niche = await request("/api/niche/countries/add", {
      method: "POST",
      body: { boardId: state.niche.board.id, country },
    });
    renderNicheWorkspace();
    const failures = Number(state.niche.countryChange?.check?.failures || 0);
    toast(
      `${countryFlag(country)} ${country.toUpperCase()} added${failures ? `; ${failures} checks failed` : " and checked"}.`,
      failures > 0,
    );
  } catch (error) {
    toast(error.message, true);
  } finally {
    setBusy(false);
  }
}

async function removeNicheCountry(country) {
  if (!state.niche?.board) return;
  setBusy(true);
  try {
    state.niche = await request("/api/niche/countries/remove", {
      method: "POST",
      body: { boardId: state.niche.board.id, country },
    });
    renderNicheWorkspace();
    toast(`${countryFlag(country)} ${country.toUpperCase()} removed from this board.`);
  } catch (error) {
    toast(error.message, true);
  } finally {
    setBusy(false);
  }
}

async function loadAppleAds() {
  if (!state.appId || state.appleAdsLoading) return;
  state.appleAdsLoading = true;
  if (!state.appleAdsLoaded) {
    el("#appleAdsContent").innerHTML = `<div class="card paid-search-empty"><div class="empty-icon">◎</div><h2>Apple Ads</h2><p>Loading read-only campaign data…</p></div>`;
  }
  try {
    const query = new URLSearchParams({
      appId: String(state.appId),
      country: state.country,
      device: state.device,
    });
    state.appleAds = await request(`/api/apple-ads?${query}`);
    state.appleAdsLoaded = true;
    renderAppleAds();
  } catch (error) {
    el("#appleAdsContent").innerHTML = `<div class="card paid-search-empty"><div class="empty-icon">!</div><h2>Apple Ads unavailable</h2><p>${escapeHtml(error.message)}</p></div>`;
  } finally {
    state.appleAdsLoading = false;
  }
}

function renderAppleAds() {
  const data = state.appleAds;
  if (!data) return;
  const credentials = data.credentials || {};
  if (!credentials.available) {
    el("#appleAdsContent").innerHTML = `<section class="card paid-setup-card">
      <p class="section-kicker">Read-only Apple Ads</p>
      <h2>Connect your local API credential</h2>
      <p>Place the signed <code>client-secret.jwt</code> at the path below. The app never displays, logs, exports, or commits its contents.</p>
      <div class="paid-credential-path">${escapeHtml(credentials.path || "Unavailable")}</div>
      <p class="paid-setup-error">${escapeHtml(credentials.reason || "The Apple Ads client secret is unavailable.")}</p>
      <button type="button" class="button button-primary" data-paid-action="discover">Check connection</button>
    </section>`;
    return;
  }
  const accounts = data.accounts || [];
  if (!accounts.length) {
    el("#appleAdsContent").innerHTML = `<section class="card paid-setup-card">
      <p class="section-kicker">Read-only Apple Ads</p>
      <h2>Discover your ad account</h2>
      <p>The local credential is valid. Discover the ad accounts it can access, then choose the one managing this app.</p>
      <button type="button" class="button button-primary" data-paid-action="discover">Discover accounts</button>
    </section>`;
    return;
  }
  const selected = accounts.find((account) => account.id === data.selectedAccountId);
  if (!selected) {
    el("#appleAdsContent").innerHTML = `<section class="card paid-setup-card">
      <p class="section-kicker">Read-only Apple Ads</p>
      <h2>Choose the ad account</h2>
      <p>Apple Ads credentials can access more than one ad account. Select the account containing the campaigns for this app.</p>
      <div class="apple-ads-account-grid">${accounts.map((account) => `<button type="button" class="apple-ads-account" data-paid-action="select-account" data-ad-account="${account.id}"><span>${escapeHtml(account.name)}</span><strong>${account.id}</strong><small>${escapeHtml((account.roles || []).join(" · ") || "No role reported")}</small></button>`).join("")}</div>
    </section>`;
    return;
  }

  const summary = data.summary || {};
  const allMarketsSummary = data.allMarketsSummary || {};
  const window = data.window || {};
  const campaigns = data.campaigns || [];
  const keywordCountries = data.keywordCountries || [];
  const countryCodes = new Set(keywordCountries.map((group) => group.code));
  if (state.appleAdsCountryFilter !== "all" && !countryCodes.has(state.appleAdsCountryFilter)) {
    state.appleAdsCountryFilter = "all";
  }
  const statusFilteredCountries = keywordCountries
    .map((group) => ({
      ...group,
      keywords: (group.keywords || []).filter((row) => state.appleAdsShowPaused || row.status === "ENABLED"),
    }));
  const visibleKeywordCountries = statusFilteredCountries
    .filter((group) => state.appleAdsCountryFilter === "all" || group.code === state.appleAdsCountryFilter)
    .filter((group) => group.keywords.length)
    .map((group) => ({
      ...group,
      keywords: sortPaidKeywordRows(group.keywords),
    }));
  const suggestions = data.suggestions || [];
  const sync = data.sync;
  el("#appleAdsContent").innerHTML = `
    <section class="paid-hero card">
      <div><p class="section-kicker">Read-only paid search</p><h2>Apple Ads performance</h2><p>${escapeHtml(selected.name)} · ${countryFlag(state.country)} ${state.country.toUpperCase()} · ${deviceName(state.device)} · ${window.days || 30} completed days</p></div>
      <div class="paid-hero-actions"><label class="select-wrap paid-account-select"><span>Ad account</span><select data-paid-account-select aria-label="Apple Ads account">${accounts.map((account) => `<option value="${account.id}" ${account.id === selected.id ? "selected" : ""}>${escapeHtml(account.name)} · ${account.id}</option>`).join("")}</select></label><span class="availability-badge">${selected.lastSyncedAt ? `Synced ${formatDate(selected.lastSyncedAt)}` : "Not synced yet"}</span><button type="button" class="button button-primary" data-paid-action="sync">↻ Sync Apple Ads</button></div>
    </section>
    ${sync ? `<div class="paid-sync-note">Imported ${sync.campaigns} campaigns, ${sync.keywords} keywords, ${sync.metricRows} daily metric rows, and ${sync.suggestions} suggestions.</div>` : ""}
    <section class="paid-summary-grid">
      ${paidMetricCard("All-market spend", formatPaidMoney(allMarketsSummary.spend, allMarketsSummary.currency), `${formatCompact(allMarketsSummary.impressions)} impressions · ${formatCompact(allMarketsSummary.taps)} taps`)}
      ${paidMetricCard("Selected-market spend", formatPaidMoney(summary.spend, summary.currency), `${state.country.toUpperCase()} · ${deviceName(state.device)}`)}
      ${paidMetricCard("Selected-market taps", formatCompact(summary.taps), `${formatCompact(summary.impressions)} impressions`)}
      ${paidMetricCard("Selected-market installs", formatCompact(summary.tapInstalls), `${formatCompact(summary.totalInstalls)} total installs`)}
      ${paidMetricCard("Cost per tap", formatPaidMoney(summary.cpt, summary.currency), "Apple-reported spend ÷ taps")}
    </section>
    <section class="card paid-table-card">
      <div class="data-head"><div><p class="section-kicker">Campaign overview</p><h2>Campaigns promoting this app</h2></div><span class="availability-badge">${campaigns.filter((item) => item.status === "ENABLED" && !item.deleted).length} enabled</span></div>
      <div class="table-scroll"><table class="paid-table"><thead><tr><th>Campaign</th><th>Status</th><th>Keywords</th><th>Spend</th><th>Impressions</th><th>Taps</th><th>Installs</th></tr></thead><tbody>${campaigns.map(appleAdsCampaignRow).join("") || `<tr><td colspan="7">No campaigns found for this app.</td></tr>`}</tbody></table></div>
    </section>
    <section class="card paid-table-card">
      <div class="data-head"><div><p class="section-kicker">Current targeting</p><h2>Apple Ads keywords by country</h2><p>Filter by market and sort each country group by any keyword metric. The selected storefront is shown first.</p></div><div class="paid-table-tools"><label class="paid-toggle"><input type="checkbox" data-paid-show-paused ${state.appleAdsShowPaused ? "checked" : ""}><span>Show paused</span></label><span class="availability-badge">${visibleKeywordCountries.reduce((count, group) => count + group.keywords.length, 0)} visible rows</span></div></div>
      <div class="paid-country-tabs">${paidCountryFilterButton("all", "All", statusFilteredCountries.reduce((count, group) => count + group.keywords.length, 0))}${statusFilteredCountries.map((group) => paidCountryFilterButton(group.code, group.name, group.keywords.length)).join("")}</div>
      <div class="table-scroll"><table class="paid-table paid-keyword-table"><thead><tr>${paidSortHeader("Keyword", "keyword")}${paidSortHeader("Match types", "matchTypes")}${paidSortHeader("Status", "status")}${paidSortHeader("Campaigns", "campaignCount")}${paidSortHeader("ASO rank", "asoRank")}${paidSortHeader("Bid", "bid")}${paidSortHeader("Spend", "spend")}${paidSortHeader("Impr.", "impressions")}${paidSortHeader("Taps", "taps")}${paidSortHeader("Installs", "installs")}</tr></thead><tbody>${visibleKeywordCountries.map(appleAdsCountryGroup).join("") || `<tr><td colspan="10">No enabled targeting keywords have been synced. Turn on Show paused or choose another country.</td></tr>`}</tbody></table></div>
    </section>
    <section class="card paid-suggestions-card">
      <div class="data-head"><div><p class="section-kicker">Apple suggestions</p><h2>Related keywords to target</h2><p>Seeded by the highest-ranking ASO keywords for ${countryFlag(state.country)} ${state.country.toUpperCase()}. Scores are Apple’s relative suggestion popularity, not search volume.</p></div><span class="availability-badge">${suggestions.length} suggestions</span></div>
      <div class="paid-suggestion-grid">${suggestions.slice(0, 30).map(appleAdsSuggestionCard).join("") || `<div class="paid-search-empty"><p>No suggestions have been synced for this market.</p></div>`}</div>
    </section>`;
}

function paidMetricCard(label, value, note) {
  return `<article class="card paid-metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(note)}</small></article>`;
}

function paidCountryFilterButton(code, name, count) {
  const active = state.appleAdsCountryFilter === code;
  return `<button type="button" class="paid-country-filter ${active ? "active" : ""}" data-paid-action="filter-country" data-country-filter="${escapeAttr(code)}"><span>${code === "all" ? "All" : `${countryFlag(code)} ${escapeHtml(name)}`}</span><small>${count}</small></button>`;
}

function paidSortHeader(label, field) {
  const active = state.appleAdsSortField === field;
  const direction = active ? state.appleAdsSortDirection : null;
  return `<th aria-sort="${active ? (direction === "asc" ? "ascending" : "descending") : "none"}"><button type="button" class="paid-sort-button ${active ? "active" : ""}" data-paid-action="sort" data-paid-sort="${field}">${escapeHtml(label)}<span>${active ? (direction === "asc" ? "↑" : "↓") : "↕"}</span></button></th>`;
}

function sortPaidKeywordRows(rows) {
  const field = state.appleAdsSortField;
  const direction = state.appleAdsSortDirection === "asc" ? 1 : -1;
  return [...rows].sort((left, right) => {
    const leftValue = paidSortValue(left, field);
    const rightValue = paidSortValue(right, field);
    if (leftValue == null && rightValue == null) return String(left.text).localeCompare(String(right.text));
    if (leftValue == null) return 1;
    if (rightValue == null) return -1;
    const comparison = typeof leftValue === "number" && typeof rightValue === "number"
      ? leftValue - rightValue
      : String(leftValue).localeCompare(String(rightValue), undefined, { numeric: true });
    return comparison ? comparison * direction : String(left.text).localeCompare(String(right.text));
  });
}

function paidSortValue(row, field) {
  const metrics = row.metrics || {};
  if (field === "keyword") return row.text;
  if (field === "matchTypes") return (row.matchTypes || []).join(", ");
  if (field === "status") return row.status;
  if (field === "campaignCount") return Number(row.campaignCount || 0);
  if (field === "asoRank") return row.asoFound && row.asoRank != null
    ? Number(row.asoRank)
    : row.asoChecked ? Number(row.asoLimit) + 1 : null;
  if (field === "bid") return row.bidMin == null ? null : Number(row.bidMin);
  if (field === "spend") return Number(metrics.spend || 0);
  if (field === "impressions") return Number(metrics.impressions || 0);
  if (field === "taps") return Number(metrics.taps || 0);
  if (field === "installs") return Number(metrics.tapInstalls || 0);
  return row.text;
}

function appleAdsCampaignRow(campaign) {
  const summary = campaign.summary || {};
  return `<tr><td><strong>${escapeHtml(campaign.name)}</strong></td><td><span class="paid-status ${campaign.status === "ENABLED" ? "enabled" : "paused"}">${escapeHtml(campaign.status)}</span></td><td>${campaign.enabledKeywordCount}/${campaign.keywordCount}</td><td>${escapeHtml(formatPaidMoney(summary.spend, summary.currency))}</td><td>${formatCompact(summary.impressions)}</td><td>${formatCompact(summary.taps)}</td><td>${formatCompact(summary.tapInstalls)}</td></tr>`;
}

function appleAdsCountryGroup(group) {
  const summary = paidRowsSummary(group.keywords || []);
  return `<tr class="paid-country-group ${group.code === state.country.toUpperCase() ? "selected" : ""}"><td colspan="10"><span>${countryFlag(group.code)} <strong>${escapeHtml(group.name)}</strong></span><small>${escapeHtml(formatPaidMoney(summary.spend, summary.currency))} spend · ${formatCompact(summary.taps)} taps</small></td></tr>${(group.keywords || []).map(appleAdsKeywordRow).join("")}`;
}

function paidRowsSummary(rows) {
  const spend = rows.reduce((total, row) => total + Number(row.metrics?.spend || 0), 0);
  const currencies = [...new Set(rows.map((row) => row.metrics?.currency).filter(Boolean))];
  return {
    spend,
    currency: currencies.length === 1 ? currencies[0] : null,
    impressions: rows.reduce((total, row) => total + Number(row.metrics?.impressions || 0), 0),
    taps: rows.reduce((total, row) => total + Number(row.metrics?.taps || 0), 0),
    tapInstalls: rows.reduce((total, row) => total + Number(row.metrics?.tapInstalls || 0), 0),
  };
}

function appleAdsKeywordRow(row) {
  const metrics = row.metrics || {};
  const bid = row.bidMin === row.bidMax
    ? formatPaidMoney(row.bidMin, row.currency)
    : `${formatPaidMoney(row.bidMin, row.currency)}–${formatPaidMoney(row.bidMax, row.currency)}`;
  const rankLabel = row.asoFound && row.asoRank
    ? `#${row.asoRank}`
    : row.asoChecked
      ? `>${row.asoLimit}`
      : row.asoError ? "!" : "⌕";
  const rankTone = row.asoFound
    ? "found"
    : row.asoChecked
      ? "not-found"
      : row.asoError ? "error" : "missing";
  const rankTitle = row.asoFound && row.asoRank
    ? `Search again for the ${row.countryName} App Store rank`
    : row.asoChecked
      ? `Not found in Apple’s top ${row.asoLimit}; click to search again`
      : row.asoError
        ? "The last App Store check failed; click to retry"
        : `Search ${row.countryName} App Store ranking for “${row.text}”`;
  return `<tr><td><strong>${escapeHtml(row.text)}</strong></td><td>${(row.matchTypes || []).map((value) => `<span class="paid-match">${escapeHtml(value)}</span>`).join(" ")}</td><td><span class="paid-status ${row.status === "ENABLED" ? "enabled" : "paused"}">${escapeHtml(row.status)}</span></td><td title="${escapeAttr((row.campaigns || []).join(", "))}">${row.campaignCount}</td><td><button type="button" class="paid-aso-rank ${rankTone}" data-paid-action="check-aso-rank" data-keyword="${escapeAttr(row.text)}" data-country="${escapeAttr(row.country)}" data-country-name="${escapeAttr(row.countryName)}" title="${escapeAttr(rankTitle)}" aria-label="${escapeAttr(rankTitle)}">${rankLabel}</button></td><td>${escapeHtml(bid)}</td><td>${escapeHtml(formatPaidMoney(metrics.spend, metrics.currency))}</td><td>${formatCompact(metrics.impressions)}</td><td>${formatCompact(metrics.taps)}</td><td>${formatCompact(metrics.tapInstalls)}</td></tr>`;
}

function appleAdsSuggestionCard(suggestion) {
  const status = suggestion.inAsoTracker ? "Tracked in ASO" : suggestion.inAppleAds ? "Already targeted" : "New opportunity";
  const disabled = suggestion.inAsoTracker ? "disabled" : "";
  return `<article class="paid-suggestion"><div><strong>${escapeHtml(suggestion.text)}</strong><span class="paid-popularity">${suggestion.popularity ?? "—"}</span></div><small>${status}</small><button type="button" class="text-button" data-paid-action="track-keyword" data-keyword="${escapeAttr(suggestion.text)}" ${disabled}>${suggestion.inAsoTracker ? "Tracked" : "Track in ASO"}</button></article>`;
}

async function appleAdsAction(event) {
  const button = event.target.closest("[data-paid-action]");
  if (!button) return;
  const action = button.dataset.paidAction;
  if (action === "filter-country") {
    state.appleAdsCountryFilter = button.dataset.countryFilter || "all";
    renderAppleAds();
  } else if (action === "sort") {
    const field = button.dataset.paidSort;
    if (state.appleAdsSortField === field) {
      state.appleAdsSortDirection = state.appleAdsSortDirection === "asc" ? "desc" : "asc";
    } else {
      state.appleAdsSortField = field;
      state.appleAdsSortDirection = ["keyword", "matchTypes", "status", "asoRank"].includes(field) ? "asc" : "desc";
    }
    renderAppleAds();
  } else if (action === "check-aso-rank") {
    await checkPaidKeywordRank(button);
  } else if (action === "discover") {
    setBusy(true);
    try {
      await request("/api/apple-ads/discover", { method: "POST", body: {} });
      toast("Apple Ads accounts discovered.");
      await loadAppleAds();
    } catch (error) { toast(error.message, true); }
    finally { setBusy(false); }
  } else if (action === "select-account") {
    await selectAppleAdsAccount(Number(button.dataset.adAccount));
  } else if (action === "sync") {
    await syncAppleAds();
  } else if (action === "track-keyword") {
    const keyword = button.dataset.keyword;
    if (!keyword || !state.appId) return;
    setBusy(true);
    try {
      await request("/api/keywords", { method: "POST", body: { appId: state.appId, keywords: keyword, countries: [state.country], devices: [state.device] } });
      await loadDashboard({ quiet: true });
      await loadAppleAds();
      toast(`“${keyword}” added to ASO tracking.`);
    } catch (error) { toast(error.message, true); }
    finally { setBusy(false); }
  }
}

async function checkPaidKeywordRank(button) {
  if (!state.appId) return;
  setBusy(true);
  try {
    const result = await request("/api/keywords/check-rank", {
      method: "POST",
      body: {
        appId: state.appId,
        keyword: button.dataset.keyword,
        country: button.dataset.country,
        countryName: button.dataset.countryName,
        device: state.device,
      },
    });
    await loadAppleAds();
    const failures = result.automaticCheck?.failures || 0;
    const rankCheck = result.rankCheck;
    const rankResult = rankCheck?.status === "error"
      ? "the Apple request failed"
      : rankCheck?.found && rankCheck?.rank
        ? `rank #${rankCheck.rank}`
        : rankCheck
          ? `not found in Apple’s top ${rankCheck.resultLimit}`
          : "no ranking result";
    toast(
      failures
        ? `Rank search for “${result.keyword}” completed with ${failures} failed Apple request${failures === 1 ? "" : "s"}.`
        : `Rank search for “${result.keyword}” in ${result.country.toUpperCase()}: ${rankResult}.`,
      failures > 0,
    );
  } catch (error) {
    toast(error.message, true);
  } finally {
    setBusy(false);
  }
}

async function appleAdsChange(event) {
  if (event.target.matches("[data-paid-show-paused]")) {
    state.appleAdsShowPaused = event.target.checked;
    renderAppleAds();
    return;
  }
  if (!event.target.matches("[data-paid-account-select]")) return;
  await selectAppleAdsAccount(Number(event.target.value));
}

async function selectAppleAdsAccount(adAccountId) {
  setBusy(true);
  try {
    await request("/api/apple-ads/account", { method: "POST", body: { adAccountId } });
    await loadAppleAds();
    await syncAppleAds();
  } catch (error) { toast(error.message, true); }
  finally { setBusy(false); }
}

async function syncAppleAds() {
  if (!state.appId) return;
  setBusy(true);
  try {
    state.appleAds = await request("/api/apple-ads/sync", {
      method: "POST",
      body: { appId: state.appId, country: state.country, device: state.device, days: 30 },
    });
    state.appleAdsLoaded = true;
    renderAppleAds();
    toast(`Apple Ads synced: ${state.appleAds.sync?.keywords || 0} keywords and ${state.appleAds.sync?.suggestions || 0} suggestions.`);
  } catch (error) {
    toast(error.message, true);
  } finally {
    setBusy(false);
  }
}

function switchTab(tab, scroll = true) {
  state.tab = tab;
  all("[data-panel]").forEach((panel) => panel.classList.toggle("active", panel.dataset.panel === tab));
  all("[data-tab]").forEach((button) => button.classList.toggle("active", button.dataset.tab === tab));
  all("[data-tab-target]").forEach((button) => button.classList.toggle("active", button.dataset.tabTarget === tab));
  el("#addKeywordButton").hidden = tab !== "rankings";
  el("#runCheckButton").hidden = tab !== "rankings";
  if (scroll) window.scrollTo({ top: 0, behavior: "smooth" });
}

async function request(url, options = {}) {
  const config = { ...options, headers: { "Content-Type": "application/json", ...(options.headers || {}) } };
  if (config.body && typeof config.body !== "string") config.body = JSON.stringify(config.body);
  const response = await fetch(url, config);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `Local request failed (${response.status})`);
  return payload;
}

function setBusy(value) { el("#busy").hidden = !value; }
let toastTimer;
function toast(message, isError = false) {
  const target = el("#toast");
  target.textContent = message;
  target.classList.toggle("error", isError);
  target.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => target.classList.remove("show"), 3500);
}

function healthValue(health) {
  if (health?.score == null) {
    return `<span class="health-chip">—</span> <strong>Audit required</strong>`;
  }
  return `<span class="health-chip">${health.score}</span> <strong>${escapeHtml(health.label)}</strong>`;
}
function countryFlag(code) { return [...String(code).toUpperCase()].map((char) => String.fromCodePoint(127397 + char.charCodeAt(0))).join(""); }
function deviceName(device) { return device === "ipad" ? "iPad" : "iPhone"; }
function deviceIcon(device) { return device === "ipad" ? "▭" : "▯"; }
function screenshotValue(listing) { return listing.screenshotStatus === "available" ? String(listing.screenshotCount) : "Not exposed"; }
function ratingValue(app) { return app.averageRating ? `★ ${app.averageRating.toFixed(1)} · ${formatCompact(app.ratingCount)} ratings` : "No rating returned"; }
function shortOpportunity(value) { return value.replace(/\s*\([^)]*\)/, ""); }
function healthIcon(key) { return ({ keyword_repetition: "⌕", title_order: "↕" })[key] || "·"; }
function initials(value) { return (value || "AS").split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase(); }
function localDateKey(value) {
  const date = new Date(value);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}
function formatDate(value) { return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(value)) : "—"; }
function relativeDate(value) {
  const days = Math.max(0, Math.floor((Date.now() - +new Date(value)) / 86400000));
  if (days === 0) return "Updated today";
  if (days === 1) return "Updated yesterday";
  return `Updated ${days} days ago`;
}
function formatCompact(value) { return new Intl.NumberFormat(undefined, { notation: Number(value) >= 1000 ? "compact" : "standard", maximumFractionDigits: 1 }).format(value || 0); }
function formatPaidMoney(value, currency) {
  if (value == null) return "—";
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "—";
  if (currency) {
    try { return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(amount); }
    catch { return `${amount.toFixed(2)} ${currency}`; }
  }
  return amount.toFixed(2);
}
function formatBytes(value) { if (!value) return "—"; return `${(value / 1024 / 1024).toFixed(0)} MB`; }
function metricTrend(trend, label, periodDays) {
  if (!trend) return "";
  if (periodDays === 30 && trend.baseline === 0) return "";
  const tone = trend.better === true ? "better" : trend.better === false ? "worse" : "flat";
  const basis = label === "Tracked"
    ? `tracked targets created on or before ${periodDays} days ago`
    : `the latest stored check on or before ${periodDays} days ago`;
  const title = `${periodDays}-day comparison: ${trend.current} now vs ${trend.baseline} for ${basis}.`;
  if (trend.percent == null) return periodDays === 7 ? `<span class="metric-trend ${tone}" title="${escapeAttr(title)}">NEW <small>7d</small></span>` : "";
  const direction = trend.percent > 0 ? "+" : trend.percent < 0 ? "−" : "";
  return `<span class="metric-trend ${tone}" title="${escapeAttr(title)}">${direction}${Math.abs(trend.percent).toFixed(1)}% <small>${periodDays}d</small></span>`;
}
function estimateCell(value, kind, sampleSize) {
  const shortLabel = kind === "difficulty" ? "Difficulty" : "Volume";
  if (value == null) return `<span class="estimate unknown" title="Run a new check to calculate this estimate."><span class="estimate-label">${shortLabel}</span><strong>—</strong></span>`;
  const tier = kind === "difficulty"
    ? value >= 67 ? "hard" : value >= 34 ? "mid" : "strong"
    : value >= 35 ? "strong" : value >= 15 ? "mid" : "low";
  const titleLabel = kind === "difficulty"
    ? "Estimated competition; higher means harder to enter the top 10."
    : "Estimated audience from matching-app ratings; not Apple search volume.";
  const sample = sampleSize ? ` Based on ${sampleSize} rated app result${sampleSize === 1 ? "" : "s"}.` : "";
  return `<span class="estimate ${tier}" title="${titleLabel}${sample}"><span class="estimate-label">${shortLabel}</span><strong>${value}</strong><span class="estimate-track"><i style="width:${value}%"></i></span></span>`;
}
function escapeHtml(value) { return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]); }
function escapeAttr(value) { return escapeHtml(value); }
