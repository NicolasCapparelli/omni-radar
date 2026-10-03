# Architecture: How the Marine Middleware Works

> *Migrated into Continuity on 2026-10-02 from `DevGuide/MARINE/architecture.md`; original text unchanged apart from link repair and this note. It was written as a pre-implementation design, so check details against `app/` (known mismatches: the repoint endpoint takes query parameters, not a JSON body, and a channel box is fixed by the opening request). The "proposed" tables describe the design, not necessarily the final code. Differences from current code: [status → Documentation drift](../../status.md#documentation-drift).*

This is the marine counterpart to the AIR [architecture.md](../air-architecture.md).
It describes how vessel tracking works end-to-end and — like AIR — how almost
all the work is done **locally** so external usage stays tiny. For the raw
limits and terms of each external source, see
[external-dependencies.md](external-dependencies.md).

Read the AIR architecture doc first. Marine mirrors it intentionally; this doc
focuses on what's the **same**, what's **different**, and why.

## The core idea (same as AIR)

A naive tracker would call a paid marine API for every vessel on screen. We
avoid almost all of that. With AIS the win is even bigger than with aircraft:
the AIS broadcast itself carries nearly every field a user sees — name,
callsign, IMO, ship type, dimensions, draught, **destination**, and ETA — all on
the same free stream as the live positions. So unlike AIR (which needs a
per-flight route lookup via adsbdb), marine needs **no per-vessel network
enrichment at all** in the common case. Everything is derived from the stream
plus offline reference tables.

## The big structural difference: WebSocket push vs. REST poll

| | AIR (OpenSky) | MARINE (aisstream.io) |
| --- | --- | --- |
| Transport | REST `/states/all` | WebSocket stream |
| Model | Poll: 1 call per client request | Push: always-on subscription |
| Cost driver | Calls per poll (credits) | Open connections (count + uptime) |
| Per-request external cost | 1 bulk call | **0** (served from in-memory store) |

OpenSky is pulled on demand. aisstream.io pushes a continuous feed for a
subscribed bounding box, so we can't fetch it per request. Instead a long-lived
background task ingests the stream into an in-memory **vessel store**, and client
requests read and bbox-filter that store locally.

```
                          ┌────────────────────────────────────────────────────┐
   ESP32 / web console    │                Omni-Radar middleware                │
        │                 │                                                      │
        │ GET /api/marine/ │   ChannelManager                                    │
        │   {channel}/     │     ├─ channel "xxyy" ──► WS subscription ──────────┼──► aisstream.io
        │   nearby?lat&lon │     │     └─ VesselStore (MMSI-keyed, TTL)  ◄────────┤    (1 socket per
        ├────────────────►│     ├─ channel "aabb" ──► WS subscription ──────────┼──►  active channel)
        │                 │     │     └─ VesselStore                             │
        │                 │   1. resolve channel + reset 8h idle timer           │
        │                 │   2. read store, filter by bounding box (local)      │
        │   JSON array    │   3. classify + enrich each vessel (local)           │
        │◄────────────────┤   4. assemble VesselPayload                          │
        └─────────────────┴──────────────────────────────────────────────────────┘
```

## AIS in one paragraph

AIS (Automatic Identification System) is the maritime equivalent of aircraft
ADS-B. Commercial vessels (>300 GT) and most recreational boats broadcast over
VHF; terrestrial and satellite receivers collect it. Two message families
matter to us:

- **Position reports** (`PositionReport`, `StandardClassBPositionReport`) —
  position, speed over ground (already in **knots**), course over ground, true
  heading, navigational status. Sent every ~2–10 s (Class A) / ~30 s (Class B).
- **Static data** (`ShipStaticData`) — name, callsign, IMO, ship type,
  dimensions, max draught, **destination**, ETA. Sent every ~6 min.

A vessel is identified by its **MMSI** (carried as `UserID` in the aisstream
payload), the marine analog of an aircraft's ICAO24/callsign.

## Channels (marine's answer to "home")

AIR uses a single `HOME_LAT`/`HOME_LON` and accepts arbitrary per-request
coordinates because each request is an independent OpenSky poll. Marine can't do
that — re-pointing means tearing down and re-opening a WebSocket. So instead of
one mutable home, marine exposes **channels**: multiple independent monitored
areas, each addressable in the URI.

```
GET /api/marine/{channel}/nearby?lat=..&lon=..&radius=..
```

- **`{channel}`** is a caller-chosen key (e.g. `nyc`, `xxyy`, `aabb`). Each key
  maps to its own coordinates, its own WebSocket subscription, and its own
  `VesselStore`. Multiple channels run concurrently and independently.
- **Coordinates** bind to a channel when it's first opened (from the request's
  `lat`/`lon`/`radius`, falling back to configured defaults). Re-pointing an
  existing channel is an explicit action (see below) so a casual request never
  silently churns a live socket.

