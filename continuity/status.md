# Status

## Current state

Upstream commits `e03563b`..`2f1a246` (2026-10-02, pushed by another contributor) landed before this documentation was pushed. They changed the AIR bounding box to scale longitude by `cos(latitude)`, made `serve.py` proxy POST, ignored AIS "not available" values, switched the military ICAO24 check to the range `ADF7C8`–`AFFFFF`, kept the selected target across refreshes (console and firmware), dropped console scans that finish after a MODE toggle, treated malformed upstream JSON as transient, and applied `LOG_LEVEL` to app loggers. The Continuity docs were updated to match by reading the diffs. None of it was run.

The code is at commit `3d6a6fc` ("V1 Release", 2026-07-22) on `master`. Before this initialization, the working tree had no source changes. Everything below comes from **reading the source**. No live run, device flash, or firmware compile happened in this session; see [Last verified state](#last-verified-state).

| Area | State (from source) |
| --- | --- |
| AIR middleware (`/api/nearby`, `/health`, `/api/metrics`) | Implemented |
| MARINE middleware (`/api/marine/{channel}/nearby`, `POST /api/marine/{channel}`) | Implemented. Needs `AISSTREAM_API_KEY`. |
| Web console (AIR, MARINE, radar, Usage tab) | Implemented |
| Firmware AIR card, radar view, touch buttons, settings (NVS) | Implemented |
| Firmware MARINE mode | Placeholder ("coming soon") |
| Paid marine fallback (`marinetraffic.py`, `MARINE_FALLBACK_*`) | Planned in [the marine docs](developer/marine/external-dependencies.md) only; not implemented |
| Automated tests, lint, CI | None |

### Known defects

These were found by reading source and have not been reproduced at runtime.

1. **`BRIGHTNESS` is missing from `hardware/include/config.example.h`.** `loadSettings` in `hardware/src/main.cpp` uses it, so a firmware build from a freshly copied example config will fail. The local, gitignored `config.h` does define it.
2. **FlightAware routes have no airport country.** `app/flightaware.py` never sets `origin_country` or `destination_country`, so those flights show no flags in the console or on the device for the 12-hour cache life.
3. **`model_code` precedence differs from the docs.** A FlightAware `aircraft_type` overrides the offline DB typecode (`app/enrich.py` `_build_payload`), but the former root README (now [user/api.md](user/api.md)) says the DB wins. It is unknown which behavior is intended.
4. **A marine channel ignores later changes of centre or radius.** The channel's box is fixed by the request that opened it, so later requests filter only the overlap and the returned `channel_box` goes unused. See [architecture → MARINE request flow](developer/architecture.md#marine-request-flow).
5. **Minor metric quirks.** The `marine.channels_active` gauge stays null until the first reaper pass (5 minutes), and `ais.ws_connected` is a single gauge shared by all channels.

### Documentation drift

The former `DevGuide/` and README documents were migrated into `continuity/` with their text unchanged and a relocation note. Where they disagree with the code, the code describes current behavior:

- [Marine overview](developer/marine/overview.md) (was `DevGuide/MARINE/README.md`) says "design / planning … No marine code exists yet", but marine is implemented. [developer/marine/architecture.md](developer/marine/architecture.md) describes the `POST` repoint as taking a JSON body, but the code takes query parameters. It also says the subscription box is "sized to the channel's max radius", which is false (defect 4).
- [Web console guide](user/web-console.md) (was `web/README.md`) calls MODE "cosmetic", but the console does marine scans. [developer/web-console.md](developer/web-console.md) doesn't mention marine at all.
- [Hardware guide](developer/hardware.md) (was `hardware/README.md`) lists the radar view and touch buttons as TODO, but both are implemented, along with a fifth button (SET) and an NVS settings screen. Its pin table says touch is on a separate SPI bus, but `platformio.ini` and `board_pins.h` say the bus is shared.
- The former root README ([user/api.md](user/api.md)) gets the model precedence wrong (defect 3). Its endpoint list leaves out the marine endpoints, and its example payload has no `latitude`/`longitude`.
- Some source comments are stale too; see [map → Investigation notes](agent/map.md#investigation-notes).

## Active work and last stopping point

- **Product work:** nothing is in progress. The last commit, "V1 Release", added MARINE to the middleware and console, plus the first firmware. Git history doesn't show where the owner meant to go next. The firmware header and hardware README describe MARINE as "next", but nobody has confirmed that as the next task.
- **This session (2026-10-02):** Continuity was initialized. Its eight documents are filled in, root `AGENTS.md` and `CLAUDE.md` now point here, and the checks and routing walkthroughs are done. Evidence is in [history/documentation/initialization.md](history/documentation/initialization.md).
- **Documentation migration (2026-10-02, owner chose full migration):** the former root README, `DevGuide/` (7 files), `web/README.md`, and `hardware/README.md` moved into `continuity/developer/` and `continuity/user/`, and the originals were removed. The root `README.md` is now a short landing page, which is the one required public entry point. Two source comments were repointed. Per-file record and recovery location: [history/migration/migration.md](history/migration/migration.md).
- **Uncommitted:** nothing is committed. The new and changed files are untracked or modified in the working tree; the removed originals are recoverable from commit `3d6a6fc`.

## Next steps and context

No next product task has been chosen. Candidates that come from the evidence, in no agreed order:

- Fix defect 1 by adding `BRIGHTNESS` to `config.example.h`. This is a small, obvious fix.
- Decide whether FlightAware routes should carry airport countries (defect 2) and which `model_code` precedence is intended (defect 3).
- Device MARINE mode ([map → Device firmware](agent/map.md#device-firmware)). This is labelled "next" in the firmware but not confirmed.
- Reconcile the migrated docs with the code (they keep their original text, so the drift listed above still applies).

**Before a live run:** `data/aircraftDatabase.csv` is dated 2026-07-13. That is older than `AIRCRAFT_DB_MAX_AGE_DAYS=30`, so the next middleware start will re-download about 95 MB unless auto-download is turned off.

## Blockers and open questions

- **Migration:** see the stopping point above; no blockers.
- **Future product work:**
  - aisstream.io terms of use are unverified. The marine docs mark this TODO "before shipping".
  - Is the FlightAware-over-DB `model_code` precedence intentional?
  - Should marine requests re-point a channel or reject a mismatched box?

## Last verified state

The checks ran on **2026-10-02** against `3d6a6fc`, plus the untracked Continuity documentation (`continuity/`, `AGENTS.md`, `CLAUDE.md`). No source files were changed.

| Check | Result |
| --- | --- |
| `.venv/Scripts/python.exe -m compileall -q app scripts web` | Passed |
| `python -c "import app.main"` (route table built; lifespan not run) | Passed: 5 `/api/*` routes plus `/health` (and FastAPI's docs routes) |
| Ad hoc smoke test of the pure functions (geo box, `StateVector` units, `classify_type`, `_should_drop_plane`, `operator_class`, `country_from_mmsi`, `vessel_category`, `recommended_poll_seconds`) | Passed. Outputs matched what the code says it should do. |
| `node --check` on the 10 `web/js/*.js` modules | Passed |
| Live middleware or console run, `pio run`, flash | **Not run**: no external calls wanted, it would trigger the DB download, and the firmware libraries aren't installed |

After rebasing onto the upstream commits, `compileall`, `import app.main`, `node --check` on all modules, and a two-line smoke test (longitude span 0.574° at 40.758° N for 15 mi; `ADF7C7` not military, `ADF7C8` military) were rerun and passed. The rest of the table above was run before the rebase, against `3d6a6fc`.

The documentation checks (links, anchors, source paths, three routing walkthroughs) passed after initialization and again after migration. See [initialization evidence](history/documentation/initialization.md) and [migration evidence](history/migration/migration.md).

## Last meaningful update

2026-10-02: Continuity initialized, then existing documentation fully migrated.
