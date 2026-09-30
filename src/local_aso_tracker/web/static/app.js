const state = {
  data: null,
  appId: null,
  country: "us",
  device: "iphone",
  tab: "rankings",
  filter: "",
  selectedTarget: null,
  pendingDeactivateTarget: null,
};

const el = (selector) => document.querySelector(selector);
const all = (selector) => [...document.querySelectorAll(selector)];

document.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  loadDashboard();
});

function bindEvents() {
  bindOnboardingEvents();
  el("#countrySelect").addEventListener("change", (event) => {
    state.country = event.target.value;
    state.selectedTarget = null;
    state.filter = "";
    el("#keywordFilter").value = "";
    loadDashboard();
  });
  el("#deviceSelect").addEventListener("change", (event) => {
    state.device = event.target.value;
    state.selectedTarget = null;
    state.selectedTarget = null;
    state.filter = "";
    el("#keywordFilter").value = "";
    renderHero();
    renderRankings();
  });
  el("#keywordFilter").addEventListener("input", (event) => {
    state.filter = event.target.value.trim().toLowerCase();
    renderRankings();
  });
  el("#runCheckButton").addEventListener("click", runCheck);
  el("#addKeywordButton").addEventListener("click", openKeywordModal);
  el("#addAppButton").addEventListener("click", () => el("#appModal").showModal());
  el("#keywordForm").addEventListener("submit", addKeyword);
  el("#appForm").addEventListener("submit", addApp);
  el("#compareButton").addEventListener("click", compareApps);
  el("#confirmDeactivateButton").addEventListener("click", confirmDeactivate);
  el("#menuButton").addEventListener("click", () => el("#sidebar").classList.toggle("open"));
  el("#rankingsBody").addEventListener("click", rankingClick);
  all("[data-tab], [data-tab-target]").forEach((button) => {
    button.addEventListener("click", () => switchTab(button.dataset.tab || button.dataset.tabTarget));
  });
  all("[data-close-modal]").forEach((button) => {
    button.addEventListener("click", () => {
      const dialog = button.closest("dialog");
      if (dialog.id === "confirmModal") state.pendingDeactivateTarget = null;
      dialog.close();
    });
  });
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
  renderRankings();
  renderHealth();
  renderCompetitorPicker();
  switchTab(state.tab, false);
}

function renderSidebar() {
  el("#setupButton").disabled = false;
  const apps = state.data.apps || [];
  el("#appCount").textContent = `${apps.length} local app${apps.length === 1 ? "" : "s"}`;
  const selectedArtwork = state.data.listing?.artworkUrl;
  el("#appList").innerHTML = apps.map((app, index) => {
    const selected = app.appleAppId === state.appId;
    const icon = selected && selectedArtwork
      ? `<img src="${escapeAttr(selectedArtwork)}" alt="">`
      : escapeHtml(initials(app.name));
    return `<button class="app-list-item ${selected ? "active" : ""}" data-app-id="${app.appleAppId}">
      <span class="app-avatar ${index % 2 ? "alt" : ""}">${icon}</span>
      <span><span class="app-name">${escapeHtml(app.name)}</span><span class="app-meta">${app.active ? "Tracking active" : "Inactive"}</span></span>
      <span class="country-badge">${countryFlag(state.country)} ${escapeHtml(state.country.toUpperCase())}</span>
    </button>`;
  }).join("") || `<div class="empty-state"><p>Add your first app to begin.</p></div>`;
  all(".app-list-item").forEach((button) => button.addEventListener("click", () => {
    state.appId = Number(button.dataset.appId);
    state.selectedTarget = null;
    state.filter = "";
    el("#keywordFilter").value = "";
    el("#sidebar").classList.remove("open");
    loadDashboard();
  }));
}

