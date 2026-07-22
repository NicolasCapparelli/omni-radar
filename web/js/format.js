// Pure formatting / presentation helpers shared across views. No DOM, no state.

// Radius of the radar scope in px (scope is 168px diameter).
export const RADAR_R = 84;

// Vehicle-type -> Material Symbol name (close-enough icons for a dev tool).
export const TYPE_ICON = {
  Plane: "flight", Seaplane: "flight", Amphibian: "flight",
  Helicopter: "mode_fan", Gyrocopter: "mode_fan", Tiltrotor: "mode_fan",
  Glider: "paragliding", Ultralight: "paragliding", Skydiver: "paragliding",
  "Lighter-than-air": "cloud", Drone: "mode_fan", Spacecraft: "rocket_launch",
  "Surface Vehicle": "directions_car", Obstacle: "warning",
  // Marine (AIS) vessel categories.
  Cargo: "directions_boat", Tanker: "directions_boat", Passenger: "directions_boat",
  "High-Speed Craft": "directions_boat", Tug: "directions_boat", Towing: "directions_boat",
  Dredger: "directions_boat", "Diving Ops": "scuba_diving", Fishing: "phishing",
  Sailing: "sailing", "Pleasure Craft": "sailing", "Pilot Vessel": "anchor",
  "Search and Rescue": "emergency", "Law Enforcement": "local_police",
  "Medical Transport": "local_hospital", "Port Tender": "anchor",
  "Anti-Pollution": "directions_boat", Military: "directions_boat",
  Noncombatant: "directions_boat", "Wing-in-Ground": "flight", Other: "directions_boat",
};

export const iconFor = (t) => TYPE_ICON[t] || "flight";

// Marine default is a boat, not a plane — vessels with no static data yet
// (ship type still Unknown) should still read as boats.
export const iconForVessel = (t) => TYPE_ICON[t] || "directions_boat";

export const classChip = (c) =>
  "chip-" + String(c || "unknown").toLowerCase().replace(/[^a-z]/g, "");

export const commas = (n) => (n ?? 0).toLocaleString("en-US");

export function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Vertical-speed -> {cls, text} for climb/descent/level styling.
export function vspdParts(fpm) {
  if (!fpm) return { cls: "level", text: "— level" };
  if (fpm > 0) return { cls: "climb", text: `▲ ${commas(fpm)} fpm` };
  return { cls: "descent", text: `▼ ${commas(Math.abs(fpm))} fpm` };
}

export const routeStr = (a) => `${a.origin || "N/A"} → ${a.destination || "N/A"}`;

export function fmtUptime(s) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return h ? `${h}h ${m}m` : m ? `${m}m ${sec}s` : `${sec}s`;
}

// Relative bearing (radians clockwise from north) + distance (miles) from the
// user's position to an aircraft, using a mid-latitude flat-earth approximation.
export function relativePosition(user, a) {
  const milesPerLat = 69.0;
  const milesPerLon = 69.0 * Math.cos((user.lat * Math.PI) / 180);
  const dNorth = (a.latitude - user.lat) * milesPerLat;
  const dEast = (a.longitude - user.lon) * milesPerLon;
  return { dist: Math.hypot(dNorth, dEast), bearing: Math.atan2(dEast, dNorth) };
}
