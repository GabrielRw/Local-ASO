const onboarding = { step: 0, busy: false, seen: false };

function bindOnboardingEvents() {
  el("#setupButton").addEventListener("click", openOnboarding);
  el("#onboardingForm").addEventListener("submit", submitOnboarding);
  el("#onboardingBack").addEventListener("click", () => showOnboardingStep(0));
  el("#onboardingClose").addEventListener("click", dismissOnboarding);
  el("#onboardingExistingApp").addEventListener("change", toggleOnboardingAppField);
  el("#onboardingModal").addEventListener("cancel", (event) => {
    event.preventDefault();
    if (!onboarding.busy) dismissOnboarding();
  });
}

function maybeOpenOnboarding() {
  if (!onboarding.seen && state.data?.onboarding?.shouldOpen) openOnboarding();
}

function openOnboarding() {
  if (!state.data || el("#onboardingModal").open) return;
  onboarding.seen = true;
  el("#sidebar").classList.remove("open");
  el("#onboardingForm").reset();
  const apps = (state.data.apps || []).filter((app) => app.active);
  el("#onboardingExistingField").hidden = !apps.length;
  el("#onboardingExistingApp").innerHTML = apps.map((app) =>
    `<option value="${app.appleAppId}" ${app.appleAppId === state.appId ? "selected" : ""}>${escapeHtml(app.name)}</option>`
  ).join("") + `<option value="">Add a different app</option>`;
  const countries = (state.data.countries || []).filter((country) => country.active);
  el("#onboardingCountry").innerHTML = countries.map((country) =>
    `<option value="${country.code}" ${country.code === state.country ? "selected" : ""}>${countryFlag(country.code)} ${escapeHtml(country.name)}</option>`
  ).join("");
  el("#onboardingDevice").value = state.device;
  toggleOnboardingAppField();
  showOnboardingStep(0, false);
  el("#onboardingModal").showModal();
  el("#onboardingTitle").focus();
}

function toggleOnboardingAppField() {
  el("#onboardingAppIdField").hidden = Boolean(el("#onboardingExistingApp").value);
}

function showOnboardingStep(step, focus = true) {
  onboarding.step = step;
  el("#onboardingTitle").textContent = step === 0 ? "A little setup. A clearer view." : "Start tracking your keywords.";
  el("#onboardingIntro").textContent = step === 0
    ? "Choose your app and storefront. Your workspace stays on this computer."
    : "Add a few search terms and we’ll run your first ranking check automatically.";
  el("#onboardingStepLabel").textContent = `Step ${step + 1} of 2`;
  all("[data-setup-step]").forEach((panel) => { panel.hidden = Number(panel.dataset.setupStep) !== step; });
  all("[data-setup-progress]").forEach((item) => {
    const index = Number(item.dataset.setupProgress);
    item.classList.toggle("current", index === step);
    item.classList.toggle("complete", index < step);
    if (index === step) item.setAttribute("aria-current", "step");
    else item.removeAttribute("aria-current");
    item.querySelector("span").textContent = index < step ? "✓" : String(index + 1);
  });
  el("#onboardingBack").hidden = step === 0;
  el("#onboardingNext").textContent = step === 1 ? "Open dashboard" : "Continue";
  el("#onboardingError").hidden = true;
  if (step === 1) {
    const app = state.data.apps.find((item) => item.appleAppId === state.appId);
    el("#onboardingSummary").innerHTML = `<div class="setup-summary-row"><span aria-hidden="true">↗</span><div><strong>${escapeHtml(app?.name || "Your app")}</strong><small>${countryFlag(state.country)} ${escapeHtml(state.country.toUpperCase())} storefront · Public App Store rankings</small></div></div>`;
    el("#onboardingNextTip").innerHTML = "Use <strong>Run check</strong> to refresh rankings later. Add more apps, keywords, countries, or devices from the dashboard anytime.";
  }
  if (focus) el("#onboardingTitle").focus();
  el("#onboardingModal").scrollTop = 0;
}

function setOnboardingBusy(busy, label = "") {
  onboarding.busy = busy;
  el("#onboardingModal").setAttribute("aria-busy", String(busy));
  all("#onboardingForm button, #onboardingForm input, #onboardingForm select, #onboardingForm textarea").forEach((control) => { control.disabled = busy; });
  el("#onboardingNext").textContent = busy ? label || "Working…" : onboarding.step === 1 ? "Open dashboard" : "Continue";
}

function onboardingError(message) {
  el("#onboardingError").textContent = message;
  el("#onboardingError").hidden = false;
}

function onboardingAppleId(value) {
  const input = value.trim();
  let digits = input;
  if (!/^\d+$/.test(input)) {
    let url;
    try { url = new URL(input); } catch { throw new Error("Enter a numerical app ID or the full App Store link."); }
    if (url.hostname !== "apps.apple.com" || !["https:", "http:"].includes(url.protocol)) throw new Error("Use an App Store link from apps.apple.com.");
    digits = url.pathname.match(/\/id(\d+)\/?$/)?.[1] || "";
  }
  const id = Number(digits);
  if (!/^\d+$/.test(digits) || !Number.isSafeInteger(id) || id <= 0) throw new Error("The App Store link must contain an app ID, such as /id123456789.");
  return id;
}

async function submitOnboarding(event) {
  event.preventDefault();
  if (onboarding.busy) return;
  el("#onboardingError").hidden = true;
  try {
    if (onboarding.step === 0) {
      const existing = el("#onboardingExistingApp").value;
      const appleId = existing ? Number(existing) : onboardingAppleId(el("#onboardingAppId").value);
      const country = el("#onboardingCountry").value;
      if (!country) throw new Error("Choose a storefront before continuing.");
      setOnboardingBusy(true, existing ? "Loading app…" : "Finding app…");
      if (!existing) await request("/api/apps", { method: "POST", body: { appleId, country } });
      state.appId = appleId;
      state.country = country;
      state.selectedTarget = null;
      state.filter = "";
      el("#keywordFilter").value = "";
      await loadDashboard({ quiet: true });
      showOnboardingStep(1);
    } else {
      const keywords = el("#onboardingKeywords").value.trim();
      const device = el("#onboardingDevice").value;
      setOnboardingBusy(true, keywords ? "Checking keywords…" : "Opening dashboard…");
      let checkResult;
      if (keywords) checkResult = await request("/api/keywords", {
        method: "POST", body: { appId: state.appId, keywords, countries: [state.country], devices: [device] },
      });
      state.data.onboarding = await request("/api/onboarding/complete", { method: "POST", body: {} });
      state.device = device;
      el("#onboardingModal").close();
      await loadDashboard({ quiet: true });
      const failures = checkResult?.automaticCheck?.failures || 0;
      const count = checkResult?.keywordsRequested || 0;
      toast(checkResult ? `${count} keyword${count === 1 ? "" : "s"} added. ${failures ? `${failures} Apple searches failed; use Run check to retry.` : "Your first rankings are ready."}` : "Your local workspace is ready.", failures > 0);
    }
  } catch (error) {
    onboardingError(error.message);
  } finally { setOnboardingBusy(false); }
}

async function dismissOnboarding() {
  if (onboarding.busy) return;
  setOnboardingBusy(true);
  try {
    state.data.onboarding = await request("/api/onboarding/complete", { method: "POST", body: {} });
    el("#onboardingModal").close();
  } catch (error) { onboardingError(error.message); }
  finally { setOnboardingBusy(false); }
}
