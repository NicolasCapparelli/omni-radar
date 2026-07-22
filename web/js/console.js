// The test console: the request bar, the SCAN action, the status strip, and the
// adaptive live-refresh loop. Owns fetching; delegates rendering to table/device
// and selection to the injected controller callbacks.

import { state, DEFAULTS } from "./state.js";
import { $ } from "./dom.js";
import { escapeHtml } from "./format.js";
import { getNearby, getMarineNearby } from "./api.js";
import { renderTable, COLSPAN } from "./table.js";
import { setConn, refreshHealth } from "./status.js";
import { startScroll } from "./device.js";

let select = () => {};
let onRowSelect = () => {};

export function initConsole(callbacks) {
  ({ select, onRowSelect } = callbacks);

  $("btnScan").addEventListener("click", scan);
  document.querySelectorAll(".request-bar input").forEach((el) =>
    el.addEventListener("keydown", (e) => { if (e.key === "Enter") scan(); }));

  $("liveToggle").addEventListener("change", () => {
    if ($("liveToggle").checked) scan().then(scheduleLive);
    else { clearTimeout(state.liveTimeout); $("pollInfo").textContent = ""; }
  });
  $("pollInterval").addEventListener("change", () => {
    if ($("liveToggle").checked) scheduleLive();
  });
}

// Reflect the current mode in the request bar (channel field is marine-only),
// then re-scan against the now-active source. Called when MODE is toggled.
export function applyMode() {
  $("channelField").hidden = state.mode !== "MARINE";
  document.body.classList.toggle("marine-theme", state.mode === "MARINE");
  // Clear the previous mode's targets immediately so stale rows/card don't
  // linger on screen until the new fetch resolves (the switch "flicker").
  clearTimeout(state.liveTimeout);
  clearTimeout(state.warmupTimeout);
  state.aircraft = [];
  state.selected = -1;
  renderTable(onRowSelect);
  $("aircraftBody").innerHTML =
    `<tr class="empty-row"><td colspan="${COLSPAN}">Loading ${state.mode}…</td></tr>`;
  select(-1);
  $("statTracked").textContent = "—";
  scan().then(() => { if ($("liveToggle").checked) scheduleLive(); });
}

export async function scan() {
  return state.mode === "MARINE" ? scanMarine() : scanAir();
}

async function scanAir() {
  const lat = $("inLat").value.trim();
  const lon = $("inLon").value.trim();
  const radius = $("inRadius").value.trim();

  // Remember the home position for the radar (fall back to defaults).
  state.user = {
    lat: parseFloat(lat) || DEFAULTS.lat,
    lon: parseFloat(lon) || DEFAULTS.lon,
    radius: parseFloat(radius) || DEFAULTS.radius,
  };

  setConn("busy", "Scanning…");
  try {
    const { aircraft, recommendedPoll, query } = await getNearby({ lat, lon, radius });
    $("requestUrl").textContent = `GET /api/nearby?${query}`;
    if (recommendedPoll) state.recommendedPoll = recommendedPoll;

    state.aircraft = aircraft;
    renderTable(onRowSelect);
    $("statTracked").textContent = aircraft.length;
    $("statUpdated").textContent = new Date().toLocaleTimeString();
    setConn("ok", `${aircraft.length} targets`);

    if (aircraft.length) {
      select(0);
      if (state.trackMode === "auto") startScroll();
    } else {
      select(-1);
    }
  } catch (err) {
    setConn("err", "Error");
    $("statUpdated").textContent = "failed";
    console.error(err);
    $("aircraftBody").innerHTML =
      `<tr class="empty-row"><td colspan="${COLSPAN}">${escapeHtml(err.message)}</td></tr>`;
  }
  refreshHealth();
}

async function scanMarine(isWarmupRetry = false) {
  const lat = $("inLat").value.trim();
  const lon = $("inLon").value.trim();
  const radius = $("inRadius").value.trim();
  const channel = ($("inChannel").value.trim() || DEFAULTS.channel);

  state.user = {
    lat: parseFloat(lat) || DEFAULTS.lat,
    lon: parseFloat(lon) || DEFAULTS.lon,
    radius: parseFloat(radius) || DEFAULTS.radius,
  };

  setConn("busy", "Scanning…");
  try {
    const { vessels, recommendedPoll, query } = await getMarineNearby({
      channel, lat, lon, radius,
    });
    $("requestUrl").textContent = `GET ${query}`;
    if (recommendedPoll) state.recommendedPoll = recommendedPoll;

    state.aircraft = vessels;  // generic "current targets" array
    renderTable(onRowSelect);
    $("statTracked").textContent = vessels.length;
    $("statUpdated").textContent = new Date().toLocaleTimeString();

    if (vessels.length) {
      setConn("ok", `${vessels.length} vessels`);
      select(0);
      if (state.trackMode === "auto") startScroll();
    } else {
      select(-1);
      setConn("ok", "channel warming up…");
      $("aircraftBody").innerHTML =
        `<tr class="empty-row"><td colspan="${COLSPAN}">Channel warming up — the AIS socket just opened. Vessels appear within a few seconds.</td></tr>`;
      // One-shot retry to catch the socket warm-up without a manual re-scan.
      if (!isWarmupRetry) {
        clearTimeout(state.warmupTimeout);
        state.warmupTimeout = setTimeout(() => {
          if (state.mode === "MARINE") scanMarine(true);
        }, 2500);
      }
    }
  } catch (err) {
    setConn("err", "Error");
    $("statUpdated").textContent = "failed";
    console.error(err);
    $("aircraftBody").innerHTML =
      `<tr class="empty-row"><td colspan="${COLSPAN}">${escapeHtml(err.message)}</td></tr>`;
  }
  refreshHealth();
}

// ── Adaptive live refresh ───────────────────────────────────────────────────
// Effective interval = max(user baseline, server recommendation, 5s floor).
function effectivePoll() {
  const manual = parseInt($("pollInterval").value, 10) || 30;
  return Math.max(5, manual, state.recommendedPoll || 0);
}

function scheduleLive() {
  clearTimeout(state.liveTimeout);
  if (!$("liveToggle").checked) return;
  const eff = effectivePoll();
  const manual = parseInt($("pollInterval").value, 10) || 30;
  $("pollInfo").textContent =
    state.recommendedPoll > manual ? `backed off to ${eff}s (low credits)` : `every ${eff}s`;
  state.liveTimeout = setTimeout(() => scan().then(scheduleLive), eff * 1000);
}
