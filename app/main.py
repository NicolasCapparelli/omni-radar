"""FastAPI application: the Local Traffic Radar middleware proxy.

Exposes ``GET /api/nearby`` for the ESP32 hardware tracker. Aggregates live
state vectors from OpenSky, enriches them via FlightAware (cached), and returns
the optimized short-key JSON payload.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, Response
from fastapi.responses import JSONResponse

from . import __version__
from .adsbdb import AdsbdbClient
from .aircraft_db import AircraftDatabase, ensure_database
from .cache import MetadataCache, run_gc_loop
from .config import get_settings
from .enrich import build_payloads
from .flightaware import FlightAwareClient
from .geo import compute_bounding_box
from .metrics import METRICS
from .models import AircraftPayload
from .opensky import OpenSkyClient, OpenSkyError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("traffic_radar")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Wire up clients, cache, and the background GC loop for the app lifetime."""
    settings = get_settings()

    app.state.settings = settings
    app.state.cache = MetadataCache(
        default_ttl_ms=settings.route_cache_ttl_ms,
        persist_path=settings.cache_persist_path,
    )
    await asyncio.to_thread(app.state.cache.load)
    app.state.opensky = OpenSkyClient(
        client_id=settings.opensky_client_id,
        client_secret=settings.opensky_client_secret,
    )
    # Route providers, in priority order: adsbdb (free) then FlightAware (fallback).
    app.state.adsbdb = AdsbdbClient(
        base_url=settings.adsbdb_base_url,
        enabled=settings.adsbdb_enabled,
        max_concurrency=settings.adsbdb_max_concurrency,
        min_interval_ms=settings.adsbdb_min_interval_ms,
    )
    app.state.flightaware = FlightAwareClient(
        api_key=settings.flightaware_api_key,
        base_url=settings.flightaware_base_url,
        max_concurrency=settings.flightaware_max_concurrency,
        min_interval_ms=settings.flightaware_min_interval_ms,
    )
    app.state.route_providers = [app.state.adsbdb, app.state.flightaware]

    # Load the offline aircraft DB off the event loop (large CSV, blocking I/O).
    # Auto-download first if it's missing or stale.
    if settings.aircraft_db_auto_download:
        await asyncio.to_thread(
            ensure_database,
            settings.aircraft_db_path,
            settings.aircraft_db_url,
            settings.aircraft_db_max_age_days,
        )
    app.state.aircraft_db = AircraftDatabase()
    await asyncio.to_thread(app.state.aircraft_db.load, settings.aircraft_db_path)

    if not settings.opensky_enabled:
        logger.warning(
            "OpenSky credentials not set — using anonymous access (low rate limits)."
        )
    if not settings.adsbdb_enabled and not settings.flightaware_enabled:
        logger.warning("No route providers enabled — routes will be unavailable.")

    gc_task = asyncio.create_task(
        run_gc_loop(app.state.cache, settings.gc_interval_ms)
    )

    try:
        yield
    finally:
        gc_task.cancel()
        try:
            await gc_task
        except asyncio.CancelledError:
            pass
        await app.state.cache.save()
        await app.state.opensky.aclose()
        await app.state.adsbdb.aclose()
        await app.state.flightaware.aclose()


app = FastAPI(
    title="Local Traffic Radar Middleware",
    version=__version__,
    summary="Self-hosted proxy that feeds the ESP32 traffic radar.",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict:
    """Liveness probe plus a peek at runtime state."""
    settings = app.state.settings
    return {
        "status": "ok",
        "version": __version__,
        "opensky_auth": settings.opensky_enabled,
        "route_providers": {
            "adsbdb": settings.adsbdb_enabled,
            "flightaware": settings.flightaware_enabled,
        },
        "cache_entries": app.state.cache.size,
        "aircraft_db_loaded": app.state.aircraft_db.loaded,
        "aircraft_db_size": app.state.aircraft_db.size,
    }


@app.get("/api/metrics")
async def metrics() -> dict:
    """Session usage metrics: external API calls vs. work served locally."""
    snap = METRICS.snapshot()
    snap["cache_entries"] = app.state.cache.size
    snap["aircraft_db_size"] = app.state.aircraft_db.size
    snap["recommended_poll_seconds"] = METRICS.recommended_poll_seconds(
        app.state.settings.poll_default_seconds, app.state.settings.poll_min_seconds
    )
    return snap


@app.get("/api/metrics/reset")
async def metrics_reset() -> dict:
    """Zero the session counters (handy for a clean measurement run)."""
    METRICS.reset()
    return {"status": "reset"}


@app.get("/api/nearby", response_model=list[AircraftPayload], response_model_by_alias=True)
async def nearby(
    response: Response,
    lat: float | None = Query(default=None, ge=-90, le=90,
                              description="Home latitude (defaults to HOME_LAT)."),
    lon: float | None = Query(default=None, ge=-180, le=180,
                              description="Home longitude (defaults to HOME_LON)."),
    radius: int | None = Query(default=None, gt=0, le=250,
                               description="Search radius in miles."),
):
    """Return enriched, optimized aircraft payloads within the radius.

    Mirrors the spec's hardware inbound request:
    ``GET /api/nearby?lat=40.75&lon=-73.99&radius=15``
    """
    settings = app.state.settings
    home_lat = lat if lat is not None else settings.home_lat
    home_lon = lon if lon is not None else settings.home_lon
    radius_miles = radius if radius is not None else settings.default_radius_miles

    box = compute_bounding_box(home_lat, home_lon, radius_miles)

    try:
        vectors = await app.state.opensky.get_states_in_box(box)
    except OpenSkyError as exc:
        logger.error("OpenSky fetch failed: %s", exc)
        return JSONResponse(
            status_code=502,
            content={"error": "upstream_unavailable", "detail": str(exc)},
        )

    payloads = await build_payloads(
        vectors,
        cache=app.state.cache,
        providers=app.state.route_providers,
        negative_ttl_ms=settings.route_negative_ttl_ms,
        aircraft_db=app.state.aircraft_db,
        filter_grounded_planes=settings.filter_grounded_planes,
        plane_min_speed_mph=settings.plane_min_speed_mph,
    )
    response.headers["X-Recommended-Poll-Seconds"] = str(
        METRICS.recommended_poll_seconds(
            settings.poll_default_seconds, settings.poll_min_seconds
        )
    )
    return payloads


def run() -> None:
    """Entry point for ``python -m app.main`` / console use."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
    )


if __name__ == "__main__":
    run()
