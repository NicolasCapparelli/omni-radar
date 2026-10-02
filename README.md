# Local Traffic Radar — Middleware Proxy

Self-hosted middleware for the ESP32 Local Traffic Radar. It aggregates live
aircraft state vectors from the **OpenSky Network**, enriches them with aircraft
metadata from the offline **OpenSky aircraft database** and flight routes from
**adsbdb.com** (free) with **FlightAware AeroAPI** as an optional fallback, and
serves a descriptive JSON payload to the hardware device. Routes are cached
hard (and persisted to disk) since they're static for a flight's life.

```
[OpenSky API] + [Static DBs] ──▶ (Middleware) ──▶ [Clean JSON] ──▶ [ESP32]
```

## Architecture

| Module | Responsibility |
| --- | --- |
| `app/main.py` | FastAPI app, `GET /api/nearby`, background GC loop |
| `app/geo.py` | Radius → bounding box (69 mi/° lat, 69·cos(lat) mi/° lon) |
| `app/opensky.py` | OAuth2 token mgmt + `/states/all` fetch |
| `app/adsbdb.py` | adsbdb.com route provider (primary, free) |
| `app/flightaware.py` | AeroAPI route provider (optional fallback) |
| `app/routes.py` | Provider throttle + route resolution |
| `app/cache.py` | Persistent route cache (TTL + GC + disk) |
| `app/static_data.py` | Offline airline / special-operator lookups |
| `app/aircraft_db.py` | Offline ICAO24 → aircraft type lookup (free `mdl` fallback) |
| `app/enrich.py` | Per-aircraft enrichment pipeline |
| `app/models.py` | Optimized short-key payload schema |

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env   # then fill in your credentials
```

Get credentials:
- **OpenSky**: https://opensky-network.org/ → My OpenSky → API Clients (OAuth2 client id/secret).
- **adsbdb**: no key required (free public route API).
- **FlightAware AeroAPI** (optional): https://www.flightaware.com/aeroapi/ — only a route fallback.

The middleware runs fine without credentials (anonymous OpenSky, no enrichment),
which is useful for local smoke testing.

### Optional: offline aircraft database (free `mdl` enrichment)

The OpenSky aircraft database fills the `mdl` (aircraft type) field for free —
even for flights with no AeroAPI route record or that get rate-limited.

The server **auto-downloads it on startup** when the local file is missing or
older than `AIRCRAFT_DB_MAX_AGE_DAYS` (default 30). To pre-fetch or force a
refresh manually:

```powershell
python scripts/download_aircraft_db.py   # -> data/aircraftDatabase.csv (~100+ MB)
```

It's loaded into memory at startup and used as a fallback whenever FlightAware
doesn't supply a model. Set `AIRCRAFT_DB_AUTO_DOWNLOAD=false` to disable the
auto-download; if no file is present, the lookup is silently skipped.

## Run

```powershell
python -m app.main
# or
uvicorn app.main:app --reload
```

## Endpoints

### `GET /api/nearby`
Query params (all optional; fall back to `.env` defaults):

| Param | Type | Example | Notes |
| --- | --- | --- | --- |
| `lat` | float | `40.7580` | Home latitude |
| `lon` | float | `-73.9965` | Home longitude |
| `radius` | int | `15` | Search radius in miles |

Example:
```
GET /api/nearby?lat=40.75&lon=-73.99&radius=15
```

Response — array of objects using the optimized key map:

```json
[
  {
    "callsign": "DAL1942",
    "vehicle_type": "Plane",
    "model_code": "A321",
    "model_name": "Airbus A321",
    "airline": "Delta Air Lines",
    "origin": "MIA",
    "origin_name": "Miami Intl",
    "origin_country": "US",
    "destination": "LGA",
    "destination_name": "LaGuardia Airport",
    "destination_country": "US",
    "altitude_feet": 4250,
    "speed_knots": 271,
    "vertical_speed_fpm": -640,
    "heading_degrees": 42,
    "squawk": "2241",
    "emergency": "None",
    "on_ground": false,
    "country": "United States",
    "registration": "N123DL",
    "operator_class": "Commercial",
    "operator": "Delta Air Lines",
    "owner": "Delta Air Lines Inc",
    "special_designation": "None"
  }
]
```

Field notes:
- Units are in the names: `altitude_feet`, `speed_knots` (ground speed),
  `vertical_speed_fpm` (feet/min, +climb/-descent), `heading_degrees`.
- `squawk` is the transponder code; `emergency` is `Hijack`/`Radio Failure`/
  `Emergency` for codes 7500/7600/7700, else `None`.
- `on_ground` flag; `country` from the ICAO24 allocation.
- `registration`, `operator`, `owner` come from the offline aircraft DB.
  `operator` falls back to the resolved `airline` name when the DB has none.
- `operator_class` is the derived category (Commercial/Cargo/Private/Military/
  Government); `special_designation` is the special-ops flag (Police/News/...).
- `model_code` is the ICAO type code; `model_name` the friendly name.

### `GET /health`
Liveness probe + cache size + which integrations are active.

### `GET /api/metrics`
Session usage counters: external API calls per provider (OpenSky / adsbdb /
FlightAware) versus work served locally (route cache hits, grounded-plane
filtering, offline aircraft-DB enrichment), plus a `local_served_ratio`.
`GET /api/metrics/reset` zeroes the counters for a clean measurement run.

## Caching & rate-limit behavior

Flight routes are the only thing requiring a network call (everything else is
offline). Resolution goes adsbdb → FlightAware, shielded by a persistent cache:

- **Found**: cached for `ROUTE_CACHE_TTL_MS` (default 12 h) — routes don't change
  mid-flight.
- **No route** (e.g. GA / private): negatively cached for `ROUTE_NEGATIVE_TTL_MS`
  (default 3 h) so we don't re-query known-empty callsigns.
- **Transient** (429 / 5xx / network): **not** cached and **not** retried in-line
  — it simply defers to the next poll, so a busy moment never amplifies into a
  retry storm.
- **Throttling**: each provider caps concurrency (`*_MAX_CONCURRENCY`) and spaces
  requests (`*_MIN_INTERVAL_MS`).
- **Persistence**: the cache is written to `CACHE_PERSIST_PATH` every
  `GC_INTERVAL_MS` and on shutdown, and reloaded on startup, so restarts reuse
  resolved routes instead of re-hitting providers.

## Implementation notes

1. **Vehicle classification.** Spans the full ICAO/OpenSky taxonomy (Plane,
   Helicopter, Glider, Seaplane, Amphibian, Gyrocopter, Tiltrotor,
   Lighter-than-air, Ultralight, Skydiver, Drone, Spacecraft, Surface Vehicle,
   Obstacle). The offline aircraft DB's ICAO Doc 8643 descriptor gives the
   airframe-accurate class (H/G/T/S/A are definitive); OpenSky's broadcast
   category covers the rest. This is more reliable than category alone, which
   many transponders leave unset.
2. **Descriptive field names.** Payload keys are spelled out and carry units
   where applicable (`altitude_feet`, `speed_knots`, `vertical_speed_fpm`,
   `heading_degrees`, `country`, `registration`, ...).
3. **Airline names.** Resolved offline first via the ICAO-designator table in
   `app/static_data.py` (callsign prefix), then the route provider's airline,
   then `"Unknown Airline"`.
4. **Aircraft model (`model_code`).** Comes from the offline OpenSky aircraft
   database (ICAO24 → type code) for free; a route provider's type is used only
   if the DB has none.
5. **Friendly model name (`model_name`).** Derived offline from the aircraft
   database's manufacturer + model columns (e.g. `Bell 429`).
6. **Plane filtering.** A plane is dropped outright when `on_ground` is true;
   when it isn't, the speed gate decides — the plane is kept only if airborne
   and moving faster than `PLANE_MIN_SPEED_MPH` (default 60 mph). So `on_ground`
   is trusted when set, and speed covers the case where it isn't. Helicopters
   and all non-plane types are always kept. Toggle with `FILTER_GROUNDED_PLANES`.