### Channel lifecycle (lazy open, 8-hour idle expiry)

```
first request to {channel}
        │
        ▼
  open WebSocket subscription for the channel's bbox ──► start filling VesselStore
        │
   each request to {channel}  ──► reset "last access" timestamp
        │
   reaper loop: if (now - last_access) > MARINE_CHANNEL_IDLE_TTL (default 8h)
        │
        ▼
  close WebSocket, drop VesselStore   (channel goes cold)
        │
   later request after shutdown  ──► fresh open, another 8h
```

A channel that nobody has queried for 8 hours shuts its socket down to save on
connection monitoring. The next request re-opens it (and the store starts cold,
re-warming as new AIS messages arrive — typically seconds to a couple minutes
for static data). This keeps the number of live WebSockets proportional to
**recently-active areas**, not to every area ever requested.

### Re-pointing / reset

There is a dedicated action to move a channel to new coordinates (the
"reset home" idea, generalized per-channel):

```
POST /api/marine/{channel}      { "lat":.., "lon":.., "radius":.. }
```

This tears down the channel's existing subscription and re-opens it on the new
bounding box (store is cleared, idle timer reset). Read-only `nearby` requests
never re-point a channel implicitly.

## Request walkthrough (`GET /api/marine/{channel}/nearby`)

### 1. Resolve the channel (`ChannelManager`)
Look up `{channel}`. If it's cold (never opened or idle-expired), open a
WebSocket subscription for its bounding box and begin ingesting. Either way,
reset the channel's last-access timestamp (the 8h idle clock).

### 2. Read + bbox-filter the store (local, zero network)
The channel's `VesselStore` holds the latest known state per MMSI. We take a
snapshot and keep only vessels inside the requested radius. Because the socket's
subscription box is sized to cover the channel's max radius, a narrower
per-request radius is just a local filter.

### 3. Classify + filter (local — mirrors AIR step 3)
- **Vessel classification** — map the AIS ship **Type code** (0–99) to a
  category label (Cargo, Tanker, Passenger, Fishing, Tug, Sailing, Pleasure,
  High-Speed Craft, Pilot, Search & Rescue, Law Enforcement, Military, …). This
  is the marine analog of `classify_type`. Offline, free.
- **Moored/slow filter** — the analog of AIR's grounded/slow-plane filter. Drop
  a vessel that is moored/at-anchor/aground (from nav status) or, when underway,
  slower than `MARINE_VESSEL_MIN_SPEED_KNOTS`. Keeps the screen to vessels
  actually moving; special types (SAR, law enforcement, pilot) are always kept.

### 4. Per-vessel enrichment (all local)
Build the display fields with **no network calls**:
- **Name, callsign, IMO, dimensions, draught, destination, ETA** — from the
  cached `ShipStaticData` already in the store.
- **Country / flag** — from the **MMSI MID** (first 3 digits) → country table.
  The analog of AIR's ICAO24 → country derivation. Offline.
- **Operator class & special designation** — derived locally from ship type +
  nav status (Commercial / Cargo / Passenger / Fishing / Military / Government /
  Pleasure, plus SAR / Law-Enforcement / Pilot / Tug / Medical flags). The
  analog of AIR's `operator_class` / `special_designation`. Offline.

