// The aircraft results table (right-hand console). Renders rows from state and
// reports row clicks via an injected callback — it owns no selection logic.

import { state } from "./state.js";
import { $ } from "./dom.js";
import { iconFor, classChip, commas, escapeHtml, vspdParts, routeStr } from "./format.js";

const COLSPAN = 11;

export function renderTable(onRowSelect) {
  const body = $("aircraftBody");
  if (!state.aircraft.length) {
    body.innerHTML = `<tr class="empty-row"><td colspan="${COLSPAN}">No targets in range.</td></tr>`;
    return;
  }
  body.innerHTML = state.aircraft.map((a, i) => rowHtml(a, i)).join("");
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
