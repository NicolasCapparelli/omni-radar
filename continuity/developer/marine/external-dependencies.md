# Marine External Dependencies

> *Migrated into Continuity on 2026-10-02 from `DevGuide/MARINE/external-dependencies.md`; original text unchanged apart from link repair and this note. The `MARINE_FALLBACK_*` keys and the paid fallback are a proposal and are not implemented; the aisstream terms-of-use TODO remains open. Differences from current code: [status → Documentation drift](../../status.md#documentation-drift).*

The marine counterpart to the AIR
[external-dependencies.md](../external-dependencies.md). Tracks every external
service / data source the marine side relies on — auth, limits/costs, role, and
how we mitigate them. Keep it current when dependencies change.

## Summary

| Dependency | Type | Auth | Cost / limits | Role | Required? |
| --- | --- | --- | --- | --- | --- |
| aisstream.io | WebSocket | Free API key | Free (community) | Live vessel positions + static data | **Yes** |
| MarineTraffic (or similar) | REST API | API key | Paid / quota | Gap-fill fallback | No |
| AIS ship-type table | Offline table | None | Free | Type code → category | No¹ |
| MMSI MID table | Offline table | None | Free | MMSI prefix → country/flag | No¹ |

¹ Built into the codebase (`marine_static_data.py`), not downloaded. Without
them, vessels still render with raw codes instead of friendly labels.

> **AIR vs MARINE primary source:** AIR's required source (OpenSky) is a REST
> poll metered in credits. MARINE's required source (aisstream.io) is a
> persistent WebSocket whose cost is measured in **open connections + uptime**,
> not per-call credits. This is the central difference between the two halves.

---

## 1. aisstream.io — live AIS stream (REQUIRED)

The marine hard dependency, analogous to OpenSky for AIR. A free, community
WebSocket that streams AIS messages for one or more subscribed bounding boxes.

- **Endpoint:** `wss://stream.aisstream.io/v0/stream`.
- **Auth:** a free **API key**, sent inside the first WebSocket message (the
  subscription), not as an HTTP header. Register at https://aisstream.io/.
- **Subscription:** after connecting, send a JSON subscription message:
  ```json
  {
    "APIKey": "<key>",
    "BoundingBoxes": [[[lat_sw, lon_sw], [lat_ne, lon_ne]]],
    "FilterMessageTypes": ["PositionReport", "StandardClassBPositionReport", "ShipStaticData"]
  }
  ```
  Note the coordinate order is **[lat, lon]**, SW corner then NE corner — a thin
  adapter over our existing `geo.BoundingBox` (which is lamin/lamax/lomin/lomax).
- **Message shape:** every message has `MetaData`, `MessageType`, and `Message`.
  We care about:
  - `PositionReport` / `StandardClassBPositionReport` → `UserID` (MMSI),
    `Latitude`, `Longitude`, `Sog` (knots), `Cog`, `TrueHeading`,
    `NavigationalStatus`.
  - `ShipStaticData` → `Name`, `CallSign`, `ImoNumber`, `Type`, `Dimension`
    (A/B/C/D), `MaximumStaticDraught`, `Destination`, `Eta`.
  - (Schema reference: the aisstream message models, captured during design.)
- **Data freshness:** position reports ~2–10 s (Class A) / ~30 s (Class B);
  static data ~6 min. Coverage is community terrestrial + satellite, so it
  varies by region and is best near coasts / busy lanes.
- **Limits:** free community service — be courteous. Mitigations:
  - One socket **per active channel**, not per request.
  - Each channel auto-closes after **8 idle hours**
    (`MARINE_CHANNEL_IDLE_TTL_MS`), so we don't hold sockets for areas nobody is
    watching.
  - Subscriptions are filtered to the message types we use, and bounded to the
    channel's box.
- **Licensing / attribution:** **TODO — verify aisstream.io's terms of use
  before shipping.** AIS redistribution terms commonly restrict rebuilding a
  database from the feed or require attribution (adsbdb has a comparable
  clause). We intend to query live for display only, never to persist or
  redistribute a vessel database. Confirm and record the exact terms here.

### Why a store instead of a poll

Because the source pushes rather than answers queries, each channel keeps a
small in-memory `VesselStore` (latest state per MMSI, TTL-evicted). Client
requests read that store — so the per-request external cost is **zero**. See
[architecture.md](architecture.md).

---

## 2. MarineTraffic / similar — paid gap-fill (OPTIONAL fallback, secondary)

The marine analog of FlightAware AeroAPI: a commercial REST API used **only** to
fill gaps the free stream hasn't covered yet (e.g. a vessel we have a position
for but no static data). Scaffolded for parity but **not a focus** — leave the
key blank for fully-free operation.

