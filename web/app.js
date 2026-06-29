"use strict";

// ── State ────────────────────────────────────────────────────────────────
const state = {
  aircraft: [],
  selected: -1,
  mode: "AIR",          // AIR | MARINE
  trackMode: "auto",    // auto | manual
  powered: true,
  scrollTimer: null,
  liveTimer: null,
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

  setConn("busy", "Scanning…");
  try {
    const resp = await fetch(`/api/nearby?${qs}`);
    if (!resp.ok) {
      const body = await resp.text();
      throw new Error(`HTTP ${resp.status}: ${body.slice(0, 200)}`);
    }
    const data = await resp.json();
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

// ── Selection + device LCD ─────────────────────────────────────────────────
function select(i) {
  state.selected = i;
  highlightRow();
  renderLCD();
  $("rawJson").textContent =
    i >= 0 ? JSON.stringify(state.aircraft[i], null, 2) : "// select an aircraft";
}

function renderLCD() {
  const card = $("lcdCard");
  const empty = $("lcdEmpty");
  const a = state.aircraft[state.selected];

  if (!a) {
    card.hidden = true;
    empty.hidden = false;
    $("lcdIndex").textContent = "0 / 0 TRACKED";
    return;
  }
  empty.hidden = true;
  card.hidden = false;

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

  // Badges: operator class + special designation.
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
  $("liveToggle").addEventListener("change", (e) => {
    if (e.target.checked) {
      state.liveTimer = setInterval(scan, LIVE_MS);
    } else if (state.liveTimer) {
      clearInterval(state.liveTimer);
      state.liveTimer = null;
    }
  });
}

// ── Init ─────────────────────────────────────────────────────────────────
window.addEventListener("DOMContentLoaded", () => {
  setupButtons();
  setupLive();
  setTrackMode("auto");
  $("btnScan").addEventListener("click", scan);
  document.querySelectorAll(".request-bar input").forEach((el) =>
    el.addEventListener("keydown", (e) => { if (e.key === "Enter") scan(); }));
  refreshHealth();
  scan();
});
