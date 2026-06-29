# External Dependencies

This document tracks every external service and data source the Omni-Radar
middleware relies on — their authentication, limits/costs, the role they play,
and how we mitigate cost and rate limits. Keep it current when dependencies
change.

Live usage against these is visible on the **Usage** screen of the web console
(`GET /api/metrics`).

## Summary

| Dependency | Type | Auth | Cost / limits | Role | Required? |
| --- | --- | --- | --- | --- | --- |
| OpenSky Network | REST API | OAuth2 | Credit-based (see below) | Live positions | **Yes** |
| adsbdb.com | REST API | None | Free (community) | Flight routes (primary) | No¹ |
| FlightAware AeroAPI | REST API | API key | Paid / quota | Flight routes (fallback) | No |
| OpenSky aircraft DB | CSV download | None | Free | Offline model/reg/owner/type | No² |

¹ Routes degrade gracefully to "Unknown" if no route provider is available.
² Without it, `model_code`/`registration`/`owner` and DB-based helicopter
detection are unavailable; the rest still works.

---

## 1. OpenSky Network — live state vectors (REQUIRED)

The only hard dependency. Supplies every aircraft's position, altitude, speed,
heading, vertical rate, squawk, and category via one bulk call per poll.

- **Endpoint:** `GET https://opensky-network.org/api/states/all` (bounding box).
- **Auth:** OAuth2 client-credentials. Token endpoint:
  `https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token`.
  Tokens expire after 30 min (we auto-refresh with a 30s margin).
- **Data freshness:** authenticated = **5s** resolution (anonymous 10s). Polling
  faster than 5s returns identical data — 5s is the hard floor.

### Credits

Credits are tracked in independent per-endpoint buckets (`/states/*` is its own
bucket, separate from `/flights/*` and `/tracks/*`).

| Tier | Quota |
| --- | --- |
| Anonymous | 400 / day |
| Standard authenticated (our tier) | 4,000 / day |
| Active feeder (≥30% uptime/month) | 8,000 / day |
| Licensed | 14,400 / hour |

`/states/all` cost scales with the bounding-box **area** (lat° × lon°):

| Box area | Credits / call |
| --- | --- |
| ≤ 25 sq° (or serial-only) | 1 |
| 25–100 sq° | 2 |
| 100–400 sq° | 3 |
| > 400 sq° / global | 4 |

Our default 15-mile radius → box ≈ 0.43° × 0.57° ≈ **0.25 sq° → 1 credit/poll**.
We only cross into 2 credits past ~150-mile radius.

### Polling guidance (standard 4,000/day, 1 credit/call)

- **5s** — hard floor (data resolution); burns 17,280/day → exhausts in ~5.5h.
- **~22s** — sustainable 24/7 (86,400 ÷ 4,000).
- **30s** — our default; ~2,880/day, comfortable headroom.
- Short demos at 5–10s are fine (a 1-hour run at 5s ≈ 720 credits).

### Rate-limit signaling & our mitigation

- Responses carry `X-Rate-Limit-Remaining`; on exhaustion the API returns `429`
  with `X-Rate-Limit-Retry-After-Seconds`.
- The middleware reads these headers (`app/opensky.py`), records them in metrics,
  and computes a **recommended poll interval** that backs off as credits run low
  (returned in `GET /api/metrics` and the `X-Recommended-Poll-Seconds` response
  header on `/api/nearby`). The web console honors it automatically.
- One call per poll regardless of aircraft count (it's a bulk feed).

---

## 2. adsbdb.com — flight routes (PRIMARY route source, free)

Free, keyless community API mapping a callsign to its origin/destination.

- **Endpoint:** `GET https://api.adsbdb.com/v0/callsign/{callsign}`.
- **Auth:** none. **404** = unknown callsign (no route).
- **Limits:** no published hard quota, but it's a donation-funded community
  service — be courteous. We throttle (`ADSBDB_MAX_CONCURRENCY`,
  `ADSBDB_MIN_INTERVAL_MS`) and never retry in-line; a `429`/5xx defers to the
  next poll.
- **Mitigation:** results are cached (12h) and persisted to disk; "no route"
  is negatively cached (3h) so we don't re-query GA/private callsigns.
- **Attribution / licensing:** route data is the work of David Taylor (Edinburgh)
  and Jim Mason (Glasgow); per adsbdb's terms it **may not be copied, published,
  or incorporated into other databases** without explicit permission. We query
  it live for display only — we must not redistribute or rebuild a route DB from
  it. Aircraft data is sourced from PlaneBase.

---

## 3. FlightAware AeroAPI — flight routes (OPTIONAL fallback)

Commercial route source, used **only** for routes adsbdb doesn't have. Leave the
key blank to disable entirely (fully free operation).

- **Endpoint:** `GET https://aeroapi.flightaware.com/aeroapi/flights/{ident}`.
- **Auth:** `x-apikey` header.
- **Cost / limits:** paid per result set; the Personal tier has a monthly
  query-unit quota and a per-minute rate limit enforced upstream (returns `429`
  on burst). Pricing is per "result set" (≈15 records).
- **Mitigation:** fallback only (fires on an adsbdb miss); throttled
  (`FLIGHTAWARE_MAX_CONCURRENCY`, `FLIGHTAWARE_MIN_INTERVAL_MS`); no in-line
  retries; same cache as adsbdb. In practice most route hits come from adsbdb,
  so AeroAPI usage stays minimal.
- **Account:** https://www.flightaware.com/aeroapi/

---

## 4. OpenSky aircraft database (offline CSV)

Static airframe registry used for free, offline enrichment: `model_code`,
`model_name`, `registration`, `operator`, `owner`, and Doc 8643 airframe class
(helicopter/glider/etc.).

- **Source:** `https://opensky-network.org/datasets/metadata/aircraftDatabase.csv`
- **Size:** ~100+ MB, ~480k airframes (loaded into memory at startup).
- **Auth:** none.
- **Refresh:** auto-downloaded on startup if missing or older than
  `AIRCRAFT_DB_MAX_AGE_DAYS` (default 30); see `scripts/download_aircraft_db.py`.
- **Mitigation:** entirely offline → zero per-request cost; replaces what would
  otherwise be paid aircraft-type lookups.

---

## Python packages

Pinned in `requirements.txt`: `fastapi`, `uvicorn[standard]`, `httpx`,
`pydantic`, `pydantic-settings`. The web console server (`web/serve.py`) and the
DB downloader use only the Python standard library.

---

## How we monitor it

`GET /api/metrics` (and the web **Usage** tab) report, per session: external
calls per provider, OpenSky credits remaining and 429 count, the recommended
poll interval, and how much was served locally (cache hits, grounded-plane
filtering, offline DB enrichment). `GET /api/metrics/reset` zeroes counters for
a clean measurement run.
