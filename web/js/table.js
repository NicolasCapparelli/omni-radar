// The results table (right-hand console). Renders rows from state and reports
// row clicks via an injected callback — it owns no selection logic. Mode-aware:
// aircraft columns in AIR, vessel columns in MARINE (hard external cutoff).

import { state } from "./state.js";
import { $ } from "./dom.js";
import { iconFor, iconForVessel, classChip, commas, escapeHtml, vspdParts, routeStr } from "./format.js";

const AIR_HEAD = `
  <th></th><th>Callsign</th><th>Type</th><th>Model</th>
  <th>Operator</th><th>Route</th>
  <th class="num">Alt</th><th class="num">Spd</th><th class="num">V/S</th>
  <th>Class</th><th>Flag</th>`;

const MARINE_HEAD = `
  <th></th><th>Vessel</th><th>Type</th><th>MMSI</th>
  <th>Destination</th><th>Status</th>
  <th class="num">Spd</th><th class="num">Crs</th><th>Flag</th>
  <th>Class</th><th>Special</th>`;

export const COLSPAN = 11;

export function renderTable(onRowSelect) {
  const head = $("tableHead");
  if (head) head.innerHTML = state.mode === "MARINE" ? MARINE_HEAD : AIR_HEAD;

  const body = $("aircraftBody");
  if (!state.aircraft.length) {
    body.innerHTML = `<tr class="empty-row"><td colspan="${COLSPAN}">No targets in range.</td></tr>`;
    return;
  }
  const row = state.mode === "MARINE" ? vesselRowHtml : rowHtml;
  body.innerHTML = state.aircraft.map((a, i) => row(a, i)).join("");
  body.querySelectorAll("tr[data-i]").forEach((tr) =>
    tr.addEventListener("click", () => onRowSelect(Number(tr.dataset.i))));
  highlightRow();
}

export function highlightRow() {
  document.querySelectorAll(".aircraft-table tr[data-i]").forEach((tr) =>
    tr.classList.toggle("selected", Number(tr.dataset.i) === state.selected));
}

function rowHtml(a, i) {
  const vs = vspdParts(a.vertical_speed_fpm);
  const emergency = a.emergency && a.emergency !== "None";
  const special = a.special_designation && a.special_designation !== "None";
  const rowCls = [emergency ? "emergency" : "", a.on_ground ? "grounded" : ""].join(" ").trim();
  const vsCls = vs.cls === "climb" ? "vs-climb" : vs.cls === "descent" ? "vs-descent" : "vs-level";
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
      <td class="num ${vsCls}">${vs.text.split(" ")[0]}</td>
      <td><span class="chip ${classChip(a.operator_class)}">${escapeHtml(a.operator_class)}</span></td>
      <td>${flag}</td>
    </tr>`;
}

function vesselRowHtml(v, i) {
  const special = v.special_designation && v.special_designation !== "None";
  const flag = v.country_iso && /^[A-Za-z]{2}$/.test(v.country_iso)
    ? `<img class="flag-img" src="https://flagcdn.com/20x15/${v.country_iso.toLowerCase()}.png" alt="${escapeHtml(v.country)}" title="${escapeHtml(v.country)}" />`
    : "";
  const specialChip = special
    ? `<span class="flag flag-special">${escapeHtml(v.special_designation)}</span>`
    : "";
  const name = v.name && v.name !== "Unknown" ? v.name : `(${v.mmsi})`;
  return `
    <tr data-i="${i}">
      <td class="ti"><span class="material-symbols-outlined">${iconForVessel(v.vessel_type)}</span></td>
      <td class="cs">${escapeHtml(name)}</td>
      <td>${escapeHtml(v.vessel_type)}</td>
      <td>${escapeHtml(v.mmsi)}</td>
      <td>${escapeHtml(v.destination)}</td>
      <td>${escapeHtml(v.nav_status)}</td>
      <td class="num">${commas(v.speed_knots)}</td>
      <td class="num">${v.course_degrees}°</td>
      <td>${flag}</td>
      <td><span class="chip ${classChip(v.operator_class)}">${escapeHtml(v.operator_class)}</span></td>
      <td>${specialChip}</td>
    </tr>`;
}
