"use strict";

// ── State ────────────────────────────────────────────────────────────────
const state = {
  aircraft: [],
  selected: -1,
  mode: "AIR",          // AIR | MARINE
  trackMode: "auto",    // auto | manual
  view: "data",         // data | radar
  powered: true,
  user: { lat: 40.7580, lon: -73.9965, radius: 15 },
  recommendedPoll: 30,
  scrollTimer: null,
  liveTimeout: null,
};

const SCROLL_MS = 5000;
const LIVE_MS = 30000;

const $ = (id) => document.getElementById(id);

// Vehicle-type -> Material Symbol (close-enough icons for a dev tool).
const TYPE_ICON = {
  Plane: "flight", Seaplane: "flight", Amphibian: "flight",
  Helicopter: "mode_fan", Gyrocopter: "mode_fan", Tiltrotor: "mode_fan",
  Glider: "paragliding", Ultralight: "paragliding", Skydiver: "paragliding",
  "Lighter-than-air": "cloud", Drone: "mode_fan", Spacecraft: "rocket_launch",
  "Surface Vehicle": "directions_car", Obstacle: "warning",
};
const iconFor = (t) => TYPE_ICON[t] || "flight";
const classChip = (c) => "chip-" + String(c || "unknown").toLowerCase().replace(/[^a-z]/g, "");

// ── Formatting helpers ─────────────────────────────────────────────────────
const commas = (n) => (n ?? 0).toLocaleString("en-US");

function vspdParts(fpm) {
  if (!fpm) return { cls: "level", text: "— level" };
  if (fpm > 0) return { cls: "climb", text: `▲ ${commas(fpm)} fpm` };
  return { cls: "descent", text: `▼ ${commas(Math.abs(fpm))} fpm` };
}

function routeStr(a) {
  return `${a.origin || "N/A"} → ${a.destination || "N/A"}`;
}

