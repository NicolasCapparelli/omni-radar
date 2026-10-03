# Continuity initialization evidence (2026-10-02)

> *Historical record. After this initialization the owner chose full migration (see [migration evidence](../migration/migration.md)): the human docs named below as "kept" or "retained" were later moved into `continuity/`, and the root README became a landing page.*

This is optional evidence. The current state and open work are in [status](../../status.md).

## Inventory

- **Tracked files:** 62 at `3d6a6fc`.
  - `app/`: 19 Python modules.
  - `web/`: 10 JS modules, 3 partials, `index.html`, `styles.css`, `serve.py`, and a README.
  - `hardware/`: `main.cpp`, `platformio.ini`, 2 hand-written headers (`board_pins.h`, `config.example.h`), generated headers (`flags.h` and 3 fonts), 2 generator scripts, 2 TTFs, `.gitignore`, and a README. The local `config.h` is gitignored.
  - `scripts/`: 1 script.
  - Docs: root `README.md`, 7 `DevGuide/**` files, `web/README.md`, `hardware/README.md`.
- **Inspected in full:** all `app/` modules except the bulk data rows of the two static-table modules; `web/js/api.js`, `state.js`, `main.js`, `console.js`, and `serve.py`; the parts of `hardware/src/main.cpp` covering the model, settings, fetch, render dispatch, radar, input, and loop; and all docs and config templates.
- **Exports and signatures only:** `web/js/device.js`, `table.js`, `usage.js`, `format.js`, `status.js`.
- **Excluded:** `.venv/`, `hardware/.pio/`, `__pycache__/`, `data/`, the TTFs, and the generated headers. `.env` and `hardware/include/config.h` were accessed only through targeted greps for non-secret keys: the `.env` key names, the two `AIRCRAFT_DB_*` values, and `BRIGHTNESS`. No secret values were read or recorded.
- **Coverage:** the [map](../../agent/map.md) has 11 capability routes and 7 shared foundations.

## Discovery files

| File | Role | Action |
| --- | --- | --- |
| `AGENTS.md` (root) | Generic agent entry point | Created with the Continuity block. No file existed before. |
| `CLAUDE.md` (root) | Claude Code entry point. This session ran in Claude Code. | Created. It imports `AGENTS.md`. |
| `.github/copilot-instructions.md`, `GEMINI.md`, `.cursor/`, and other tool rule files | — | None existed. None were added, to avoid unused integrations. |
| `README.md`, `DevGuide/**`, `web/README.md`, `hardware/README.md` | Human developer docs, not agent entry points | Kept unchanged. Continuity links to them. Their drift is recorded in [status](../../status.md#documentation-drift). |

No locked specifications or externally consumed agent guides exist. The source mentions a "middleware spec" (for example, in the `geo.py` docstring), but the spec is not in the repository.

## Checks

The verification commands and their results are in [status → Last verified state](../../status.md#last-verified-state). Link and anchor checking used a script that resolves every relative link in `continuity/**/*.md`, `AGENTS.md`, and `CLAUDE.md`, and checks `#anchors` against GitHub-style heading slugs in the target file. The source paths named in the map were checked for existence with the same script. Result: all resolved.

## Routing walkthroughs

| Request | Map entry chosen | Next read (exact) | Verification route | Outcome and repair |
| --- | --- | --- | --- | --- |
| "Picking this back up after a few months. How do I get the screen showing flights again?" (setup and resumption; different wording from the area names) | [Setup and resumption](../../agent/map.md#setup-and-resumption) | [status → Known defects](../../status.md#known-defects), [setup → Configuration](../../developer/setup.md#configuration), `hardware/include/config.example.h`, `app/main.py` `lifespan` | `GET /health` on `:8000`; then `pio run`, `pio run --target upload`, `pio device monitor` in `hardware/` | Found the missing `BRIGHTNESS` (a compile blocker) and the DB re-download on next start before either could cause trouble. Repair: added the "screen shows nothing" wording and a direct link to setup troubleshooting from the route. |
| "Add Breeze Airways (MXY) so its flights show a proper airline name." (local feature change) | [Offline lookup tables](../../agent/map.md#offline-lookup-tables) | `app/static_data.py` `AIRLINE_BY_ICAO`, then `airline_from_callsign` (used by `adsbdb.py`, `flightaware.py`, and `enrich._offline_meta`) and `operator_class` | Smoke-test `airline_from_callsign("MXY123")` and `operator_class("MXY123")`; then a live `/api/nearby` | The route reached the right table. Following callers showed that the airline name is stored in cached `FlightMeta`, so cached callsigns keep the old name for up to 12 h, across restarts. Repair: added this cache effect, and how to clear it, to the map entry. |
| "The device shows a route but no flags for some flights." (bug crossing a feature and a shared subsystem) | [Payload contract](../../agent/map.md#payload-contract), then [Route resolution and cache](../../agent/map.md#route-resolution-and-cache) | `hardware/src/main.cpp` `flagFor`/`copyAircraft` (an empty ISO code means no flag), then `app/flightaware.py` `FlightAwareClient.fetch_route` (does not set `origin_country` or `destination_country`), compared with `app/adsbdb.py` `_airport_country` | Find a FlightAware-resolved callsign in `data/route_cache.json`; live `/api/nearby` with a FlightAware key; the console shows the same symptom | Root cause located: the FlightAware parser omits countries, and the result is cached for 12 h. Repair: added the "missing a flag" wording to the payload-contract entry, and recorded the gap in the route entry, the data model, and status (defect 2). |

## Completion checklist

- [x] The eight durable docs are filled in. `about.md` was kept, with the adoption line added. `agent/instructions.md` was kept unchanged; no project-specific adjustments were needed beyond the exclusions in the map.
- [x] The discovery files and their roles are accounted for (table above).
- [x] Retained authority and unknowns are explained: existing docs are kept with drift recorded, and unknown intent is labelled in status and the data model.
- [x] Links, anchors, and source paths were checked.
- [x] All three routing walkthroughs are complete.
- [x] Runtime checks that ran and that were skipped are labelled (status).
- [x] Cleanup references checked: `initialize.md` was removed, and no populated doc links to it. `migrate.md` is kept until the user's migration decision.
