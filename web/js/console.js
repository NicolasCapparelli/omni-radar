// The test console: the request bar, the SCAN action, the status strip, and the
// adaptive live-refresh loop. Owns fetching; delegates rendering to table/device
// and selection to the injected controller callbacks.

import { state, DEFAULTS } from "./state.js";
import { $ } from "./dom.js";
import { escapeHtml } from "./format.js";
import { getNearby } from "./api.js";
import { renderTable } from "./table.js";
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

export async function scan() {
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
      `<tr class="empty-row"><td colspan="11">${escapeHtml(err.message)}</td></tr>`;
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
