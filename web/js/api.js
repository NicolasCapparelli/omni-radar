// Thin wrappers around the middleware HTTP endpoints (proxied by serve.py).

const enc = encodeURIComponent;

// GET /api/nearby — returns { aircraft, recommendedPoll, query }.
export async function getNearby({ lat, lon, radius }) {
  const query = `lat=${enc(lat)}&lon=${enc(lon)}&radius=${enc(radius)}`;
  const resp = await fetch(`/api/nearby?${query}`);
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`HTTP ${resp.status}: ${body.slice(0, 200)}`);
  }
  const data = await resp.json();
  const rec = parseInt(resp.headers.get("X-Recommended-Poll-Seconds"), 10);
  return {
    aircraft: Array.isArray(data) ? data : [],
    recommendedPoll: Number.isFinite(rec) ? rec : null,
    query,
  };
}

export const getHealth = () => fetch("/health").then((r) => r.json());

// GET /api/marine/{channel}/nearby — returns { vessels, recommendedPoll, query }.
// Each channel owns its own aisstream WebSocket on the backend (lazily opened).
export async function getMarineNearby({ channel, lat, lon, radius }) {
  const query = `lat=${enc(lat)}&lon=${enc(lon)}&radius=${enc(radius)}`;
  const path = `/api/marine/${enc(channel)}/nearby`;
  const resp = await fetch(`${path}?${query}`);
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`HTTP ${resp.status}: ${body.slice(0, 200)}`);
  }
  const data = await resp.json();
  const rec = parseInt(resp.headers.get("X-Recommended-Poll-Seconds"), 10);
  return {
    vessels: Array.isArray(data) ? data : [],
    recommendedPoll: Number.isFinite(rec) ? rec : null,
    query: `${path}?${query}`,
  };
}

export const getMetrics = () => fetch("/api/metrics").then((r) => r.json());
export const resetMetrics = () => fetch("/api/metrics/reset");
