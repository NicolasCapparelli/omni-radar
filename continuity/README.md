# Omni-Radar (Local Traffic Radar)

## Purpose and audience

Omni-Radar is a self-hosted "what's moving near me" tracker. It has three parts:

- **Middleware** ([app/](../app/)) is a FastAPI service. It turns one bulk OpenSky Network poll into descriptive, unit-bearing aircraft records (`GET /api/nearby`) and turns aisstream.io AIS WebSocket feeds into vessel records (`GET /api/marine/{channel}/nearby`). It does most of the enrichment offline so that external API usage stays small.
- **Web console** ([web/](../web/)) is a no-build developer console. It calls the API and emulates the device's LCD in a browser.
- **Device firmware** ([hardware/](../hardware/)) runs on an ESP32-3248S035 3.5" touch display. It polls the middleware over WiFi and shows the tracked aircraft.

The audience, observed from the repository, is a single developer/owner who runs the middleware on a LAN PC and the device at home. The repository does not say whether wider distribution is intended.

## Scope and maturity

The most recent commit is labelled `V1 Release`, and `app.__version__` is `1.0.0`. As implemented in source:

- **AIR (aircraft):** middleware, console, and device data card plus radar view are implemented.
- **MARINE (vessels):** middleware endpoints and console are implemented. On the device, MARINE mode is a "coming soon" placeholder.
- **Planned, not implemented:** a paid marine gap-fill provider (described in [developer/marine/external-dependencies.md](developer/marine/external-dependencies.md)) and device MARINE mode.
- **Not present:** an automated test suite.

For known defects, documentation drift, and the current stopping point, see [status](status.md).

## Find what you need

| Task | Start here |
| --- | --- |
| Understand this documentation framework | [What is Continuity?](about.md) |
| Install, configure, run, flash, or check a change | [Setup](developer/setup.md) |
| Understand components and flows | [Architecture](developer/architecture.md) |
| Understand payload fields, units, and absence values | [Data model](data/model.md) |
| Resume work after an absence | [Status](status.md) |
| Locate implementation context | [Agent map](agent/map.md) |
| Work as an agent | [Reading and maintenance contract](agent/instructions.md) |
| External service limits, credits, and licensing (AIR) | [developer/external-dependencies.md](developer/external-dependencies.md) |
| External services and planned config (MARINE) | [developer/marine/external-dependencies.md](developer/marine/external-dependencies.md) |
| API endpoints, example JSON, caching and rate-limit behavior | [API reference](user/api.md) |
| Web console usage | [Web console](user/web-console.md) |
| Web console module structure | [Developer: web console](developer/web-console.md) |
| Device firmware: pins, build, flash | [Hardware](developer/hardware.md) |
| AIR middleware walkthrough | [AIR architecture](developer/air-architecture.md) |
| MARINE design | [Marine overview](developer/marine/overview.md), [marine architecture](developer/marine/architecture.md) |

The former root README, `DevGuide/`, `web/README.md`, and `hardware/README.md` were migrated into this directory on 2026-10-02 (record: [migration evidence](history/migration/migration.md)); the repository-root [README.md](../README.md) is now a short landing page. The migrated documents keep their original text with a relocation note. Where they disagree with source, [status → Documentation drift](status.md#documentation-drift) lists the differences, and source wins for current behavior.
