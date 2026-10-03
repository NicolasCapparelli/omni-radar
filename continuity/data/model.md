# Data model

## Overview and schema routes

There is no database. The model consists of **outbound JSON payloads** (the contract with the console and firmware), **in-memory state** (route cache, vessel stores, channels, metrics), **one persisted file** (the route cache), **one offline dataset** (the aircraft DB CSV), and **configuration**.

| Concept | Meaning | Authoritative definition | Producer | Consumers |
| --- | --- | --- | --- | --- |
| `AircraftPayload` | One tracked aircraft, as returned by `/api/nearby` | [app/models.py](../../app/models.py) | [enrich.py](../../app/enrich.py) `_build_payload` | [web/js/table.js](../../web/js/table.js), [web/js/device.js](../../web/js/device.js), [hardware/src/main.cpp](../../hardware/src/main.cpp) `buildFilter`/`copyAircraft` |
| `VesselPayload` | One tracked vessel, as returned by `/api/marine/{channel}/nearby` | [app/models.py](../../app/models.py) | [marine_enrich.py](../../app/marine_enrich.py) `_build_payload` | `table.js` `vesselRowHtml`, `device.js` `renderVesselCard` (the firmware does not consume it) |
| `StateVector` | Typed OpenSky state vector plus unit conversions | [app/opensky.py](../../app/opensky.py) | `StateVector.from_array` | `enrich.py` |
| `FlightMeta` | Route plus airline for one callsign; the cache value | [app/cache.py](../../app/cache.py) | `adsbdb.py`, `flightaware.py`, `enrich._offline_meta` | `enrich._build_payload` |
| Route cache file | Persisted `FlightMeta` entries with expiry | `MetadataCache.save` and `load` in [cache.py](../../app/cache.py) (`CACHE_VERSION = 2`) | GC loop, shutdown | Startup |
| `AircraftRecord` | Offline airframe metadata keyed by ICAO24 | [app/aircraft_db.py](../../app/aircraft_db.py) | `AircraftDatabase.load` (CSV) | `enrich.py` |
| `VesselState` | Merged latest AIS state per MMSI | [app/vessel_store.py](../../app/vessel_store.py) | `aisstream.py` `_handle_message` | `marine_enrich.py` |
| `Channel` | Monitored marine area: box, store, task, idle clock | [app/channels.py](../../app/channels.py) | `ChannelManager._open` | `main.py`, `/health`, `/api/metrics` |
| Metrics snapshot | Session counters and gauges | [app/metrics.py](../../app/metrics.py) `Metrics.snapshot` | Calls throughout `app/` | [web/js/usage.js](../../web/js/usage.js) |
| `/health` body | Integration flags, cache size, DB size, marine stats | [app/main.py](../../app/main.py) `health` | — | [web/js/status.js](../../web/js/status.js) |
| `Settings` | Middleware configuration | [app/config.py](../../app/config.py), [.env.example](../../.env.example) | `.env` and environment | `main.py` `lifespan` |
| Device config and NVS | Firmware compile-time config and runtime settings | [config.example.h](../../hardware/include/config.example.h), `Settings`/`loadSettings` in [main.cpp](../../hardware/src/main.cpp) | User or SET screen | Firmware |
| Static tables | Airline designators, special operators, military ICAO24 blocks, AIS type, nav status, MID → ISO → country | [app/static_data.py](../../app/static_data.py), [app/marine_static_data.py](../../app/marine_static_data.py) | Code (seed data) | Enrichment |

There are no validators or migrations beyond pydantic response models, `Query`/`Path` constraints in `main.py`, and `CACHE_VERSION`.

## Entities, relationships, and lifecycles

### AircraftPayload

- **Identity:** there is no stable ID in the payload. `callsign` identifies a flight and is the route-cache key. The ICAO24 address is used internally but **not exposed**. Each response is a fresh list. Clients select targets by array index, so selection can shift between polls.
- **Lifecycle:** built per request. An aircraft appears only if OpenSky returned it with a callsign and position, inside the box, and it survived the plane filter. The **box is a rectangle, not a circle**, so corners reach about 1.4× the radius.

### Route cache entry (FlightMeta)

- Keyed by callsign; one entry per callsign.
- **found:** TTL `ROUTE_CACHE_TTL_MS` (12 h).
- **notfound:** an offline-airline-only meta with TTL `ROUTE_NEGATIVE_TTL_MS` (3 h).
- **Transient failures** are never stored.
- Expired entries are evicted lazily on `get` and by the GC sweep every `GC_INTERVAL_MS`. The GC also saves the cache, and so does shutdown.
- **Callsign reuse:** a callsign reused for a different route within 12 h keeps serving the cached route. This is inherent in callsign keying.

### VesselState, Channel

- **One `VesselStore` per channel**, keyed by integer MMSI. The same vessel can exist in several channels independently.
- **Merge rules:**
  - Position reports update only non-null fields.
  - Static reports update only truthy fields.
  - The metadata `ShipName` fills `name` only if it is empty. A static report's name always overwrites it.
  - `last_update_ms` refreshes on any message.
- Vessels silent longer than `MARINE_VESSEL_TTL_MS` (15 min) are hidden from snapshots immediately and removed by the reaper sweep.
- **Channel keys:** 1–32 characters `[A-Za-z0-9_-]`, chosen by the caller. A channel is created on its first `nearby` request or `POST`. It is re-created if its task has finished. It is destroyed when idle longer than 8 h (checked every 5 min), by `POST` repoint (the store is discarded), or at shutdown.

## Representations and conversion boundaries

### Units and conversions (AIR)

The conversions live in `StateVector` in [opensky.py](../../app/opensky.py):

