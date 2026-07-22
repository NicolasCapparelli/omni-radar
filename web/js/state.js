// Shared, mutable application state for the console. A single source of truth
// that the view modules read and the controller mutates.

export const DEFAULTS = { lat: 40.7580, lon: -73.9965, radius: 15, channel: "web" };

export const SCROLL_MS = 5000; // auto-cycle cadence (mirrors the hardware)

export const state = {
  aircraft: [],          // last fetched aircraft array
  selected: -1,          // index into `aircraft`, or -1
  mode: "AIR",           // AIR | MARINE
  trackMode: "auto",     // auto (cycle) | manual (lock)
  view: "data",          // data | radar  (device body view)
  powered: true,         // device screen on/off
  user: { ...DEFAULTS }, // last-scanned home position (for the radar)
  recommendedPoll: 30,   // server-advertised poll interval (seconds)
  scrollTimer: null,     // auto-cycle interval handle
  liveTimeout: null,     // live-refresh timeout handle
  warmupTimeout: null,   // one-shot marine warm-up retry handle
};
