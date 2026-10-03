# Implementation map

The map has 11 capability routes and 7 shared foundations. Every source path below is relative to the repository root. The verification commands referred to as "the checks" are in [setup → Verify a change](../developer/setup.md#verify-a-change). There are no automated tests.

## Routes

### Setup and resumption

- **Vocabulary:** get it running again, pick this back up, returning after a break, install, env, credentials, flash the device, "screen shows nothing", where was I.
- **Read first:** [status → Active work and last stopping point](../status.md#active-work-and-last-stopping-point) and [status → Known defects](../status.md#known-defects), then [setup → Install, build, and run](../developer/setup.md#install-build-and-run) and [setup → Configuration](../developer/setup.md#configuration).
- **Source starts:**
  - Startup wiring: `app/main.py` `lifespan`
  - Config: `app/config.py`, `.env.example`
  - Device config: `hardware/include/config.example.h`. It is missing `BRIGHTNESS`; see [setup → Troubleshooting](../developer/setup.md#troubleshooting).
- **Verify:** the checks; `GET /health` once the server is running.

### AIR nearby endpoint

- **Vocabulary:** `/api/nearby`, aircraft near me, planes, flights, radius, bounding box, 502, upstream unavailable, `nearby()`.
- **Boundary:** request parameters and defaults, the single OpenSky fetch, the error mapping, and the poll header. It delegates enrichment.
- **Source starts:**
  - Handler: `app/main.py` `nearby`
  - Box: `app/geo.py` `compute_bounding_box`
- **Model:** [AircraftPayload](../data/model.md#aircraftpayload).
- **Detail:** [user/api.md](../user/api.md#endpoints) has the endpoint reference and example JSON; [developer/air-architecture.md](../developer/air-architecture.md) has the request walkthrough.
- **Depends on:** [OpenSky client](#opensky-client), [AIR enrichment pipeline](#air-enrichment-pipeline), [Metrics and adaptive polling](#metrics-and-adaptive-polling).

### OpenSky client

- **Vocabulary:** OpenSky, state vectors, `/states/all`, OAuth2, token, credits, 429, rate limit, anonymous access, altitude/speed conversion, squawk, emergency 7700.
- **Boundary:** auth, the HTTP call, rate-limit header capture, parsing state-vector arrays, and unit conversion.
- **Source starts:**
  - Client: `app/opensky.py` `OpenSkyClient.get_states_in_box`
  - Parsing and units: `StateVector.from_array` and its properties
- **Model:** [Units and conversions (AIR)](../data/model.md#units-and-conversions-air).
- **Detail:** credit tiers are in [developer/external-dependencies.md](../developer/external-dependencies.md#1-opensky-network--live-state-vectors-required).
- **Verify:** smoke-test `StateVector.from_array` on a sample array.

### AIR enrichment pipeline

- **Vocabulary:** enrich, classify, vehicle type, helicopter detection, grounded or slow filter, `FILTER_GROUNDED_PLANES`, `PLANE_MIN_SPEED_MPH`, model code, registration, operator, owner, payload assembly.
- **Boundary:** classification, filtering, and per-aircraft merging of route and DB data into a payload. Route lookup itself belongs to [Route resolution](#route-resolution-and-cache).
- **Source starts:**
  - Orchestrator: `app/enrich.py` `build_payloads`
  - Rules: `classify_type`, `_should_drop_plane`
  - Assembly: `_build_payload`
- **Model:** [Precedence and derived values](../data/model.md#precedence-and-derived-values). Note that the `model_code` precedence contradicts the README.
- **Depends on:** [Offline aircraft database](#offline-aircraft-database), [Offline lookup tables](#offline-lookup-tables), [Payload contract](#payload-contract).

### Route resolution and cache

- **Vocabulary:** route, origin/destination, airport, adsbdb, FlightAware, AeroAPI, fallback, negative cache, "no route", route cache, `route_cache.json`, `CACHE_VERSION`, provider throttle.
- **Boundary:** the provider order and the found/notfound/unavailable taxonomy (`routes.py`); per-provider HTTP and parsing (`adsbdb.py`, `flightaware.py`); TTL storage and disk persistence (`cache.py`).
- **Source starts:**
  - Cache policy: `app/enrich.py` `_resolve_metadata`
  - Provider chain: `app/routes.py` `resolve_route`
  - Parsers: `app/adsbdb.py` `AdsbdbClient.fetch_route`, `app/flightaware.py` `FlightAwareClient.fetch_route`
  - Storage: `app/cache.py` `MetadataCache`, `run_gc_loop`
- **Model:** [Route cache entry](../data/model.md#route-cache-entry-flightmeta). Known gap: FlightAware routes carry no airport country (no flags).
- **Depends on:** [Throttle](#provider-throttle), [Background loops](#lifecycle-and-background-loops).

### Offline aircraft database

- **Vocabulary:** aircraft DB, `aircraftDatabase.csv`, ICAO24, typecode, Doc 8643, descriptor, tail number, auto-download, stale DB, `download_aircraft_db.py`.
- **Source starts:**
  - Loader and lookup: `app/aircraft_db.py` `AircraftDatabase.load`, `get`, `descriptor_class`
  - Refresh: `ensure_database`, and the CLI wrapper `scripts/download_aircraft_db.py`
- **Note:** startup re-downloads the CSV when it is stale. Avoid triggering this unintentionally; see [setup → Verify a change](../developer/setup.md#verify-a-change).

### Offline lookup tables

- **Vocabulary:** add an airline, ICAO designator, callsign prefix, cargo operator, military, police, news, medical, operator class, special designation, AIS ship type, nav status, MID, flag country.
- **Boundary:** pure data plus small functions. Changes here alter classification and filters elsewhere.
- **Source starts:**
  - AIR: `app/static_data.py` `AIRLINE_BY_ICAO`, `SPECIAL_BY_CALLSIGN_PREFIX`, `SPECIAL_PATTERNS`, `MILITARY_ICAO24_RANGES`, `operator_class`
  - Marine: `app/marine_static_data.py` `NAV_STATUS`, `STATIONARY_NAV_STATUS`, `vessel_category`, `_CATEGORY_OPERATOR_CLASS`, `_MID_TO_ISO`, `country_from_mmsi`
- **Cross-effects:**
  - An airline-table entry makes the flight `Commercial` and is preferred as the `airline` name.
  - The `airline` name is stored inside cached `FlightMeta` entries. Callsigns already in the cache keep their old name until the entry expires (up to 12 h, and the cache is persisted across restarts). To see a table change immediately, delete `data/route_cache.json` or bump `CACHE_VERSION`. `operator_class` is computed per request, so it changes right away.
  - A marine category added to `_ALWAYS_KEEP` (in `marine_enrich.py`) bypasses the moored filter.
- **Verify:** smoke-test `operator_class`, `special_designation`, `vessel_category`, `country_from_mmsi`.

### MARINE channels and ingest

- **Vocabulary:** marine, AIS, vessels, ships, boats, aisstream, WebSocket, channel, MMSI, warm-up, idle expiry, 8 hours, reconnect, repoint, `POST /api/marine/{channel}`, 503 `marine_disabled`.
- **Boundary:** channel registry and lifecycle, the WebSocket ingest loop, and the per-MMSI merge store. It does not include payload rules.
- **Source starts:**
  - Endpoints: `app/main.py` `marine_nearby`, `marine_repoint`, `_marine_box`
  - Registry: `app/channels.py` `ChannelManager.snapshot`, `repoint`, `reap_once`
  - Ingest: `app/aisstream.py` `AisStreamClient.run`, `_handle_message`
  - Store: `app/vessel_store.py` `VesselStore`
- **Model:** [VesselState, Channel](../data/model.md#vesselstate-channel).
- **Limit:** the channel box is fixed by the opening request; see [architecture → MARINE request flow](../developer/architecture.md#marine-request-flow).
- **Detail:** [developer/marine/architecture.md](../developer/marine/architecture.md) is the pre-implementation design. Its status line is stale.
- **Verify:** a live run needs `AISSTREAM_API_KEY`. Offline, `VesselStore` can be exercised directly in a snippet.

### MARINE enrichment

- **Vocabulary:** vessel type, moored or anchored filter, `FILTER_MOORED_VESSELS`, `MARINE_VESSEL_MIN_SPEED_KNOTS`, draught, ETA, nav status label, vessel flag.
- **Source starts:**
  - Orchestrator: `app/marine_enrich.py` `build_vessel_payloads`
  - Rules: `_should_drop_vessel`, `_ALWAYS_KEEP`
  - Assembly: `_build_payload`
- **Model:** [VesselPayload in the schema index](../data/model.md#overview-and-schema-routes) and [Absence semantics](../data/model.md#absence-semantics).
- **Depends on:** [Offline lookup tables](#offline-lookup-tables), [Geo](#geo-and-bounding-boxes).

### Web console

- **Vocabulary:** web UI, debug console, emulator, LCD preview, SCAN, live refresh, Usage tab, metrics dashboard, MODE, ALT radar, ACTION lock, `serve.py`, proxy, partials, port 8080.
- **Boundary:** a browser-only client. Each module owns one DOM region, and `select` is injected from `main.js`.
- **Source starts:**
  - Composition root: `web/js/main.js`
  - Fetch and live loop: `web/js/console.js` `scan`, `scanAir`, `scanMarine`, `scheduleLive`
  - Endpoint wrappers: `web/js/api.js`
  - Rendering: `web/js/device.js` (`renderAircraftCard`, `renderVesselCard`, `renderRadar`), `web/js/table.js` (`rowHtml`, `vesselRowHtml`, `COLSPAN`), `web/js/usage.js` (`renderMetrics`)
  - Markup: `web/partials/console.html`
  - Styling: `web/styles.css`. LCD visual changes must be mirrored in the firmware; see [Device firmware](#device-firmware).
  - Proxy: `web/serve.py` (`Handler._proxy`; GET and POST under `/api`)
- **Detail:** [developer/web-console.md](../developer/web-console.md#extending) covers module boundaries and how to extend them (it predates marine support); [user/web-console.md](../user/web-console.md) covers using the console.
- **Verify:** `node --check` on changed modules, then a manual run.
- **Depends on:** [Payload contract](#payload-contract), [Metrics and adaptive polling](#metrics-and-adaptive-polling).

### Device firmware

- **Vocabulary:** ESP32, hardware, device, firmware, TFT, ST7796, LCD, touch, buttons (POWER/MODE/ACTION/ALT/SET), settings screen, brightness, NVS, WiFi, PlatformIO, flash, radar view, flags atlas, fonts.
- **Boundary:** a single-file Arduino sketch that is AIR-only (MARINE shows a placeholder). The pin and driver config lives in the build flags. The palette and layout mirror `web/styles.css` and `web/js/device.js` by hand, so LCD design changes apply to both.
- **Source starts:**
  - Network: `hardware/src/main.cpp` `fetchNearby`, `buildFilter`, `copyAircraft`
  - Rendering: `renderAll`, `drawAircraftCard`, `drawRadar`, `drawSettings`
  - Input: `handleButton`, `pollTouch`
  - Main loop: `loop`
  - Board config: `hardware/platformio.ini`, `hardware/include/board_pins.h`
  - Generated assets: `hardware/tools/gen_flags.py` and `gen_fonts.py`, which produce `hardware/include/flags.h` and `fonts/*.h`
- **Detail:** pin map, build, and flashing: [developer/hardware.md](../developer/hardware.md#pin-map-esp32-3248s035). Its status table and touch-bus note are stale; see [status → Documentation drift](../status.md#documentation-drift).
- **Verify:** `pio run` in `hardware/`, then flash and watch the serial monitor. Neither was executed.
- **Depends on:** [Payload contract](#payload-contract), [Metrics and adaptive polling](#metrics-and-adaptive-polling) (header), [Configuration](#configuration).

## Shared foundations and dependency routes

### Payload contract

`AircraftPayload` and `VesselPayload` in `app/models.py` are consumed by `web/js/table.js` and `device.js`, and `AircraftPayload` also by the firmware's `buildFilter`/`copyAircraft`. Any field rename or removal, a sentinel change, or a unit change needs all of these consumers reviewed and the device reflashed. See [Change and compatibility constraints](../data/model.md#change-and-compatibility-constraints). Investigate here whenever a field "shows blank", "shows Unknown", or "is missing a flag".

### Configuration

The middleware reads `app/config.py` `Settings`, with `.env.example` as its template. The firmware reads `hardware/include/config.h` (template `config.example.h`) plus the NVS settings. Defaults for home position and radius are duplicated across `config.py`, `.env.example`, `config.example.h`, and `web/js/state.js` `DEFAULTS`. See [setup → Configuration](../developer/setup.md#configuration).

### Geo and bounding boxes

`app/geo.py` `BoundingBox`, `compute_bounding_box`, `as_aisstream_bbox`, `contains`. The longitude span is scaled by `cos(latitude)` (floored at 0.01 near the poles), matching the radar renderers (`web/js/format.js` `relativePosition`, firmware `drawRadar`). Investigate here for "targets outside the radius" or "radar distance mismatch".

### Metrics and adaptive polling

**Vocabulary:** health check, `/health`, status dot, `/api/metrics`, Usage tab, served-locally ratio, reset counters, credits remaining, recommended poll.

**Endpoint handlers:** `app/main.py` `health`, `metrics`, `metrics_reset`. `/health` feeds `web/js/status.js` `refreshHealth` (the connection dot).

`app/metrics.py` `METRICS` is the global singleton. Counters are incremented across `app/`. `recommended_poll_seconds` feeds the `X-Recommended-Poll-Seconds` header (in `main.py`), which `web/js/console.js` `effectivePoll` and firmware `fetchNearby` honor. Counter keys and snapshot shape are read by `web/js/usage.js`.

Known quirks:
- The `marine.channels_active` gauge is set only by the reaper, so it is `null` for the first 5 minutes.
- `ais.ws_connected` is one gauge shared by all channels.

### Lifecycle and background loops

`app/main.py` `lifespan` creates the clients, loads the cache and aircraft DB, and starts `cache.run_gc_loop` and `channels.run_reaper_loop`. On shutdown it cancels the loops, closes the channels, saves the cache, and closes the HTTP clients. Investigate here for startup or shutdown issues, persistence, or lost cache entries.

### Provider throttle

`app/routes.py` `Throttle` (semaphore plus minimum interval), configured from the `*_MAX_CONCURRENCY` and `*_MIN_INTERVAL_MS` settings. It is used by `adsbdb.py` and `flightaware.py`. Investigate here for slow enrichment with many new callsigns: throttled route lookups run inside the request's `asyncio.gather`, so the request waits for them.

### External service terms and limits

Authoritative material (migrated from `DevGuide/`): [developer/external-dependencies.md](../developer/external-dependencies.md) (AIR) and [developer/marine/external-dependencies.md](../developer/marine/external-dependencies.md) (MARINE). Read these before changing polling cadence or provider usage, or before persisting or redistributing any third-party data. adsbdb forbids redistribution, and the aisstream terms are unverified.

## Investigation notes

- **Exclusions:** do not orient in `.venv/`, `hardware/.pio/`, `__pycache__/`, `data/` (the large CSV and the cache JSON), `hardware/tools/*.ttf`, or the generated `hardware/include/flags.h` and `hardware/include/fonts/*.h`. Regenerate those with `hardware/tools/gen_*.py`; never hand-edit them. Never print `.env` or `hardware/include/config.h`, which contain secrets.
- **Overlapping routes:**
  - "Wrong or missing route" → [Route resolution](#route-resolution-and-cache).
  - "Wrong airline or operator class" → [Offline lookup tables](#offline-lookup-tables) first, then [AIR enrichment](#air-enrichment-pipeline).
  - "Plane missing from the list" → the [AIR enrichment](#air-enrichment-pipeline) filter, then the [OpenSky client](#opensky-client) (dropped for no callsign or position).
- **Stale source comments:**
  - The `app/main.py` module docstring says "via FlightAware" and "short-key".
  - The `app/enrich.py` `_build_payload` comment does not match the actual `model_code` precedence.
  - The `hardware/src/main.cpp` header says "radar view (ALT btn)" is stubbed and that there are four buttons.

  Trust the code.
- **Unused code:** `FlightMeta.is_placeholder`; `AircraftDatabase.lookup_type`, `lookup_model_name`, `lookup_registration`, `is_rotorcraft`; the `channel_box` return value in `marine_nearby`.
- **No matching route?** Search `app/`, `web/js/`, and `hardware/src/`, then add or repair the entry here.