Optionally, a **paid REST fallback** (e.g. MarineTraffic) can fill gaps for
vessels we've seen a position for but not yet static data. This is scaffolded
but **secondary** — disabled unless a key is set, cached/throttled exactly like
FlightAware. See [external-dependencies.md](external-dependencies.md).

### 5. Assemble the payload
Each vessel becomes a descriptive, unit-bearing `VesselPayload`. Proposed fields
(parallel to `AircraftPayload`, divergent where the domain differs):

| Field | Source | AIR analog |
| --- | --- | --- |
| `mmsi` | UserID | (callsign) |
| `name` | ShipStaticData.Name | — |
| `callsign` | ShipStaticData.CallSign | `callsign` |
| `imo_number` | ShipStaticData.ImoNumber | `registration` |
| `vessel_type` | Type code → label | `vehicle_type` |
| `ship_type_code` | Type | `model_code` |
| `nav_status` | NavigationalStatus → label | (`on_ground`) |
| `destination` | ShipStaticData.Destination | `destination` |
| `eta` | ShipStaticData.Eta | — |
| `speed_knots` | Sog | `speed_knots` |
| `course_degrees` | Cog | — |
| `heading_degrees` | TrueHeading | `heading_degrees` |
| `latitude` / `longitude` | Lat / Lon | same |
| `length_meters` / `beam_meters` | Dimension A+B / C+D | — |
| `draught_meters` | MaximumStaticDraught | `altitude_feet` (dimension-ish) |
| `country` | MMSI MID → country | `country` |
| `operator_class` | derived | `operator_class` |
| `special_designation` | derived | `special_designation` |

There is deliberately **no** altitude/squawk/vertical-speed (AIR-only) and AIR
has no draught/ETA/nav-status (marine-only) — the hard external cutoff.

## The local-work pieces, at a glance

| Piece | Module (proposed) | AIR mirror |
| --- | --- | --- |
| Bounding-box math | reuse `geo.py` | same |
| AIS WebSocket client + reconnect/backoff | `aisstream.py` | `opensky.py` |
| In-memory MMSI store + TTL eviction | `vessel_store.py` | role of `cache.py` |
| Channel registry + 8h idle reaper | `channels.py` | (new concept) |
| Ship-type + MMSI-MID + nav-status tables | `marine_static_data.py` | `static_data.py` |
| Classification + filter + payload assembly | `marine_enrich.py` | `enrich.py` |
| `VesselPayload` schema | add to `models.py` | `AircraftPayload` |
| Optional paid fallback | `marinetraffic.py` | `flightaware.py` |
| Marine endpoints + lifespan wiring | `main.py` | `/api/nearby` + `gc_task` |

## How it all adds up

For a single `/api/marine/{channel}/nearby` request over a busy area:
- **0** external calls — the response is served entirely from the channel's
  in-memory store.
- **0** network calls for name/type/destination/dimensions/country — all from
  the stream + offline tables.
- The only standing external cost is **one WebSocket per active channel**, held
  for at most 8 idle hours.

So external usage scales with the number of **recently-active channels**, not
with vessel count, request rate, or total areas ever requested.

## Adaptive polling

The marine store refreshes continuously from the stream, so there is no
credit-driven back-off like AIR. Marine still advertises a recommended client
poll interval (so the device/console don't hammer it pointlessly): a small fixed
default, since the underlying AIS position cadence is ~2–30 s. The
`X-Recommended-Poll-Seconds` convention is reused for symmetry with AIR.

## Failure behavior (mirrors AIR's degrade-gracefully stance)

- **aisstream WS drops** → the channel's ingest task reconnects with backoff;
  requests keep serving the last-known store contents (vessels age out by TTL if
  the outage is long).
- **Channel cold / just opened** → the store is still warming; `nearby` returns
  whatever has arrived so far (positions first, static data fills in within
  minutes). No error.
- **Paid fallback down/disabled** → vessels simply show only stream-derived
  fields; everything else still renders.
