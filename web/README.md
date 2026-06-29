# Omni-Radar Web Console

A standalone developer console for the Local Traffic Radar middleware, plus a
faithful emulator of the 2.8" ESP32 hardware screen. It is fully decoupled from
the API (`app/`) — it only talks to the middleware over HTTP.

## What it does
- **Test console** (right): set lat/lon/radius, hit `SCAN` → `GET /api/nearby`,
  and browse every returned aircraft in a dense table (type, model, operator,
  route, altitude, speed, vertical-speed, operator-class, special flags).
- **Device emulator** (left): renders the selected aircraft exactly as the
  320×240 hardware LCD will, with the three physical buttons:
  - **POWER** — sleep/wake the screen.
  - **MODE** — toggle AIR / MARINE (cosmetic; mirrors the firmware's reserved mode).
  - **ACTION** — toggle Auto-Cycle ↔ Manual-Lock; while locked, step to the next target.
- Auto-cycle advances every 5s (like the hardware). Clicking a table row locks
  and selects. `Auto-refresh 30s` re-polls the API on the device's cadence.
- A raw-JSON panel shows the full payload for the selected aircraft.

## Run

1. Start the middleware (from the project root):
   ```powershell
   python -m app.main          # serves the API on :8000
   ```
2. Start this console (from the `web/` folder):
   ```powershell
   python serve.py             # serves the UI on :8080, proxies /api + /health -> :8000
   ```
3. Open http://localhost:8080

The console's static server reverse-proxies `/api/*` and `/health` to the
middleware, so the browser uses a single origin and no CORS changes are needed.

Point it at a different middleware host with:
```powershell
python serve.py --port 8080 --api http://192.168.1.50:8000
```

## Files
- `index.html` — layout
- `styles.css` — cream/gold chrome + dark green-phosphor LCD theme
- `app.js` — fetch, table, device rendering, button behavior
- `serve.py` — static server + API proxy (stdlib only, no dependencies)
