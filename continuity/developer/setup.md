# Setup and verification

Commands below are labelled **executed** (run during the 2026-10-02 Continuity initialization) or **documented** (taken from existing READMEs or derived from source, but not run in this session).

## Prerequisites

| Component | Requirement | Evidence |
| --- | --- | --- |
| Middleware | Python 3 with venv. The local `.venv` is Python **3.14.3**; no minimum version is declared. | `.venv/Scripts/python.exe --version` (executed) |
| Middleware packages | `fastapi`, `uvicorn[standard]`, `httpx`, `pydantic`, `pydantic-settings`, `websockets` | [requirements.txt](../../requirements.txt) |
| Web console | Python stdlib only, plus a browser. The browser loads Google Fonts and flagcdn.com. | [web/serve.py](../../web/serve.py), [developer/external-dependencies.md](external-dependencies.md#web-console-cdn-assets-debug-ui-only) |
| Firmware | PlatformIO (VS Code extension or `pio` CLI), the `espressif32` platform, a data-capable micro-USB cable | [hardware/platformio.ini](../../hardware/platformio.ini), [developer/hardware.md](hardware.md#prerequisites) |
| Firmware asset generators (optional) | Python with Pillow; network access to flagcdn.com for flags | [hardware/tools/gen_flags.py](../../hardware/tools/gen_flags.py), [hardware/tools/gen_fonts.py](../../hardware/tools/gen_fonts.py) |
| External services | OpenSky (required for AIR; works anonymously at lower limits), adsbdb (keyless), FlightAware AeroAPI (optional key), aisstream.io (key required for MARINE) | [Architecture → External systems](architecture.md#external-systems) |

On this machine, PlatformIO is installed at `~/.platformio/penv/Scripts/pio.exe` and is not on `PATH`. The firmware libraries (`TFT_eSPI`, `ArduinoJson`) are not yet installed under `hardware/.pio/`, so the first `pio run` will download them.

## Configuration

### Middleware: `.env`

[app/config.py](../../app/config.py) (`Settings`, pydantic-settings) reads `.env` from the **current working directory**, so start the middleware from the repository root. Environment variables override `.env`. Every key and its default is listed in [.env.example](../../.env.example), which maps 1:1 to `Settings` fields.

- **Secrets** (only in `.env`, which is gitignored; never record their values): `OPENSKY_CLIENT_ID`, `OPENSKY_CLIENT_SECRET`, `FLIGHTAWARE_API_KEY`, `AISSTREAM_API_KEY`.
- **Feature switches derived from those keys:**
  - OpenSky authenticates only when both OpenSky values are set; otherwise it runs anonymously.
  - FlightAware is enabled only when its key is non-empty.
  - Marine requires `AISSTREAM_ENABLED=true` **and** a key. Without both, the `/api/marine/*` endpoints return 503.
- **Paths are relative to the working directory:** `CACHE_PERSIST_PATH=data/route_cache.json` and `AIRCRAFT_DB_PATH=data/aircraftDatabase.csv`. Both files are gitignored.
- **Log level:** `LOG_LEVEL` (default `info`) sets both uvicorn and the app's own loggers; unknown names fall back to INFO (`app/main.py`).
- **Aircraft DB auto-download:** at startup the server re-downloads the roughly 95 MB CSV if it is missing or older than `AIRCRAFT_DB_MAX_AGE_DAYS` (30 by default). Set `AIRCRAFT_DB_AUTO_DOWNLOAD=false` to disable this.

The `MARINE_FALLBACK_*` keys shown in [developer/marine/external-dependencies.md](marine/external-dependencies.md#configuration-proposed-env-keys) are a **proposal**. `Settings` does not read them, and `extra="ignore"` silently drops them.

### Firmware: `hardware/include/config.h`

Copy [config.example.h](../../hardware/include/config.example.h) to `hardware/include/config.h`. That file is gitignored and holds the WiFi password. It needs:

- `WIFI_SSID` and `WIFI_PASSWORD`
- `MIDDLEWARE_BASE_URL`: the PC's LAN IP on port 8000, not `localhost`
- `HOME_LAT`, `HOME_LON`, and `RADIUS_MILES`
- `POLL_DEFAULT_SECONDS`, `POLL_MIN_SECONDS`, and `CYCLE_INTERVAL_MS`
- **`BRIGHTNESS` (0–255).** [src/main.cpp](../../hardware/src/main.cpp) (`loadSettings`) requires it, but **config.example.h does not define it**. Add it by hand, for example `#define BRIGHTNESS 200`; see [Troubleshooting](#troubleshooting).

At runtime, the device's SET screen stores user settings in ESP32 NVS (Preferences namespace `omniradar`, keys `cycle`, `bright`, `radius`, `poll`). Once a value is stored, it overrides the matching config.h default.

Display and touch pins live in [platformio.ini](../../hardware/platformio.ini) `build_flags` (TFT_eSPI is configured entirely through `-D` flags). The rest of the board pins and the touch calibration constants (`TS_RAW_*`) are in [board_pins.h](../../hardware/include/board_pins.h).

## Install, build, and run

All middleware commands run from the **repository root** in PowerShell.

1. Create the venv and install packages (documented):
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   Copy-Item .env.example .env   # then fill in keys
   ```
2. Optionally pre-fetch the aircraft DB (documented). The script writes to `data/aircraftDatabase.csv`, and `--url`/`--out` override the source and destination:
   ```powershell
   python scripts/download_aircraft_db.py
   ```
3. Run the middleware (documented). It binds to `HOST:PORT`, which defaults to `0.0.0.0:8000`. Interactive API docs are at `/docs`.
   ```powershell
   python -m app.main
   # or, with auto-reload:
   uvicorn app.main:app --reload
   ```
   First success: `GET http://localhost:8000/health` returns `"status": "ok"`. Stop the server with Ctrl+C. Shutdown persists the route cache to `CACHE_PERSIST_PATH`.
4. Run the web console from `web/` (documented):
   ```powershell
   cd web
   python serve.py                      # http://localhost:8080, proxies /api/* and /health -> :8000
   python serve.py --port 8080 --api http://192.168.1.50:8000
   ```
   `serve.py` reads the `PORT` and `MIDDLEWARE_URL` environment variables as defaults. It proxies GET and POST requests under `/api` (and GET `/health`).
5. Build and flash the firmware from `hardware/` (documented):
   ```powershell
   cd hardware
   pio run                       # compile
   pio run --target upload       # flash over USB (add --upload-port COM5 if needed)
   pio device monitor            # serial log @ 115200
   ```
6. Regenerate the firmware assets (documented; only when changing fonts or flags). These scripts overwrite `include/flags.h` and `include/fonts/*.h`; never hand-edit those files:
   ```powershell
   python hardware/tools/gen_flags.py
   python hardware/tools/gen_fonts.py
   ```

**Reset.** Deleting `data/route_cache.json` clears the route cache. Bumping `CACHE_VERSION` in [app/cache.py](../../app/cache.py) also discards it on the next load. `GET /api/metrics/reset` zeroes the session counters.

## Verify a change

**There is no automated test suite** and no lint or type-check configuration in the repository. Use these checks:

| Check | Command (repo root) | When | Status |
| --- | --- | --- | --- |
| Python syntax | `.venv/Scripts/python.exe -m compileall -q app scripts web` | Any Python change | Executed, passed |
| App wiring and imports (does not run lifespan, so no network) | `.venv/Scripts/python.exe -c "import app.main"` | Imports, routes, models | Executed, passed |
| Pure-function smoke test | Call `compute_bounding_box`, `StateVector.from_array`, `classify_type`, `_should_drop_plane`, `operator_class`, `country_from_mmsi`, `vessel_category`, `Metrics.recommended_poll_seconds` in a Python snippet | Geo, classification, filter, tables, poll logic | Executed ad hoc, passed |
| JS syntax | `node --check web/js/<file>.js` for each module | Web console change | Executed, all 10 passed |
| Live API | Run the middleware, then `GET /health`, `/api/nearby?lat=..&lon=..&radius=15`, `/api/metrics`, `/api/marine/<ch>/nearby` | Behavior changes. Costs OpenSky credits; marine needs a key. | Not executed |
| Console visual | Run `serve.py` and open `:8080`. Toggle MODE, ALT, and ACTION, and open the Usage tab. | UI changes | Not executed |
| Firmware compile | `pio run` in `hardware/` | Firmware changes. Compiles against your local `config.h`, so it does not prove config.example.h works. | Not executed (libraries not installed) |

**Before a live run:** starting the middleware triggers the aircraft DB staleness check. The local `data/aircraftDatabase.csv` is dated 2026-07-13, which is more than 30 days old, so the next start **will re-download it** unless `AIRCRAFT_DB_AUTO_DOWNLOAD=false`.

For payload changes, also check every consumer listed in [Data model → Change and compatibility constraints](../data/model.md#change-and-compatibility-constraints).

## Troubleshooting

| Symptom | Diagnosis | Remedy |
| --- | --- | --- |
| Firmware fails to compile with `'BRIGHTNESS' was not declared` | config.h was copied from config.example.h, which lacks `BRIGHTNESS` | Add `#define BRIGHTNESS 200` to config.h. The example file should be fixed; see [status](../status.md#known-defects). |
| `/api/marine/...` returns 503 `marine_disabled` | No `AISSTREAM_API_KEY`, or `AISSTREAM_ENABLED=false` | Set the key in `.env` and restart |
| `/api/nearby` returns 502 `upstream_unavailable` | OpenSky transport error, non-200 response, or 429 | Check `/api/metrics` → `external_calls.opensky` (credits and retry-after). Clients should keep their last data and retry. |
| Marine returns `[]` right after the first request | The channel just opened, and its store warms up from the stream | Wait seconds to minutes. The console retries once after 2.5 s. |
| Startup is slow, or a large download appears in the logs | Aircraft DB is missing or stale, so auto-download runs | Expected. Pre-fetch with the script, or disable auto-download. |
| Device: WiFi connects, but no data | `MIDDLEWARE_BASE_URL` is `localhost` or a wrong IP, or a firewall blocks it | Use the PC's LAN IP. Test `http://<PC-IP>:8000/api/nearby?radius=15` in a browser. |
| Device: white or blank screen; inverted or mirrored colors | Pin map or driver mismatch (ST7796 vs ILI9488), or rotation | See [developer/hardware.md → Troubleshooting](hardware.md#troubleshooting) |
| Device: taps land in the wrong place | Touch calibration | Read the serial `[touch] raw=` logs and tune `TS_RAW_*` in [board_pins.h](../../hardware/include/board_pins.h) |