- **Endpoint:** provider-specific (e.g. MarineTraffic vessel/position services).
- **Auth:** API key.
- **Cost / limits:** paid per credit / result set; per-minute rate limits
  upstream. Exact model depends on the chosen provider.
- **Mitigation:** fallback only; disabled unless a key is configured; throttled
  (`MARINE_FALLBACK_MAX_CONCURRENCY`, `MARINE_FALLBACK_MIN_INTERVAL_MS`); no
  in-line retries; results cached. In practice the stream covers almost
  everything, so fallback usage should stay near zero.
- **Provider choice is deferred** — MarineTraffic, VesselFinder, and FleetMon
  all offer comparable bounding-box / vessel-detail REST APIs. Pick at
  implementation time; keep the interface generic (a `MarineProvider` protocol,
  mirroring AIR's `RouteProvider`).

---

## 3. Offline AIS reference tables

Static, in-code tables for free offline enrichment (the marine analog of AIR's
`static_data.py`). No download, no network.

- **Ship-type table:** AIS `Type` code (0–99) → category label and operator
  class. Standard ranges: 30 Fishing, 36 Sailing, 37 Pleasure, 40–49 High-Speed
  Craft, 50 Pilot, 51 Search & Rescue, 52 Tug, 55 Law Enforcement, 58 Medical,
  60–69 Passenger, 70–79 Cargo, 80–89 Tanker, 35/59 Military/Noncombatant.
- **MMSI MID table:** first 3 digits of the MMSI (the Maritime Identification
  Digits) → country / flag (ISO alpha-2). Used for the `country` field and the
  flag asset in the web console.
- **Nav-status table:** `NavigationalStatus` code → label (Under way using
  engine, At anchor, Moored, Aground, Fishing, …) — drives the moored/slow
  filter.

---

## Python packages

The marine side adds **one** new runtime dependency: a WebSocket client
(`websockets` is the standard choice; `httpx` does not speak WebSocket). The
optional paid fallback reuses the existing `httpx`. To be added to
`requirements.txt` at implementation time.

## Configuration (proposed `.env` keys)

Mirrors the AIR naming style; all marine keys are prefixed for the hard cutoff:

```
# aisstream.io (required marine source)
AISSTREAM_API_KEY=
AISSTREAM_ENABLED=true
AISSTREAM_WS_URL=wss://stream.aisstream.io/v0/stream

# Channels
MARINE_DEFAULT_RADIUS_MILES=15
MARINE_CHANNEL_IDLE_TTL_MS=28800000   # 8 hours from last request
MARINE_VESSEL_TTL_MS=900000           # drop a vessel after 15 min of silence
MARINE_GC_INTERVAL_MS=300000          # sweep stores + reap idle channels

# Filtering (analog of AIR's grounded/slow-plane filter)
FILTER_MOORED_VESSELS=true
MARINE_VESSEL_MIN_SPEED_KNOTS=0.5

# Optional paid fallback (leave key blank to disable)
MARINE_FALLBACK_API_KEY=
MARINE_FALLBACK_MAX_CONCURRENCY=2
MARINE_FALLBACK_MIN_INTERVAL_MS=350
```

The `AISSTREAM_API_KEY` and `MARINE_FALLBACK_API_KEY` are **secrets** — `.env`
only, never logged or echoed.

---

## How we monitor it

A marine metrics namespace (parallel to AIR's, separate counters) on the Usage
screen. Because there are no per-request credits, the marine metrics center on
connection health and store coverage:

- `ais.messages_received`, by message type.
- `marine.channels_active` and per-channel `marine.vessels_tracked`.
- `ais.ws_connected` (gauge) and `ais.ws_reconnects`.
- Served-locally counts: requests answered purely from the store (≈ all of
  them) and fallback calls made (≈ zero).
