// Top-bar connection indicator + the console status strip (cache / providers).

import { $ } from "./dom.js";
import { commas } from "./format.js";
import { getHealth } from "./api.js";

const DOT = { ok: "dot-ok", busy: "dot-busy", err: "dot-err" };

export function setConn(kind, text) {
  $("connDot").className = "dot " + (DOT[kind] || "dot-idle");
  $("connText").textContent = text;
}

// Pull /health for cache size and provider availability dots.
export async function refreshHealth() {
  try {
    const h = await getHealth();
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