// ── Data fetching ──────────────────────────────────────────────────────────
async function scan() {
  const lat = $("inLat").value.trim();
  const lon = $("inLon").value.trim();
  const radius = $("inRadius").value.trim();
  const qs = `lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}&radius=${encodeURIComponent(radius)}`;
  $("requestUrl").textContent = `GET /api/nearby?${qs}`;

  // Capture the user's position/radius for the radar view (fall back to NYC).
  state.user = {
    lat: parseFloat(lat) || 40.7580,
    lon: parseFloat(lon) || -73.9965,
    radius: parseFloat(radius) || 15,
  };

  setConn("busy", "Scanning…");
  try {
    const resp = await fetch(`/api/nearby?${qs}`);
    if (!resp.ok) {
      const body = await resp.text();
      throw new Error(`HTTP ${resp.status}: ${body.slice(0, 200)}`);
    }
    const data = await resp.json();
    const rec = resp.headers.get("X-Recommended-Poll-Seconds");
    if (rec) state.recommendedPoll = parseInt(rec) || state.recommendedPoll;
    state.aircraft = Array.isArray(data) ? data : [];
    renderTable();
    $("statTracked").textContent = state.aircraft.length;
    $("statUpdated").textContent = new Date().toLocaleTimeString();
    setConn("ok", `${state.aircraft.length} targets`);

    if (state.aircraft.length) {
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

async function refreshHealth() {
  try {
    const h = await (await fetch("/health")).json();
    $("statCache").textContent = commas(h.cache_entries ?? 0);
    const p = h.route_providers || {};
    const dot = (label, on) =>
      `<span class="pdot"><span class="dot ${on ? "dot-ok" : "dot-idle"}"></span>${label}</span>`;
    $("statProviders").innerHTML =
      dot("OpenSky", h.opensky_auth) + dot("adsbdb", p.adsbdb) + dot("FA", p.flightaware);
  } catch {
    $("statProviders").textContent = "unavailable";
  }
}

// ── Table rendering ──────────────────────────────────────────────────────
function renderTable() {
  const body = $("aircraftBody");
  if (!state.aircraft.length) {
    body.innerHTML = `<tr class="empty-row"><td colspan="11">No targets in range.</td></tr>`;
    return;
  }
  body.innerHTML = state.aircraft.map((a, i) => {
    const vs = vspdParts(a.vertical_speed_fpm);
    const emergency = a.emergency && a.emergency !== "None";
    const special = a.special_designation && a.special_designation !== "None";
    const rowCls = [emergency ? "emergency" : "", a.on_ground ? "grounded" : ""].join(" ").trim();
    const flag = emergency
      ? `<span class="flag flag-emergency">${escapeHtml(a.emergency)}</span>`
      : special
        ? `<span class="flag flag-special">${escapeHtml(a.special_designation)}</span>`
        : "";
    return `
      <tr data-i="${i}" class="${rowCls}">
        <td class="ti"><span class="material-symbols-outlined">${iconFor(a.vehicle_type)}</span></td>
        <td class="cs">${escapeHtml(a.callsign)}</td>
        <td>${escapeHtml(a.vehicle_type)}</td>
        <td>${escapeHtml(a.model_code)}</td>
        <td>${escapeHtml(a.operator || a.airline)}</td>
        <td>${escapeHtml(routeStr(a))}</td>
        <td class="num">${commas(a.altitude_feet)}</td>
        <td class="num">${commas(a.speed_knots)}</td>
        <td class="num ${vs.cls === "climb" ? "vs-climb" : vs.cls === "descent" ? "vs-descent" : "vs-level"}">${vs.text.split(" ")[0]}</td>
        <td><span class="chip ${classChip(a.operator_class)}">${escapeHtml(a.operator_class)}</span></td>
        <td>${flag}</td>
      </tr>`;
  }).join("");

  body.querySelectorAll("tr[data-i]").forEach((tr) => {
    tr.addEventListener("click", () => {
      // Manual selection from the table locks tracking.
      if (state.trackMode === "auto") setTrackMode("manual");
      select(Number(tr.dataset.i));
    });
  });
  highlightRow();
}

function highlightRow() {
  document.querySelectorAll(".aircraft-table tr").forEach((tr) =>
    tr.classList.toggle("selected", Number(tr.dataset.i) === state.selected));
}

// ── Selection + device views ───────────────────────────────────────────────
function select(i) {
  state.selected = i;
  highlightRow();
  renderCard();
  renderRadar();
  updateView();
  $("rawJson").textContent =
    i >= 0 ? JSON.stringify(state.aircraft[i], null, 2) : "// select an aircraft";
}

// Decide which of the three body views is visible.
function updateView() {
  const a = state.aircraft[state.selected];
  const empty = $("lcdEmpty"), card = $("lcdCard"), radar = $("lcdRadar");
  if (!a) {
    empty.hidden = false; card.hidden = true; radar.hidden = true;
    $("lcdIndex").textContent = "0 / 0 TRACKED";
    return;
  }
  empty.hidden = true;
  const radarActive = state.view === "radar" && state.mode === "AIR";
  radar.hidden = !radarActive;
  card.hidden = radarActive;
}

function renderCard() {
  const a = state.aircraft[state.selected];
  if (!a) return;

  $("lcdCallsign").textContent = a.callsign || "--------";
  $("lcdOrigin").textContent = a.origin || "N/A";
  $("lcdDest").textContent = a.destination || "N/A";
  $("lcdOriginName").textContent = a.origin_name || "";
  $("lcdDestName").textContent = a.destination_name || "";
  $("lcdAirline").textContent = a.operator && a.operator !== "Unknown" ? a.operator : a.airline;
  $("lcdTypeIcon").textContent = iconFor(a.vehicle_type);
  $("lcdModel").textContent = `${a.model_code} · ${a.model_name}`;
  $("lcdAlt").textContent = `${commas(a.altitude_feet)} ft`;
  $("lcdSpd").textContent = `${commas(a.speed_knots)} kt`;
  $("lcdHdg").textContent = `${a.heading_degrees}°`;
  $("lcdHdgArrow").style.transform = `rotate(${a.heading_degrees || 0}deg)`;

  const vs = vspdParts(a.vertical_speed_fpm);
  const vspdEl = $("lcdVspd");
  vspdEl.textContent = vs.text;
  vspdEl.className = "lcd-vspd " + vs.cls;

  const badges = [];
  if (a.operator_class && a.operator_class !== "Unknown")
    badges.push(`<span class="chip ${classChip(a.operator_class)}">${escapeHtml(a.operator_class)}</span>`);
  if (a.special_designation && a.special_designation !== "None")
    badges.push(`<span class="chip chip-military">${escapeHtml(a.special_designation)}</span>`);
  $("lcdBadges").innerHTML = badges.join("");

  const emergency = a.emergency && a.emergency !== "None";
  $("lcdEmergency").hidden = !emergency;
  $("lcdEmergency").textContent = `⚠ ${a.emergency}`;
  $("lcd").classList.toggle("alert", emergency);

  $("lcdIndex").textContent = `${state.selected + 1} / ${state.aircraft.length} TRACKED`;
}

// Relative bearing + distance (miles) from the user to the aircraft.
function relativePosition(user, a) {
  const milesPerLat = 69.0;
  const milesPerLon = 69.0 * Math.cos((user.lat * Math.PI) / 180);
  const dNorth = (a.latitude - user.lat) * milesPerLat;
  const dEast = (a.longitude - user.lon) * milesPerLon;
  const dist = Math.hypot(dNorth, dEast);
  const bearing = Math.atan2(dEast, dNorth); // radians, clockwise from north
  return { dist, bearing };
}

const RADAR_R = 84; // px (scope is 168px diameter)

function renderRadar() {
  const a = state.aircraft[state.selected];
  const planeEl = $("radarPlane"), infoEl = $("radarPlaneInfo");
  $("radarRange").textContent = `${state.user.radius} mi`;

  if (!a || a.latitude == null || a.longitude == null) {
    planeEl.hidden = true; infoEl.hidden = true;
    return;
  }
  const { dist, bearing } = relativePosition(state.user, a);
  const r = Math.min(dist / state.user.radius, 1) * RADAR_R;
  const x = RADAR_R + r * Math.sin(bearing);
  const y = RADAR_R - r * Math.cos(bearing);

  planeEl.hidden = false;
  planeEl.style.left = `${x}px`;
  planeEl.style.top = `${y}px`;
  $("radarPlaneIcon").textContent = iconFor(a.vehicle_type);
  $("radarPlaneIcon").style.transform = `rotate(${a.heading_degrees || 0}deg)`;

  infoEl.hidden = false;
  infoEl.innerHTML =
    `<b>${escapeHtml(a.callsign)}</b><br>${commas(a.altitude_feet)} ft<br>${dist.toFixed(1)} mi`;
  const onLeft = x > RADAR_R;
  infoEl.style.left = `${onLeft ? x - 12 : x + 12}px`;
  infoEl.style.top = `${Math.min(Math.max(y - 4, -10), 140)}px`;
  infoEl.style.transform = onLeft ? "translateX(-100%)" : "none";
  infoEl.style.textAlign = onLeft ? "right" : "left";
}

// ── Auto-scroll (mirrors the hardware's Auto-Cycle mode) ────────────────────
function startScroll() {
  stopScroll();
  if (!state.powered || state.trackMode !== "auto" || !state.aircraft.length) return;
  state.scrollTimer = setInterval(() => {
    state.selected = (state.selected + 1) % state.aircraft.length;
    select(state.selected);
  }, SCROLL_MS);
}
function stopScroll() {
  if (state.scrollTimer) { clearInterval(state.scrollTimer); state.scrollTimer = null; }
}

function setTrackMode(mode) {
  state.trackMode = mode;
  const badge = $("lcdTrackMode");
  if (mode === "auto") {
    badge.textContent = "AUTO-CYCLING";
    badge.classList.remove("lock");
    $("actionHint").textContent = "Auto-Scroll: cycling every 5s. Press ACTION to lock.";
    startScroll();
  } else {
    badge.textContent = "MANUAL LOCK";
    badge.classList.add("lock");
    $("actionHint").textContent = "Manual-Lock: press ACTION to step to the next target.";
    stopScroll();
  }
}

// ── Hardware buttons ────────────────────────────────────────────────────────
function setupButtons() {
  $("btnPower").addEventListener("click", () => {
    state.powered = !state.powered;
    $("lcdOff").hidden = state.powered;
    $("btnPower").classList.toggle("active", !state.powered);
    if (!state.powered) stopScroll();
    else if (state.trackMode === "auto") startScroll();
  });

  $("btnMode").addEventListener("click", () => {
    state.mode = state.mode === "AIR" ? "MARINE" : "AIR";
    $("modePill").textContent = state.mode;
    $("lcdModeIcon").textContent = state.mode === "AIR" ? "flight" : "sailing";
    // Radar is AIR-only; drop back to the data view when leaving AIR.
    if (state.mode !== "AIR" && state.view === "radar") {
      state.view = "data";
      $("btnAlt").classList.remove("active");
    }
    updateView();
  });

  $("btnAlt").addEventListener("click", () => {
    if (!state.powered) return;
    if (state.mode !== "AIR") {
      $("actionHint").textContent = "Radar view is available in AIR mode only.";
      return;
    }
    state.view = state.view === "radar" ? "data" : "radar";
    $("btnAlt").classList.toggle("active", state.view === "radar");
    $("actionHint").textContent = state.view === "radar"
      ? "Radar: target position relative to you (North up)."
      : (state.trackMode === "auto"
          ? "Auto-Scroll: cycling every 5s. Press ACTION to lock."
          : "Manual-Lock: press ACTION to step to the next target.");
    renderRadar();
    updateView();
  });

  $("btnAction").addEventListener("click", () => {
    if (!state.powered) return;
    if (state.trackMode === "auto") {
      setTrackMode("manual");
    } else if (state.aircraft.length) {
      // Step to the next target while locked.
      state.selected = (state.selected + 1) % state.aircraft.length;
      select(state.selected);
    }
  });
}

// ── Misc ─────────────────────────────────────────────────────────────────
function setConn(kind, text) {
  const dot = $("connDot");
  dot.className = "dot " + ({ ok: "dot-ok", busy: "dot-busy", err: "dot-err" }[kind] || "dot-idle");
  $("connText").textContent = text;
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function setupLive() {
  $("liveToggle").addEventListener("change", () => {
    if ($("liveToggle").checked) {
      scan().then(scheduleLive);
    } else {
      clearTimeout(state.liveTimeout);
      $("pollInfo").textContent = "";
    }
  });
  $("pollInterval").addEventListener("change", () => {
    if ($("liveToggle").checked) scheduleLive();
  });
}

function effectivePoll() {
  const manual = parseInt($("pollInterval").value) || 30;
  return Math.max(5, manual, state.recommendedPoll || 0);
}

function scheduleLive() {
  clearTimeout(state.liveTimeout);
  if (!$("liveToggle").checked) return;
  const eff = effectivePoll();
  const manual = parseInt($("pollInterval").value) || 30;
  $("pollInfo").textContent =
    state.recommendedPoll > manual ? `backed off to ${eff}s (low credits)` : `every ${eff}s`;
  state.liveTimeout = setTimeout(() => scan().then(scheduleLive), eff * 1000);
}

// ── Init ─────────────────────────────────────────────────────────────────
window.addEventListener("DOMContentLoaded", () => {
  setupButtons();
  setupLive();
  setupUsage();
  setTrackMode("auto");
  $("btnScan").addEventListener("click", scan);
  document.querySelectorAll(".request-bar input").forEach((el) =>
    el.addEventListener("keydown", (e) => { if (e.key === "Enter") scan(); }));
  refreshHealth();
  scan();
});

// ── Usage view ─────────────────────────────────────────────────────────────
const usage = { timer: null };

function showView(which) {
  const isUsage = which === "usage";
  $("consoleView").hidden = isUsage;
  $("usageView").hidden = !isUsage;
  $("navConsole").classList.toggle("active", !isUsage);
  $("navUsage").classList.toggle("active", isUsage);
  if (isUsage) {
    fetchMetrics();
    if ($("usageLive").checked) startUsageTimer();
  } else {
    stopUsageTimer();
  }
}

function startUsageTimer() {
  stopUsageTimer();
  usage.timer = setInterval(fetchMetrics, 5000);
}
function stopUsageTimer() {
  if (usage.timer) { clearInterval(usage.timer); usage.timer = null; }
}

function fmtUptime(s) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return h ? `${h}h ${m}m` : m ? `${m}m ${sec}s` : `${sec}s`;
}

async function fetchMetrics() {
  try {
    const m = await (await fetch("/api/metrics")).json();
    renderMetrics(m);
  } catch (err) {
    console.error("metrics fetch failed", err);
  }
}

function renderMetrics(m) {
  const ext = m.external_calls, sv = m.savings;
  $("usageUptime").textContent = `Uptime ${fmtUptime(m.uptime_seconds)} · ${commas(m.requests.nearby)} scans · ${commas(m.requests.aircraft_returned)} aircraft served`;

  $("hExternal").textContent = commas(ext.total);
  $("hAvoided").textContent = commas(sv.calls_avoided_total);
  $("hAvoidedDetail").textContent = `${commas(sv.cache_hits)} cache · ${commas(sv.planes_filtered)} filtered`;
  $("hRatio").textContent = `${Math.round(sv.local_served_ratio * 100)}%`;
  $("hFa").textContent = commas(ext.flightaware.requests);

  const prov = (name, p, key) => `
    <tr><td class="prov">${name}</td>
      <td class="num">${commas(p.requests)}</td>
      <td class="num">${key ? commas(p.found) : "—"}</td>
      <td class="num">${key ? commas(p.not_found) : "—"}</td>
      <td class="num">${key ? commas(p.rate_limited) : "—"}</td>
      <td class="num">${commas(p.errors)}</td></tr>`;
  $("providerRows").innerHTML =
    prov("OpenSky", ext.opensky, false) +
    prov("adsbdb", ext.adsbdb, true) +
    prov("FlightAware", ext.flightaware, true);
  $("openskyNote").textContent =
    `OpenSky is 1 call per scan (the bulk live feed); adsbdb & FlightAware are per-callsign route lookups. Cache entries: ${commas(m.cache_entries ?? 0)}.`;

  const os = ext.opensky;
  const credits = os.credits_remaining;
  $("openskyCredits").textContent = credits == null
    ? `OpenSky daily credits: not yet observed — run a scan. (429s so far: ${commas(os.rate_limited)})`
    : `OpenSky daily credits remaining: ${commas(credits)} · rate-limited (429): ${commas(os.rate_limited)}`;
  $("recPoll").textContent =
    `Recommended poll interval: ${m.recommended_poll_seconds}s — data refreshes every ~5s; backs off automatically as credits run low.`;

  const item = (icon, label, val) =>
    `<li><span><span class="material-symbols-outlined">${icon}</span>${label}</span><b>${commas(val)}</b></li>`;
  $("savingsList").innerHTML =
    item("bolt", "Route cache hits (no call)", sv.cache_hits) +
    item("filter_alt", "Grounded planes filtered", sv.planes_filtered) +
    item("dns", "Offline aircraft-DB enrichments", sv.offline_db_enrichments) +
    item("block", "Known no-route (negatively cached)", m.route_resolution.not_found);

  // Bars: cache hits, filtered, provider route calls (cost).
  const providerRouteCalls = ext.adsbdb.requests + ext.flightaware.requests;
  const max = Math.max(sv.cache_hits, sv.planes_filtered, providerRouteCalls, 1);
  $("barCache").style.width = `${(sv.cache_hits / max) * 100}%`;
  $("barFiltered").style.width = `${(sv.planes_filtered / max) * 100}%`;
  $("barCalls").style.width = `${(providerRouteCalls / max) * 100}%`;
  $("numCache").textContent = commas(sv.cache_hits);
  $("numFiltered").textContent = commas(sv.planes_filtered);
  $("numCalls").textContent = commas(providerRouteCalls);
}

function setupUsage() {
  $("navConsole").addEventListener("click", () => showView("console"));
  $("navUsage").addEventListener("click", () => showView("usage"));
  $("btnUsageRefresh").addEventListener("click", fetchMetrics);
  $("usageLive").addEventListener("change", (e) =>
    e.target.checked ? startUsageTimer() : stopUsageTimer());
  $("btnUsageReset").addEventListener("click", async () => {
    await fetch("/api/metrics/reset");
    fetchMetrics();
  });
}