function renderCountryControls() {
  const countries = (state.data.countries || []).filter((country) => country.active);
  const options = countries.map((country) => `<option value="${country.code}" ${country.code === state.country ? "selected" : ""}>${countryFlag(country.code)} ${country.code.toUpperCase()} · ${escapeHtml(country.name)}</option>`).join("");
  el("#countrySelect").innerHTML = options;
  el("#appCountrySelect").innerHTML = options;
  el("#deviceSelect").value = state.device;
  el("#countryChecks").innerHTML = countries.map((country) => `<label class="country-check"><input type="checkbox" name="country" value="${country.code}" ${country.code === state.country ? "checked" : ""}><span>${countryFlag(country.code)} <strong>${country.code.toUpperCase()}</strong> · ${escapeHtml(country.name)}</span></label>`).join("");
}

function openKeywordModal() {
  all('#deviceChecks input[name="device"]').forEach((input) => {
    input.checked = input.value === state.device;
  });
  el("#keywordModal").showModal();
}

function renderHero() {
  const listing = state.data.listing;
  if (!state.appId || !listing) {
    el("#appHero").innerHTML = `<div class="empty-state"><div class="empty-icon">+</div><h3>No app selected</h3><p>Add an App Store app by numerical ID.</p></div>`;
    return;
  }
  const health = state.data.health;
  const updated = listing.updatedAt ? relativeDate(listing.updatedAt) : "No update date";
  const ratingLabel = listing.ratingCount === 1 ? "rating" : "ratings";
  const rating = listing.averageRating ? `${listing.averageRating.toFixed(1)} (${formatCompact(listing.ratingCount)} ${ratingLabel})` : "No rating yet";
  el("#appHero").innerHTML = `<div class="hero-grid">
    <div class="hero-identity"><div class="hero-icon">${listing.artworkUrl ? `<img src="${escapeAttr(listing.artworkUrl)}" alt="">` : escapeHtml(initials(listing.name))}</div><div class="hero-copy"><h1>${escapeHtml(listing.name)}</h1><p>${escapeHtml(listing.seller || listing.bundleId || "Apple App Store")}</p></div></div>
    <div class="hero-stat"><span>Genre</span><strong>${escapeHtml(listing.genre || "—")}</strong></div>
    <div class="hero-stat"><span>Version</span><strong>${escapeHtml(listing.version || "—")}</strong></div>
    <div class="hero-stat optional"><span>Size</span><strong>${formatBytes(listing.fileSizeBytes)}</strong></div>
    <div class="hero-stat optional"><span>Price</span><strong>${escapeHtml(listing.price || "—")}</strong></div>
    <button class="score-ring" style="--score:${health?.score || 0}" id="heroHealthButton" aria-label="Open listing health"><strong>${health?.score ?? "—"}</strong></button>
  </div>
  <div class="hero-foot"><div class="hero-foot-group"><span>★ ${escapeHtml(rating)}</span><span>${escapeHtml(updated)}</span><span>↻ Apple public data</span></div><div class="hero-foot-group"><span>${countryFlag(state.country)} ${state.country.toUpperCase()} · ${deviceName(state.device)} rankings</span>${listing.url ? `<a href="${escapeAttr(listing.url)}" target="_blank" rel="noreferrer">View on App Store ↗</a>` : ""}</div></div>`;
  el("#heroHealthButton")?.addEventListener("click", () => switchTab("health"));
}

function filteredRows() {
  return countryRows().filter((row) => !state.filter || row.keyword.toLowerCase().includes(state.filter));
}

function countryRows() {
  return (state.data.rankings || []).filter((row) => row.country === state.country && row.device === state.device);
}

