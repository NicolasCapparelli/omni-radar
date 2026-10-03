# Architecture

## System overview

```
                 poll (REST)                                   push (WebSocket)
OpenSky /states/all ─┐                                     ┌─ aisstream.io (1 socket per active channel)
adsbdb / FlightAware ─┤ (route lookups, cache-miss only)    │
offline aircraft DB ──┤                                     │
                      ▼                                     ▼
            ┌──────────────── app/ (FastAPI, one process) ────────────────┐
            │  AIR: geo → opensky → enrich (classify, filter, DB, route)  │
            │  MARINE: channels → aisstream → vessel_store → marine_enrich│
            │  shared: config, metrics, Throttle, background loops        │
            └───────────────┬─────────────────────────────┬───────────────┘
                 JSON over HTTP (+ X-Recommended-Poll-Seconds)
                            ▼                             ▼
                web/ console (browser via serve.py)   hardware/ ESP32 firmware (AIR only)
```

| Component | Responsibility | Entry point |
| --- | --- | --- |
| HTTP API and lifecycle | Endpoints, startup wiring, background loops, shutdown persistence | [app/main.py](../../app/main.py) (`lifespan`, `nearby`, `marine_nearby`, `marine_repoint`, `health`, `metrics`) |
| AIR live data | OAuth2 client credentials; one bounding-box `/states/all` call per request | [app/opensky.py](../../app/opensky.py) (`OpenSkyClient.get_states_in_box`, `StateVector`) |
| AIR enrichment | Classifies, filters grounded and slow planes, adds offline metadata, resolves routes, assembles payloads | [app/enrich.py](../../app/enrich.py) (`build_payloads`) |
| Route resolution | Ordered providers behind a persistent cache | [app/routes.py](../../app/routes.py), [app/adsbdb.py](../../app/adsbdb.py), [app/flightaware.py](../../app/flightaware.py), [app/cache.py](../../app/cache.py) |
| Offline AIR data | ICAO24 → type, model, registration, owner, and Doc 8643 class; callsign → airline, operator class, special flag | [app/aircraft_db.py](../../app/aircraft_db.py), [app/static_data.py](../../app/static_data.py) |
| MARINE ingest | Per-channel WebSocket subscription that merges messages into an MMSI-keyed store | [app/channels.py](../../app/channels.py), [app/aisstream.py](../../app/aisstream.py), [app/vessel_store.py](../../app/vessel_store.py) |
| MARINE enrichment | Box filter, moored and slow filter, offline code tables, payloads | [app/marine_enrich.py](../../app/marine_enrich.py), [app/marine_static_data.py](../../app/marine_static_data.py) |
| Web console | Static ES modules plus HTML partials; same-origin GET/POST proxy | [web/js/main.js](../../web/js/main.js), [web/serve.py](../../web/serve.py); detail in [developer/web-console.md](web-console.md) |
| Firmware | WiFi poll, filtered JSON parse, TFT rendering, touch buttons, NVS settings | [hardware/src/main.cpp](../../hardware/src/main.cpp) (`fetchNearby`, `renderAll`, `handleButton`, `loop`) |

