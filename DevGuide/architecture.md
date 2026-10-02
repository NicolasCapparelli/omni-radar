# Architecture: How the Middleware Works

This is a medium/high-level tour of the Omni-Radar middleware — what it does on
each request, and (the heart of the design) all the work it does **locally** so
that external API usage stays tiny. For the raw limits and costs of each
external service, see [external-dependencies.md](external-dependencies.md).

## The core idea

A naive tracker would, for every aircraft on screen, call a paid flight API for
its route and aircraft details — dozens of calls per refresh, blowing through
rate limits in a dense area like NYC. We avoid almost all of that.

The key realization: **only two things truly require the network** — the live
positions (one bulk call) and the flight *route* (origin → destination). Every
other field a user sees (aircraft model, registration, owner, airline, vehicle
type, helicopter detection, country, speed, altitude, heading, squawk) is
derived **locally** for free. And even routes are cached so hard that repeat
lookups cost nothing.

```
                         ┌─────────────────────────────────────────────┐
   ESP32 / web console   │              Omni-Radar middleware            │
        │                │                                               │
        │ GET /api/nearby│   1. radius → bounding box (geo.py)           │
        ├───────────────►│   2. OpenSky /states/all  ◄── 1 bulk call ────┼──► OpenSky
        │                │   3. classify + filter (local)                │
        │                │   4. enrich each aircraft:                    │
        │                │        • model/reg/owner/type ◄ offline DB     │
        │                │        • airline ◄ offline table               │
        │                │        • route ◄ cache → adsbdb → FlightAware  ┼──► adsbdb / FA
        │   JSON array   │   5. assemble descriptive payload             │     (only on
        │◄───────────────┤                                               │      cache miss)
        └────────────────┴───────────────────────────────────────────────┘
```

## Request walkthrough (`GET /api/nearby?lat&lon&radius`)

### 1. Radius → bounding box (`geo.py`)
The hardware sends a home coordinate + radius (miles). We convert that to the
lat/lon bounding box OpenSky needs, using flat-earth approximations
(69 mi per ° latitude, 69·cos(latitude) mi per ° longitude). Keeping the box small also keeps
the OpenSky credit cost at the minimum (1 credit per call).

### 2. One bulk OpenSky call (`opensky.py`)
A single `GET /states/all` for the box returns every aircraft's *state vector*:
position, barometric altitude, ground speed, heading, vertical rate, squawk,
on-ground flag, and ADS-B emitter category. **This is the only call whose count
is independent of how many aircraft are present** — one call covers the whole
area. We also read the rate-limit headers here to track remaining credits.

### 3. Classification + filtering (local, `enrich.py`)
Before spending anything on enrichment, we process the raw vectors locally:

- **Vehicle classification** — full ICAO/OpenSky taxonomy (Plane, Helicopter,
  Glider, Seaplane, Amphibian, Gyrocopter, Tiltrotor, Lighter-than-air,
  Ultralight, Skydiver, Drone, Spacecraft, Surface Vehicle, Obstacle). We use
  the offline aircraft DB's Doc 8643 descriptor (airframe-accurate for
  H/G/T/S/A) and fall back to OpenSky's broadcast category for the rest. This is
  more reliable than the broadcast category alone, which many transponders leave
  unset.
- **Grounded/slow-plane filter** — a plane is dropped if it's `on_ground`, or if
  it's airborne but slower than `PLANE_MIN_SPEED_MPH` (default 60). Helicopters
  and all non-plane types are always kept. This removes parked/taxiing clutter
  **before** any route lookup, so those aircraft cost zero enrichment calls. In
  a busy area this is the single biggest saver — often 70–90% of targets.

### 4. Per-aircraft enrichment (mostly local)
For each surviving aircraft we build the display fields:

- **Aircraft model, registration, owner, type code** — looked up in the
  **offline OpenSky aircraft database** (`aircraft_db.py`) by the 24-bit ICAO
  address that's already in every state vector. ~480k airframes held in memory;
  zero network cost. Replaces what would otherwise be paid aircraft-info calls.
- **Airline name** — resolved from a static ICAO-designator table
  (`static_data.py`) keyed off the callsign prefix (e.g. `DAL` → Delta). Free.
