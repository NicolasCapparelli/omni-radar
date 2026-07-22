// Entry point. Loads the HTML partials, then wires the modules together.
//
// `select` (the single source of "what is shown") lives here and is injected
// into the device and console modules, so neither view module needs to know
// about the others — the dependency graph stays acyclic.

import { state } from "./state.js";
import { $ } from "./dom.js";
import { initDevice, renderDevice, setTrackMode } from "./device.js";
import { highlightRow } from "./table.js";
import { initConsole, scan, applyMode } from "./console.js";
import { initUsage } from "./usage.js";
import { refreshHealth } from "./status.js";

// Set the active selection and refresh everything that depends on it.
function select(i) {
  state.selected = i;
  highlightRow();
  renderDevice();
  $("rawJson").textContent =
    i >= 0 ? JSON.stringify(state.aircraft[i], null, 2) : "// select a target";
}

// A click in the results table locks tracking, then selects.
function onRowSelect(i) {
  if (state.trackMode === "auto") setTrackMode("manual");
  select(i);
}

// Inject each mount point's partial HTML (data-partial="name" -> partials/name.html).
async function loadPartials() {
  const mounts = [...document.querySelectorAll("[data-partial]")];
  await Promise.all(mounts.map(async (mount) => {
    const name = mount.dataset.partial;
    const resp = await fetch(`partials/${name}.html`);
    if (!resp.ok) throw new Error(`partial '${name}' failed: HTTP ${resp.status}`);
    mount.innerHTML = await resp.text();
  }));
}

async function init() {
  try {
    await loadPartials();
  } catch (err) {
    document.body.insertAdjacentHTML("afterbegin",
      `<p style="color:#b3261e;padding:16px">Failed to load UI: ${err.message}</p>`);
    return;
  }
  initDevice(select, applyMode);
  initConsole({ select, onRowSelect });
  initUsage();
  setTrackMode("auto");
  refreshHealth();
  scan();
}

window.addEventListener("DOMContentLoaded", init);