AIR and MARINE are deliberately separated at the external surface: separate URL namespaces, payload models, metric groups, and docs. Internally they share `geo`, `metrics`, `config`, and the FastAPI app. The design is described in [DevGuide/MARINE/README.md](marine/overview.md#the-guiding-principle-mirror-air-separate-externally), whose "no marine code exists yet" status line is historical.

## Representative flows

### AIR request flow

`GET /api/nearby?lat&lon&radius`

1. [main.py](../../app/main.py) `nearby` fills in missing parameters from `HOME_LAT`, `HOME_LON`, and `DEFAULT_RADIUS_MILES`. [geo.py](../../app/geo.py) `compute_bounding_box` then builds a box using 69 mi per degree of latitude and `69 × cos(latitude)` mi per degree of longitude.
2. `OpenSkyClient.get_states_in_box` makes **one** call. It records `X-Rate-Limit-Remaining` and the retry-after value in metrics, and raises `OpenSkyError` on transport errors, 429, non-200 responses, invalid JSON, or a malformed token response. `main.py` maps that error to **502**. Vectors without a callsign or position are dropped.
3. `build_payloads` classifies every vector (`classify_type`: DB descriptor H/G/T/S/A first, then the OpenSky category, otherwise `Plane`). It then drops planes that are `on_ground` or at or below `PLANE_MIN_SPEED_MPH` (`_should_drop_plane`, when `FILTER_GROUNDED_PLANES=true`), before any route lookup.
4. For each surviving aircraft, run concurrently (`asyncio.gather`), `_resolve_metadata` returns a cached `FlightMeta` if one exists. Otherwise `resolve_route` tries the providers in order: adsbdb, then FlightAware (only if a key is set).
   - **found:** cached for 12 h.
   - **notfound:** offline airline only, negatively cached for 3 h.
   - **unavailable** (429, 5xx, network): offline airline only, **not cached and not retried in-line**.
5. `_build_payload` merges in the offline aircraft DB (model, registration, operator, owner) and the static tables (`operator_class`, `special_designation`). The response carries the `X-Recommended-Poll-Seconds` header from `Metrics.recommended_poll_seconds`.

Field semantics are in [data/model.md → AircraftPayload](../data/model.md#aircraftpayload).

### MARINE request flow

`GET /api/marine/{channel}/nearby`

1. `ChannelManager.snapshot(key, box)` opens the channel lazily if it is cold or its task has finished. Opening creates a `VesselStore` and an `AisStreamClient.run` task. The method resets the channel's idle clock and returns a store snapshot.
2. The ingest task subscribes with the API key, the box, and the message types. It merges position and static reports into the store per MMSI and reconnects with exponential backoff from 2 s up to 60 s.
3. `build_vessel_payloads` filters the snapshot to the **request** box. It then drops moored, anchored, aground, or slow vessels (always keeping SAR, law enforcement, pilot, and military) and maps the code tables. **There are zero external calls per request.**
4. The reaper loop (`run_reaper_loop`, every `MARINE_GC_INTERVAL_MS`) closes channels idle longer than `MARINE_CHANNEL_IDLE_TTL_MS` (8 h) and sweeps vessels silent for more than 15 min.

**Implementation limit:** a channel's subscription box is fixed by the request that **opened** it, or by `POST /api/marine/{channel}`. Later `nearby` requests on the same channel with a different centre or a larger radius filter the existing store, so the result covers only the overlap. `snapshot` returns `channel_box`, but `main.py` ignores it. The DevGuide's claim that the subscription is "sized to cover the channel's max radius" does not match the code.

### Clients

- **Web console:** `console.scan()` → `api.getNearby`/`getMarineNearby` → table, device emulator, and raw JSON. Live refresh uses `max(baseline, server recommendation, 5 s)`. See [developer/web-console.md](web-console.md#data-flow-of-a-scan); it predates marine support in the console.
- **Firmware:** in `loop()`, `fetchNearby()` runs every `max(cfg.pollSec, header, POLL_MIN_SECONDS)`. It parses with an ArduinoJson **filter** (only listed keys), keeps at most **60** targets, and auto-cycles through them every `cfg.cycleSec`. MARINE mode is a placeholder, and the firmware never calls `/api/marine`.

## External systems

| System | Used by | Failure behavior in source |
| --- | --- | --- |
| OpenSky `/states/all` plus the OAuth token endpoint | `opensky.py` | 502 to the client (also for invalid JSON or a malformed token response); client keeps its last data |
| adsbdb `/v0/callsign/{cs}` | `adsbdb.py` | 404 or empty route → notfound; 429/5xx/network or invalid JSON → unavailable |
| FlightAware AeroAPI `/flights/{ident}` | `flightaware.py` | Same taxonomy as adsbdb; disabled without a key |
| OpenSky aircraft DB CSV | `aircraft_db.py` at startup | Download errors are swallowed; the existing file is used, or enrichment runs without the DB |
| aisstream.io WebSocket | `aisstream.py` | Reconnect with backoff; requests keep serving the store |
| Google Fonts, flagcdn.com | Browser console only | Flags are skipped when no ISO code is present |
| flagcdn.com | `hardware/tools/gen_flags.py`, at asset-generation time only (`gen_fonts.py` uses the bundled TTFs) | — |

Credits, quotas, and licensing (including adsbdb's no-redistribution terms and the **unverified aisstream terms**) are documented in [developer/external-dependencies.md](external-dependencies.md) and [developer/marine/external-dependencies.md](marine/external-dependencies.md).

## Constraints and design reasoning

- **Minimize external calls (stated design goal).** Only positions and routes need the network. Everything else comes from the offline DB and tables, and routes are cached hard and persisted. Per [developer/air-architecture.md](air-architecture.md#how-it-all-adds-up), external usage scales with *new airborne callsigns*, not with aircraft count or poll rate. Source supports this mechanism. The quoted savings ("often 70–90%") are not verified here.
- **Never retry in-line.** Transient provider failures defer to the next client poll to avoid retry storms (`routes.resolve_route`, the provider clients). Each provider is wrapped in a `Throttle` (concurrency limit plus minimum spacing).
- **Clients pull; the middleware advises.** The middleware never polls OpenSky on its own. `Metrics.recommended_poll_seconds` doubles the interval below 1,000 credits, quadruples it below 200, and uses `retry-after` (or 60 s) at 0. Credit counts come from the latest response header. They are process-global, not per client. Marine always advertises `POLL_DEFAULT_SECONDS`.
- **Single process, in-memory state.** The route cache, vessel stores, channels, and metrics live in one process with `asyncio.Lock`s. Cache persistence is atomic (temp file plus replace), but there is no cross-process coordination, so running multiple workers would give each its own cache and metrics. Metrics reset on restart.
- **Startup cost.** The aircraft DB (about 95 MB CSV) is fully loaded into a dict at startup, off the event loop. Load time and memory were not measured.
- **Firmware memory.** The board has no PSRAM, so the JSON is parsed with a key filter and at most 60 targets are kept. The partition table is `huge_app.csv` (no OTA) to fit the font and flag assets.
- **The web console mirrors the hardware.** The firmware palette and layout are copied from `web/styles.css` and `web/js/device.js`. Comments in [main.cpp](../../hardware/src/main.cpp) reference those functions, so visual changes are expected to be made in both places.
- **Rationale not recorded:** why FlightAware's `aircraft_type` takes precedence over the DB typecode (see [data model → precedence](../data/model.md#precedence-and-derived-values)).

## Deeper context

- [Data model](../data/model.md) covers payload fields, units, absence values, and consumers.
- [Implementation map](../agent/map.md) has request-oriented routes.
- The migrated narrative docs (originally `DevGuide/`): [developer/air-architecture.md](air-architecture.md) (the AIR walkthrough is accurate apart from the drift noted in status), [developer/marine/architecture.md](marine/architecture.md) (written as a pre-implementation design), and [developer/web-console.md](web-console.md).
