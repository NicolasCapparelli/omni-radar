# Omni-Radar (Local Traffic Radar)

Self-hosted middleware, web debug console, and ESP32 device firmware that track nearby aircraft (OpenSky, adsbdb, FlightAware) and vessels (aisstream.io AIS).

```
[OpenSky / aisstream.io] + [offline DBs] ──▶ (FastAPI middleware) ──▶ [JSON] ──▶ [ESP32 device / web console]
```

Project documentation lives in [continuity/](continuity/README.md):

- [Setup and run](continuity/developer/setup.md): install, configure `.env`, run the middleware, console, and firmware
- [API reference and caching behavior](continuity/user/api.md)
- [Architecture](continuity/developer/architecture.md) and [data model](continuity/data/model.md)
- [Current status](continuity/status.md)

Quick start (from the repository root):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env   # then fill in your credentials
python -m app.main            # API on :8000
```
