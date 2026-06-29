// The Usage view: external API call counters vs. work served locally. Self
// contained — owns the Console/Usage tab switch and its own refresh timer.

import { $ } from "./dom.js";
import { commas, fmtUptime } from "./format.js";
import { getMetrics, resetMetrics } from "./api.js";

let timer = null;

export function initUsage() {
  $("navConsole").addEventListener("click", () => showView("console"));
  $("navUsage").addEventListener("click", () => showView("usage"));
  $("btnUsageRefresh").addEventListener("click", fetchMetrics);
  $("usageLive").addEventListener("change", (e) =>
    e.target.checked ? startTimer() : stopTimer());
  $("btnUsageReset").addEventListener("click", async () => {
    await resetMetrics();
    fetchMetrics();
  });
}

function showView(which) {
  const isUsage = which === "usage";
  $("consoleView").hidden = isUsage;
  $("usageView").hidden = !isUsage;
  $("navConsole").classList.toggle("active", !isUsage);
  $("navUsage").classList.toggle("active", isUsage);
  if (isUsage) {
    fetchMetrics();
    if ($("usageLive").checked) startTimer();
  } else {
    stopTimer();
  }
}

function startTimer() { stopTimer(); timer = setInterval(fetchMetrics, 5000); }
function stopTimer() { if (timer) { clearInterval(timer); timer = null; } }

async function fetchMetrics() {
  try {
    renderMetrics(await getMetrics());
  } catch (err) {
    console.error("metrics fetch failed", err);
  }
}

function renderMetrics(m) {
  const ext = m.external_calls, sv = m.savings;

  $("usageUptime").textContent =
    `Uptime ${fmtUptime(m.uptime_seconds)} · ${commas(m.requests.nearby)} scans · ` +
    `${commas(m.requests.aircraft_returned)} aircraft served`;

  $("hExternal").textContent = commas(ext.total);
  $("hAvoided").textContent = commas(sv.calls_avoided_total);
  $("hAvoidedDetail").textContent = `${commas(sv.cache_hits)} cache · ${commas(sv.planes_filtered)} filtered`;
  $("hRatio").textContent = `${Math.round(sv.local_served_ratio * 100)}%`;
  $("hFa").textContent = commas(ext.flightaware.requests);

  $("providerRows").innerHTML =
    providerRow("OpenSky", ext.opensky, false) +
    providerRow("adsbdb", ext.adsbdb, true) +
    providerRow("FlightAware", ext.flightaware, true);
  $("openskyNote").textContent =
    `OpenSky is 1 call per scan (the bulk live feed); adsbdb & FlightAware are ` +
    `per-callsign route lookups. Cache entries: ${commas(m.cache_entries ?? 0)}.`;

  const os = ext.opensky;
  $("openskyCredits").textContent = os.credits_remaining == null
    ? `OpenSky daily credits: not yet observed — run a scan. (429s so far: ${commas(os.rate_limited)})`
    : `OpenSky daily credits remaining: ${commas(os.credits_remaining)} · rate-limited (429): ${commas(os.rate_limited)}`;
  $("recPoll").textContent =
    `Recommended poll interval: ${m.recommended_poll_seconds}s — data refreshes ` +
    `every ~5s; backs off automatically as credits run low.`;

  $("savingsList").innerHTML =
    savingItem("bolt", "Route cache hits (no call)", sv.cache_hits) +
    savingItem("filter_alt", "Grounded planes filtered", sv.planes_filtered) +
    savingItem("dns", "Offline aircraft-DB enrichments", sv.offline_db_enrichments) +
    savingItem("block", "Known no-route (negatively cached)", m.route_resolution.not_found);

  // Made-vs-avoided bars.
  const providerRouteCalls = ext.adsbdb.requests + ext.flightaware.requests;
  const max = Math.max(sv.cache_hits, sv.planes_filtered, providerRouteCalls, 1);
  $("barCache").style.width = `${(sv.cache_hits / max) * 100}%`;
  $("barFiltered").style.width = `${(sv.planes_filtered / max) * 100}%`;
  $("barCalls").style.width = `${(providerRouteCalls / max) * 100}%`;
  $("numCache").textContent = commas(sv.cache_hits);
  $("numFiltered").textContent = commas(sv.planes_filtered);
  $("numCalls").textContent = commas(providerRouteCalls);
}

function providerRow(name, p, detailed) {
  const cell = (v) => `<td class="num">${detailed ? commas(v) : "—"}</td>`;
  return `
    <tr><td class="prov">${name}</td>
      <td class="num">${commas(p.requests)}</td>
      ${cell(p.found)}${cell(p.not_found)}${cell(p.rate_limited)}
      <td class="num">${commas(p.errors)}</td></tr>`;
}

const savingItem = (icon, label, val) =>
  `<li><span><span class="material-symbols-outlined">${icon}</span>${label}</span><b>${commas(val)}</b></li>`;
