// The hardware device emulator: the 320x240 LCD (data card + radar view), the
// footer track-mode badge, auto-cycling, and the four physical buttons.
//
// Selection is owned by the controller; `initDevice(select)` injects it so the
// auto-cycle timer and the ACTION step button can advance the selection without
// this module importing the controller (keeps the dependency graph acyclic).

import { state, SCROLL_MS } from "./state.js";
import { $ } from "./dom.js";
import { iconFor, iconForVessel, classChip, commas, escapeHtml, vspdParts, relativePosition, RADAR_R } from "./format.js";

let select = () => {};
let onModeToggle = () => {};

export function initDevice(selectFn, onModeToggleFn) {
  select = selectFn;
  if (onModeToggleFn) onModeToggle = onModeToggleFn;
  wireButtons();
}

// Render the whole device for the current selection.
export function renderDevice() {
  renderCard();
  renderRadar();
  updateView();
}

// ── Body view visibility (empty / radar / data card) ───────────────────────
function updateView() {
  const a = state.aircraft[state.selected];
  const empty = $("lcdEmpty"), card = $("lcdCard"), radar = $("lcdRadar");
  if (!a) {
    empty.hidden = false; card.hidden = true; radar.hidden = true;
    $("lcdIndex").textContent = "0 / 0 TRACKED";
    return;
  }
  empty.hidden = true;
  const radarActive = state.view === "radar";
  radar.hidden = !radarActive;
  card.hidden = radarActive;
}

// ── Data card ───────────────────────────────────────────────────────────────
function renderCard() {
  const a = state.aircraft[state.selected];
  if (!a) return;
  if (state.mode === "MARINE") renderVesselCard(a);
  else renderAircraftCard(a);
}

function renderAircraftCard(a) {
  $("lcdCallsign").textContent = a.callsign || "--------";
  $("lcdOrigin").textContent = a.origin || "N/A";
  $("lcdDest").textContent = a.destination || "N/A";
  setFlag("lcdOriginFlag", a.origin_country);
  setFlag("lcdDestFlag", a.destination_country);
  $("lcdOriginName").textContent = a.origin_name || "";
  $("lcdDestName").textContent = a.destination_name || "";
  $("lcdAirline").textContent = a.operator && a.operator !== "Unknown" ? a.operator : a.airline;
  $("lcdTypeIcon").textContent = iconFor(a.vehicle_type);
  $("lcdModel").textContent = `${a.model_code} · ${a.model_name}`;
  setLabel("lcdAlt", "ALT");
  $("lcdAlt").textContent = `${commas(a.altitude_feet)} ft`;
  setLabel("lcdHdg", "HDG");
  $("lcdSpd").textContent = `${commas(a.speed_knots)} kt`;
  $("lcdHdg").textContent = `${a.heading_degrees}°`;
  $("lcdHdgArrow").style.transform = `rotate(${a.heading_degrees || 0}deg)`;

  const vs = vspdParts(a.vertical_speed_fpm);
  $("lcdVspd").textContent = vs.text;
  $("lcdVspd").className = "lcd-vspd " + vs.cls;

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

// Marine card: reuses the same LCD elements with vessel-appropriate content.
function renderVesselCard(v) {
  const named = v.name && v.name !== "Unknown";
  $("lcdCallsign").textContent = named ? v.name : `MMSI ${v.mmsi}`;
  // Route line: flag state on the left, free-text destination on the right.
  $("lcdOrigin").textContent = v.country || "—";
  setFlag("lcdOriginFlag", v.country_iso);
  $("lcdDest").textContent = v.destination || "N/A";
  setFlag("lcdDestFlag", null);
  $("lcdOriginName").textContent = `MMSI ${v.mmsi}`;
  $("lcdDestName").textContent = v.eta ? `ETA ${v.eta}` : "";
  $("lcdAirline").textContent = v.callsign
    ? `Callsign ${v.callsign}`
    : (named ? "" : "Awaiting vessel details…");
  $("lcdTypeIcon").textContent = iconForVessel(v.vessel_type);
  const dims = v.length_meters ? ` · ${v.length_meters}×${v.beam_meters} m` : "";
  $("lcdModel").textContent = `${v.vessel_type}${dims}`;
  setLabel("lcdAlt", "DRAFT");
  $("lcdAlt").textContent = v.draught_meters ? `${v.draught_meters} m` : "— m";
  setLabel("lcdHdg", "COG");
  $("lcdSpd").textContent = `${commas(v.speed_knots)} kt`;
  $("lcdHdg").textContent = `${v.course_degrees}°`;
  $("lcdHdgArrow").style.transform = `rotate(${v.course_degrees || 0}deg)`;

  $("lcdVspd").textContent = v.nav_status || "";
  $("lcdVspd").className = "lcd-vspd level";

  const badges = [];
  if (v.operator_class && v.operator_class !== "Unknown")
    badges.push(`<span class="chip ${classChip(v.operator_class)}">${escapeHtml(v.operator_class)}</span>`);
  if (v.special_designation && v.special_designation !== "None")
    badges.push(`<span class="chip chip-military">${escapeHtml(v.special_designation)}</span>`);
  $("lcdBadges").innerHTML = badges.join("");

  $("lcdEmergency").hidden = true;
  $("lcd").classList.remove("alert");
  $("lcdIndex").textContent = `${state.selected + 1} / ${state.aircraft.length} TRACKED`;
}

// Set the <label> next to a telemetry value element.
function setLabel(valueId, text) {
  const label = $(valueId).previousElementSibling;
  if (label && label.tagName === "LABEL") label.textContent = text;
}

// Point a flag <img> at flagcdn for an ISO alpha-2 country code, or hide it.
function setFlag(id, iso) {
  const el = $(id);
  if (iso && /^[A-Za-z]{2}$/.test(iso)) {
    el.src = `https://flagcdn.com/32x24/${iso.toLowerCase()}.png`;
    el.hidden = false;
  } else {
    el.hidden = true;
    el.removeAttribute("src");
  }
}

// ── Radar view (fixed compass, North up) ────────────────────────────────────
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
  const vtype = state.mode === "MARINE" ? a.vessel_type : a.vehicle_type;
  $("radarPlaneIcon").textContent =
    state.mode === "MARINE" ? iconForVessel(vtype) : iconFor(vtype);
  $("radarPlaneIcon").style.transform = `rotate(${a.heading_degrees || 0}deg)`;

  infoEl.hidden = false;
  const label = state.mode === "MARINE"
    ? `<b>${escapeHtml(a.name && a.name !== "Unknown" ? a.name : a.mmsi)}</b><br>${commas(a.speed_knots)} kt<br>${dist.toFixed(1)} mi`
    : `<b>${escapeHtml(a.callsign)}</b><br>${commas(a.altitude_feet)} ft<br>${dist.toFixed(1)} mi`;
  infoEl.innerHTML = label;
  const onLeft = x > RADAR_R;
  infoEl.style.left = `${onLeft ? x - 12 : x + 12}px`;
  infoEl.style.top = `${Math.min(Math.max(y - 4, -10), 140)}px`;
  infoEl.style.transform = onLeft ? "translateX(-100%)" : "none";
  infoEl.style.textAlign = onLeft ? "right" : "left";
}