| Field | Conversion | Rounding |
| --- | --- | --- |
| `altitude_feet` | Barometric metres × 3.28084 | Integer |
| `speed_knots` | Ground speed m/s × 1.943844 | Integer |
| `vertical_speed_fpm` | m/s × 196.850394 | Integer |
| `heading_degrees` | True track | Rounded, mod 360 |

The plane speed gate compares raw m/s against `PLANE_MIN_SPEED_MPH × 0.44704`.

**Geo:** the AIR and MARINE boxes use 69 mi per degree of latitude and a **fixed** 53 mi per degree of longitude, clamped to valid lat/lon ranges. Boxes crossing the antimeridian are not handled.

### Absence semantics

Absent values become sentinels, not nulls. Consumers must treat these as "unknown":

| Value | Meaning |
| --- | --- |
| `"Unknown"` | `model_code`, `model_name`, `registration`, `operator`, `owner`, `operator_class`; AIR `country`; vessel `name`, `imo_number`, `vessel_type`, `nav_status`, `country` |
| `"Unknown Airline"` | AIR `airline` |
| `"N/A"` | `origin`, `destination` (AIR and vessel) |
| `"Unknown Route"` | `origin_name`, `destination_name` |
| `""` | `origin_country`, `destination_country`, `squawk`, vessel `callsign`, `eta`, `country_iso` |
| `"None"` (string) | `emergency`, `special_designation` |
| `0` | Ambiguous: a null altitude, speed, vertical rate, or heading becomes `0`, which looks the same as a real zero. Vessel `heading_degrees` ≥ 360 (AIS 511 = not available) also becomes `0`. |
| `null` | Only `latitude` and `longitude`, and never null for AIR because vectors without a position are dropped |

### Precedence and derived values

- **`model_code`:** `FlightMeta.model` from the route provider is used **unless it is `"Unknown"`**, in which case the DB typecode applies. adsbdb always sends `"Unknown"`, so for adsbdb routes the DB wins. A FlightAware `aircraft_type` **overrides** the DB typecode. This contradicts the root README, which says a provider type is used "only if the DB has none". Whether that precedence is intended is unknown.
- **`model_name`, `registration`, `owner`:** come only from the DB.
- **`operator`:** DB operator, otherwise `airline` if that is not `"Unknown Airline"`, otherwise `"Unknown"`.
- **`airline`:** offline table by callsign prefix, otherwise the provider's airline name, otherwise `"Unknown Airline"`.
- **`origin_country` and `destination_country`:** ISO alpha-2 codes **set only by adsbdb** (`country_iso_name`). FlightAware-resolved routes leave them `""`, so those flights show no flags on the console or device for the 12 h cache life.
- **`operator_class`:**
  1. A special designation of Military, Police or Medical, or Cargo (prefix or table) → that class (Police and Medical → Government).
  2. Otherwise, an airline-table prefix → Commercial.
  3. Otherwise, a registration-looking callsign → Private.
  4. Otherwise, a resolved airline → Commercial.
  5. Otherwise → Unknown.

  Adding a designator to `AIRLINE_BY_ICAO` therefore also makes its flights Commercial.
- **`special_designation`:** callsign prefix table, then regex patterns (for example `N\d+PD` → Police), then military ICAO24 blocks (`ae`, `adf`).
- **`vehicle_type`:** DB Doc 8643 class H/G/T/S/A beats the OpenSky category, which beats the default `Plane`. Without the DB, rotorcraft that do not broadcast category 8 are labelled `Plane` and become subject to the speed filter.
- **AIR `country`:** OpenSky's `origin_country`, which is the ICAO24 registration country. It is a country *name*, not ISO.
- **Vessel `country` and `country_iso`:** from the MMSI's first three digits (MID).
- **Vessel `eta`:** `MM-DD HH:MM` with no year. Timezone: AIS ETAs are UTC by convention. That is an inference; the code does not convert.

### Firmware representation

The ESP32 `Aircraft` struct keeps a **subset** of fields, chosen by `buildFilter`'s key list. It prefers `operator` and falls back to `airline`, and stores at most 60 targets. Fields missing from the JSON silently take the defaults in `copyAircraft`.

## Change and compatibility constraints

- **Payload field names are a cross-repository contract with no versioning.** Renaming or removing an `AircraftPayload` field requires updating, together:
  - [table.js](../../web/js/table.js) `rowHtml`
  - [device.js](../../web/js/device.js) `renderAircraftCard`/`renderRadar`
  - the firmware's `buildFilter` keys and `copyAircraft` in [main.cpp](../../hardware/src/main.cpp), followed by a reflash

  The firmware degrades silently to defaults rather than failing. Sentinel strings such as `"Unknown"`, `"None"`, and `"N/A"` are compared literally in the firmware and the JS.
- **Persisted cache shape:** changing `FlightMeta` fields requires bumping `CACHE_VERSION` in [cache.py](../../app/cache.py). Otherwise `FlightMeta(**item)` raises `TypeError` and every entry from the old file is silently skipped (when a field was removed), or old entries load with default values for new fields.
- **Metrics keys:** [usage.js](../../web/js/usage.js) reads the nested `Metrics.snapshot()` structure, so review both together.
- **Configuration:** every new `Settings` field should be added to [.env.example](../../.env.example). Unknown env keys are silently ignored (`extra="ignore"`).
- **Aircraft DB CSV:** column names are read tolerantly (`typecode`/`icaoaircrafttype`, `manufacturericao`/`manufacturername`). Rows without a type code are skipped entirely, which also drops their registration and owner.
- **Static tables** are described in source as extendable seed data. See [map → Offline lookup tables](../agent/map.md#offline-lookup-tables) for the effects of changing them.
