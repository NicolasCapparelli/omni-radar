# Console screenshot notes

Captured on 2026-10-14 in the Codex in-app browser after explicit permission. These are unedited screenshots of the repository's real web console, not generated mockups or photographs of the ESP32.

- `air-console.jpg`: AIR target card, route, telemetry, and selected result.
- `marine-console.jpg`: MARINE vessel card and AIS result table. The normal browser viewport clips the right edge of the wide marine console.

The preview used a temporary Python standard-library server serving the existing `web/` files and synthetic API responses. Aircraft records passed through `StateVector` parsing and the real AIR endpoint/enrichment; a synthetic route was seeded into an isolated cache. Vessel records passed through `VesselStore` position/static merging and marine enrichment. Names and identifiers in these captures are synthetic; coordinates are the public defaults from the repository, not a user's private location.

The preview did not load `.env`, the owner's aircraft database, or the persisted route cache. Provider credentials were blank, live providers were not called, and database auto-download was disabled. The app's existing font/icon and flag assets were loaded by the browser. The preview harness was temporary and is not a built-in demo mode or a reproducible checked-in screenshot workflow.

To capture new screens, run the console as described in the root [README](../../README.md#install-and-run), use approved synthetic fixtures or carefully reviewed public data, and verify that the entire captured area contains no credentials, private locations, or account details. Browser/computer control requires the user's explicit permission under the task's instructions. Do not substitute fabricated screenshots for a failed local run.