function renderRankings() {
  if (!state.data) return;
  const rows = filteredRows().sort((a, b) => (a.rank ?? 9999) - (b.rank ?? 9999));
  const metricRows = countryRows();
  const found = metricRows.filter((row) => row.found && row.rank != null);
  const ranks = found.map((row) => row.rank);
  const targetCount = state.data.targetCounts?.[`${state.country}:${state.device}`] || 0;
  const metrics = [
    ["Tracked", targetCount, `${countryFlag(state.country)} ${state.country.toUpperCase()} · ${deviceName(state.device)}`, "⌕"],
    ["Top 10", ranks.filter((rank) => rank <= 10).length, "Defend visibility", "↑"],
    ["Top 50", ranks.filter((rank) => rank <= 50).length, "Growth range", "◎"],
    ["Not visible", metricRows.filter((row) => !row.found).length, `Outside retrieved window`, "—"],
    ["Average rank", ranks.length ? (ranks.reduce((a, b) => a + b, 0) / ranks.length).toFixed(1) : "—", "Found keywords only", "∿"],
  ];
  el("#metrics").innerHTML = metrics.map(([label, value, note, icon]) => `<article class="metric"><span class="metric-label">${label}<b>${icon}</b></span><strong class="metric-value">${value}</strong><span class="metric-note">${note}</span></article>`).join("");

  el("#rankingsBody").innerHTML = rows.map((row) => {
    const changeClass = row.change === "NEW" ? "new" : row.change === "LOST" ? "lost" : row.change.startsWith("+") ? "up" : row.change.startsWith("-") ? "down" : "flat";
    const signalClass = row.opportunity.startsWith("Defend") ? "defend" : row.opportunity.includes("Growth") ? "growth" : row.opportunity.includes("visible") ? "absent" : "";
    return `<tr data-target-id="${row.targetId}" class="${row.targetId === state.selectedTarget ? "selected" : ""}">
      <td class="keyword-cell">${escapeHtml(row.keyword)}</td><td><span class="country-badge">${countryFlag(row.country)} ${row.country.toUpperCase()}</span></td><td><span class="device-badge ${escapeAttr(row.device)}">${deviceIcon(row.device)} ${deviceName(row.device)}</span></td>
      <td><span class="rank-number ${row.rank && row.rank <= 10 ? "top" : ""}">${row.found ? `#${row.rank}` : `>${row.resultLimit}`}</span></td>
      <td><span class="movement ${changeClass}">${escapeHtml(row.change)}</span></td><td><span class="signal ${signalClass}">${escapeHtml(shortOpportunity(row.opportunity))}</span></td>
      <td>${formatDate(row.checkedAt)}</td><td><button class="row-action" data-delete-target="${row.targetId}" title="Stop tracking">×</button></td>
    </tr>`;
  }).join("");
  const emptyTitle = el("#rankingsEmpty h3");
  const emptyCopy = el("#rankingsEmpty p");
  if (state.filter) {
    emptyTitle.textContent = "No matching keywords";
    emptyCopy.textContent = "Try a different keyword filter.";
  } else if (targetCount > 0) {
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
}

async function rankingClick(event) {
  const remove = event.target.closest("[data-delete-target]");
  if (remove) {
    event.stopPropagation();
    state.pendingDeactivateTarget = Number(remove.dataset.deleteTarget);
    el("#confirmModal").showModal();
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

function renderHealth() {
  const health = state.data.health;
  renderScreenshots();
  if (!health) {
    el("#healthScoreCard").innerHTML = `<div class="empty-state"><div class="empty-icon">!</div><h3>Listing unavailable</h3><p>${escapeHtml(state.data.listingError || "Apple did not return listing metadata.")}</p></div>`;
    el("#healthBreakdown").innerHTML = "";
    el("#healthSuggestions").innerHTML = "";
    return;
  }
  el("#healthScoreCard").innerHTML = `<p class="section-kicker">Listing health</p><div class="score-ring" style="--score:${health.score}"><strong>${health.score}</strong></div><h2>${escapeHtml(health.label)}</h2><p>Public listing completeness for ${state.country.toUpperCase()}. Unavailable Apple fields are excluded. This is a local heuristic—not an Apple or proprietary ASO score.</p>`;
  el("#healthBreakdown").innerHTML = health.items.map((item) => {
    const available = item.available !== false;
    const percent = Math.round(item.score / item.maximum * 100);
    const band = percent < 40 ? "low" : percent < 75 ? "mid" : "";
    const progress = available ? `<div class="progress"><i class="${band}" style="width:${percent}%"></i></div>` : `<div class="progress unavailable"><span>Not exposed</span></div>`;
    return `<div class="health-row ${available ? "" : "unavailable"}"><span class="health-row-icon">${healthIcon(item.key)}</span><div><strong>${escapeHtml(item.label)}</strong><small>${escapeHtml(item.detail)}</small></div>${progress}<div class="score-fraction">${available ? `${item.score}/${item.maximum}` : "N/A"}</div></div>`;
  }).join("");
  el("#healthSuggestions").innerHTML = `<div class="suggestion-list">${health.suggestions.map((item) => `<article class="suggestion"><i></i><p>${escapeHtml(item)}</p></article>`).join("")}</div>`;
  el("#healthMethodology").textContent = health.methodology;
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
  if (!state.appId) return;
  setBusy(true);
  try {
    const result = await request("/api/check", { method: "POST", body: { appId: state.appId, country: state.country, device: state.device } });
    toast(`Stored ${result.checks} check${result.checks === 1 ? "" : "s"} from ${result.searches} Apple search${result.searches === 1 ? "" : "es"}.`);
    await loadDashboard({ quiet: true });
  } catch (error) { toast(error.message, true); }
  finally { setBusy(false); }
}

async function addKeyword(event) {
  event.preventDefault();
  const countries = all('#countryChecks input:checked').map((input) => input.value);
  if (!countries.length) { toast("Select at least one storefront.", true); return; }
  const devices = all('#deviceChecks input:checked').map((input) => input.value);
  if (!devices.length) { toast("Select at least one device.", true); return; }
  setBusy(true);
  try {
    const result = await request("/api/keywords", { method: "POST", body: { appId: state.appId, keywords: el("#keywordInput").value, countries, devices } });
    el("#keywordModal").close();
    el("#keywordForm").reset();
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

function healthValue(health) { return `<span class="health-chip">${health.score}</span> <strong>${escapeHtml(health.label)}</strong>`; }
function countryFlag(code) { return [...String(code).toUpperCase()].map((char) => String.fromCodePoint(127397 + char.charCodeAt(0))).join(""); }
function deviceName(device) { return device === "ipad" ? "iPad" : "iPhone"; }
function deviceIcon(device) { return device === "ipad" ? "▭" : "▯"; }
function screenshotValue(listing) { return listing.screenshotStatus === "available" ? String(listing.screenshotCount) : "Not exposed"; }
function ratingValue(app) { return app.averageRating ? `★ ${app.averageRating.toFixed(1)} · ${formatCompact(app.ratingCount)} ratings` : "No rating returned"; }
function shortOpportunity(value) { return value.replace(/\s*\([^)]*\)/, ""); }
function healthIcon(key) { return ({ title: "T", description: "≡", screenshots: "▣", ratings: "★", freshness: "↻", localization: "◎" })[key] || "·"; }
function initials(value) { return (value || "AS").split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase(); }
function formatDate(value) { return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(value)) : "—"; }
function relativeDate(value) {
  const days = Math.max(0, Math.floor((Date.now() - +new Date(value)) / 86400000));
  if (days === 0) return "Updated today";
  if (days === 1) return "Updated yesterday";
  return `Updated ${days} days ago`;
}
function formatCompact(value) { return new Intl.NumberFormat(undefined, { notation: Number(value) >= 1000 ? "compact" : "standard", maximumFractionDigits: 1 }).format(value || 0); }
function formatBytes(value) { if (!value) return "—"; return `${(value / 1024 / 1024).toFixed(0)} MB`; }
function escapeHtml(value) { return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]); }
function escapeAttr(value) { return escapeHtml(value); }