- **Operator class & special designation** — derived locally (Commercial /
  Cargo / Private / Military / Government, plus Police/News/Medical flags) from
  the callsign, static tables, and the DB registration. Free.
- **Route (origin → destination)** — the *only* per-aircraft field that may need
  the network, and it goes through the cache-first chain described next.

### 5. Route resolution (`routes.py`, `adsbdb.py`, `flightaware.py`, `cache.py`)
Routes are resolved through a cache-shielded provider chain:

1. **Persistent cache first** (`cache.py`). Routes don't change during a flight,
   so resolved routes are cached for 12h and **persisted to disk**, surviving
   restarts. A cache hit costs nothing.
2. **adsbdb** (primary) — free, keyless community API. Most commercial traffic
   resolves here.
3. **FlightAware AeroAPI** (optional fallback) — only queried when adsbdb has no
   route, and only if a key is configured.

Three caching outcomes:
- **Found** → cached 12h.
- **Definitively no route** (e.g. private GA) → *negatively* cached ~3h, so we
  stop re-asking about known-empty callsigns.
- **Transient failure** (429/5xx/network) → not cached and **not retried
  in-line**; it simply defers to the next poll, so a busy moment never
  amplifies into a retry storm.

Providers are throttled (concurrency + spacing) to stay polite. After a brief
warm-up the cache covers the recurring traffic, so steady-state route calls drop
to just the genuinely new callsigns.

### 6. Assemble the payload
Each aircraft becomes a descriptive, unit-bearing JSON object
(`models.py`): `callsign`, `vehicle_type`, `model_code`, `model_name`,
`airline`, `origin`/`destination` (+ names), `altitude_feet`, `speed_knots`,
`vertical_speed_fpm`, `heading_degrees`, `latitude`/`longitude`, `squawk`,
`emergency`, `on_ground`, `country`, `registration`, `operator_class`,
`operator`, `owner`, `special_designation`.

## The local-work pieces, at a glance

| Piece | Module | Replaces / avoids |
| --- | --- | --- |
| Bounding-box math | `geo.py` | Keeps OpenSky at min credit cost |
| Bulk position fetch | `opensky.py` | 1 call regardless of aircraft count |
| Vehicle classification | `enrich.py` + `aircraft_db.py` | Paid aircraft-type lookups |
| Grounded/slow filter | `enrich.py` | Route lookups for parked/taxi traffic |
| Offline aircraft DB | `aircraft_db.py` | Paid model/registration/owner lookups |
| Airline / operator tables | `static_data.py` | Paid operator lookups |
| Route cache (disk-backed) | `cache.py` | Repeat route lookups (incl. across restarts) |
| Free route provider | `adsbdb.py` | Paid FlightAware route calls |

## How it all adds up

For a single `/api/nearby` poll over a busy area:
- **1** OpenSky call (always), regardless of aircraft count.
- **0** route calls for filtered (parked/taxiing) planes.
- **0** route calls for any aircraft whose route is already cached.
- **0** network calls for model/registration/owner/airline/type/classification —
  all local.
- A handful of route calls only for *new, airborne, moving* aircraft not yet in
  the cache — and those are free via adsbdb in the common case.

So external usage scales with **new distinct airborne callsigns**, not with the
number of aircraft on screen or the polling frequency. Everything else is served
locally. The **Usage** screen (`/api/metrics`) quantifies this live: calls made
per provider vs. calls avoided by the cache, the filter, and the offline DB.

## Adaptive polling

The middleware never polls on its own — clients (device/web console) poll it.
Because the middleware is the one that knows OpenSky's remaining credit balance
(from the rate-limit headers), it advertises a **recommended poll interval** via
the `X-Recommended-Poll-Seconds` response header and `/api/metrics`. The
interval starts at `POLL_DEFAULT_SECONDS` (30) and automatically backs off as
credits run low. OpenSky data only refreshes every ~5s, so that's the floor.

## Failure behavior

- **OpenSky down/429** → `/api/nearby` returns `502`; the client keeps the last
  good data and retries next poll.
- **Route provider down/429** → that aircraft shows no route this poll; retried
  next poll. Everything else (model, type, etc.) still renders from local data.
- **Aircraft DB missing** → model/registration/owner and DB-based helicopter
  detection are skipped; positions and classification by broadcast category
  still work.