// ── Track mode + auto-cycle ─────────────────────────────────────────────────
const HINT_AUTO = "Auto-Scroll: cycling every 5s. Press ACTION to lock.";
const HINT_MANUAL = "Manual-Lock: press ACTION to step to the next target.";

export function setTrackMode(mode) {
  state.trackMode = mode;
  const badge = $("lcdTrackMode");
  if (mode === "auto") {
    badge.textContent = "AUTO-CYCLING";
    badge.classList.remove("lock");
    $("actionHint").textContent = HINT_AUTO;
    startScroll();
  } else {
    badge.textContent = "MANUAL LOCK";
    badge.classList.add("lock");
    $("actionHint").textContent = HINT_MANUAL;
    stopScroll();
  }
}

export function startScroll() {
  stopScroll();
  if (!state.powered || state.trackMode !== "auto" || !state.aircraft.length) return;
  state.scrollTimer = setInterval(() => {
    select((state.selected + 1) % state.aircraft.length);
  }, SCROLL_MS);
}

export function stopScroll() {
  if (state.scrollTimer) { clearInterval(state.scrollTimer); state.scrollTimer = null; }
}

// ── Physical buttons ────────────────────────────────────────────────────────
function wireButtons() {
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
    // Leaving radar selected is fine — it works in both modes now.
    updateView();
    onModeToggle();  // re-scan against the newly-active source
  });

  $("btnAlt").addEventListener("click", () => {
    if (!state.powered) return;
    state.view = state.view === "radar" ? "data" : "radar";
    $("btnAlt").classList.toggle("active", state.view === "radar");
    $("actionHint").textContent = state.view === "radar"
      ? "Radar: target position relative to you (North up)."
      : (state.trackMode === "auto" ? HINT_AUTO : HINT_MANUAL);
    renderRadar();
    updateView();
  });

  $("btnAction").addEventListener("click", () => {
    if (!state.powered) return;
    if (state.trackMode === "auto") {
      setTrackMode("manual");
    } else if (state.aircraft.length) {
      select((state.selected + 1) % state.aircraft.length); // step while locked
    }
  });
}
