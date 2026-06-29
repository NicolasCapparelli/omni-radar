"""Application configuration loaded from environment / .env file."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed settings sourced from environment variables.

    Values map 1:1 to the keys documented in ``.env.example``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # OpenSky OAuth2 client credentials
    opensky_client_id: str = ""
    opensky_client_secret: str = ""

    # ── Route providers ──────────────────────────────────────────────────
    # adsbdb (free, keyless) is the primary route source.
    adsbdb_enabled: bool = True
    adsbdb_base_url: str = "https://api.adsbdb.com/v0"
    adsbdb_max_concurrency: int = 2
    adsbdb_min_interval_ms: int = 200

    # FlightAware AeroAPI — optional fallback for routes adsbdb doesn't have.
    flightaware_api_key: str = ""
    flightaware_base_url: str = "https://aeroapi.flightaware.com/aeroapi"
    flightaware_max_concurrency: int = 2
    flightaware_min_interval_ms: int = 350

    # Hardware defaults
    home_lat: float = 40.7580
    home_lon: float = -73.9965
    default_radius_miles: int = 15

    # Route cache (routes are static for a flight's life, so cache hard).
    route_cache_ttl_ms: int = 43_200_000   # 12 hours for resolved routes
    route_negative_ttl_ms: int = 10_800_000  # 3 hours for "no route found"
    gc_interval_ms: int = 1_800_000        # sweep + persist every 30 minutes
    cache_persist_path: str = "data/route_cache.json"

    # Offline aircraft database (free ICAO24 -> aircraft type fallback for `mdl`)
    aircraft_db_path: str = "data/aircraftDatabase.csv"
    aircraft_db_url: str = (
        "https://opensky-network.org/datasets/metadata/aircraftDatabase.csv"
    )
    # Auto-download on startup if the local file is missing or older than the
    # max age. Set max age to 0 to disable the staleness check; set
    # auto_download to false to skip downloading entirely.
    aircraft_db_auto_download: bool = True
    aircraft_db_max_age_days: int = 30

    # Filtering: drop a plane outright if on_ground is true; otherwise (airborne)
    # rely on speed and keep it only if moving faster than the gate. Trusts
    # on_ground when set, and uses the speed gate when it isn't. Helicopters and
    # all non-plane types are always kept.
    filter_grounded_planes: bool = True
    plane_min_speed_mph: float = 60.0

    # Polling guidance advertised to clients (device/web console poll us).
    # OpenSky data refreshes every ~5s (the floor); credit back-off raises this.
    poll_default_seconds: int = 30
    poll_min_seconds: int = 5

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"

    @property
    def opensky_enabled(self) -> bool:
        return bool(self.opensky_client_id and self.opensky_client_secret)

    @property
    def flightaware_enabled(self) -> bool:
        return bool(self.flightaware_api_key)


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton of the application settings."""
    return Settings()
