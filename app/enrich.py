"""Orchestration: turn raw OpenSky state vectors into the optimized payload.

Pipeline per aircraft:
  1. Native (free) extraction: vehicle type, model, registration, owner, airline,
     and special designation from the state vector, the offline aircraft DB, and
     static tables — no network calls.
  2. Route lookup (origin/destination) via the route providers (adsbdb first,
     FlightAware fallback), shielded by a persistent look-aside cache.
  3. Assemble the descriptive ``AircraftPayload``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Sequence

from .aircraft_db import AircraftDatabase
from .cache import FlightMeta, MetadataCache
from .metrics import METRICS
from .models import AircraftPayload
from .opensky import StateVector
from .routes import RouteProvider, resolve_route
from .static_data import airline_from_callsign, operator_class, special_designation

logger = logging.getLogger("traffic_radar.enrich")

# OpenSky broadcast "category" index -> vehicle type label.
# (Indices 2-7 are weight classes of fixed-wing aircraft -> "Plane".)
CATEGORY_TYPE: dict[int, str] = {
    2: "Plane",
    3: "Plane",
    4: "Plane",
    5: "Plane",
    6: "Plane",
    7: "Plane",
    8: "Helicopter",
    9: "Glider",
    10: "Lighter-than-air",
    11: "Skydiver",
    12: "Ultralight",
    14: "Drone",
    15: "Spacecraft",
    16: "Surface Vehicle",
    17: "Surface Vehicle",
    18: "Obstacle",
    19: "Obstacle",
    20: "Obstacle",
}

# ICAO Doc 8643 descriptor first char -> vehicle type label (airframe-accurate).
DESCRIPTOR_TYPE: dict[str, str] = {
    "L": "Plane",       # landplane
    "S": "Seaplane",
    "A": "Amphibian",
    "H": "Helicopter",
    "G": "Gyrocopter",
    "T": "Tiltrotor",
}

# Descriptor classes that are definitive regardless of broadcast category.
_DEFINITIVE_DESCRIPTORS = {"H", "G", "T", "S", "A"}


def classify_type(
    vector: StateVector,
    aircraft_db: "AircraftDatabase | None" = None,
) -> str:
    """Classify a vehicle across the full ICAO/OpenSky taxonomy.

    Resolution:
      1. The offline aircraft DB's Doc 8643 descriptor gives the airframe's
         physical class. H/G/T/S/A are definitive (helicopter, gyrocopter,
         tiltrotor, seaplane, amphibian).
      2. Otherwise the OpenSky broadcast category distinguishes glider,
         lighter-than-air, skydiver, ultralight, drone, spacecraft, surface
         vehicle, and obstacle.
      3. Falls back to "Plane" for landplanes / generic aircraft / unknowns.
    """
    descr_class = aircraft_db.descriptor_class(vector.icao24) if aircraft_db else None
    if descr_class in _DEFINITIVE_DESCRIPTORS:
        return DESCRIPTOR_TYPE[descr_class]

    label = CATEGORY_TYPE.get(vector.category) if vector.category is not None else None
    if label:
        return label

    return "Plane"


def _offline_meta(callsign: str) -> FlightMeta:
    """Metadata with only the offline airline name (no route)."""
    return FlightMeta(airline=airline_from_callsign(callsign) or "Unknown Airline")


async def _resolve_metadata(
    callsign: str,
    cache: MetadataCache,
    providers: Sequence[RouteProvider],
    negative_ttl_ms: int,
) -> FlightMeta:
    """Resolve route metadata for a callsign, shielded by the cache.

    Caching taxonomy: route found -> default (long) TTL; definitively no route
    -> negative TTL; transient provider failure -> not cached (retry next poll).
    """
    cached = await cache.get(callsign)
    if cached is not None:
        METRICS.incr("routes.cache_hits")
        return cached
    METRICS.incr("routes.cache_misses")

    if not any(p.enabled for p in providers):
        return _offline_meta(callsign)

    meta, status = await resolve_route(callsign, providers)
    if status == "found" and meta is not None:
        await cache.set(callsign, meta)
        return meta
    if status == "notfound":
        empty = _offline_meta(callsign)
        await cache.set(callsign, empty, ttl_ms=negative_ttl_ms)
        return empty
    # transient/unavailable: don't cache, let the next poll retry.
    return _offline_meta(callsign)


def _build_payload(
    vector: StateVector,
    meta: FlightMeta,
    vehicle_type: str,
    aircraft_db: AircraftDatabase | None = None,
) -> AircraftPayload:
    # Prefer the enriched model; fall back to the offline ICAO24 -> type lookup.
    model = meta.model
    model_name = "Unknown"
    registration = None
    operator_name = "Unknown"
    owner_name = "Unknown"
    if aircraft_db is not None:
        record = aircraft_db.get(vector.icao24)
        if record is not None:
            METRICS.incr("aircraftdb.hits")
            if (not model or model == "Unknown") and record.typecode:
                model = record.typecode
            if record.model_name:
                model_name = record.model_name
            registration = record.registration or None
            if record.operator:
                operator_name = record.operator
            if record.owner:
                owner_name = record.owner

    # Operator name fallback: DB operator -> resolved airline name.
    if operator_name == "Unknown" and meta.airline and meta.airline != "Unknown Airline":
        operator_name = meta.airline

    return AircraftPayload(
        callsign=vector.callsign,
        vehicle_type=vehicle_type,
        model_code=model or "Unknown",
        model_name=model_name,
        airline=meta.airline,
        origin=meta.origin,
        origin_name=meta.origin_name,
        origin_country=meta.origin_country,
        destination=meta.destination,
        destination_name=meta.destination_name,
        destination_country=meta.destination_country,
        altitude_feet=vector.altitude_ft,
        speed_knots=vector.speed_knots,
        vertical_speed_fpm=vector.vertical_rate_fpm,
        heading_degrees=vector.heading_deg,
        latitude=vector.latitude,
        longitude=vector.longitude,
        squawk=vector.squawk or "",
        emergency=vector.emergency,
        on_ground=vector.on_ground,
        country=vector.origin_country or "Unknown",
        registration=registration or "Unknown",
        operator_class=operator_class(
            vector.callsign, vector.icao24, registration, airline=meta.airline
        ),
        operator=operator_name,
        owner=owner_name,
        special_designation=special_designation(vector.callsign, vector.icao24),
    )


MPH_TO_MS = 0.44704


def _should_drop_plane(
    vector: StateVector, vehicle_type: str, min_speed_ms: float
) -> bool:
    """Decide whether to drop a fixed-wing plane before enrichment.

    Rules:
      * non-planes are never dropped;
      * if ``on_ground`` is true, drop it outright;
      * otherwise (airborne) rely on speed: keep only if moving faster than the
        gate. A missing ground speed counts as below the gate (dropped).
    """
    if vehicle_type != "Plane":
        return False
    if vector.on_ground:
        return True
    return vector.velocity is None or vector.velocity <= min_speed_ms


async def build_payloads(
    vectors: list[StateVector],
    cache: MetadataCache,
    providers: Sequence[RouteProvider],
    negative_ttl_ms: int,
    aircraft_db: AircraftDatabase | None = None,
    filter_grounded_planes: bool = False,
    plane_min_speed_mph: float = 60.0,
) -> list[AircraftPayload]:
    """Enrich every state vector concurrently and return payloads.

    Route lookups go through ``providers`` (cached); ``filter_grounded_planes``
    drops on-ground / slow planes before enrichment to avoid wasted lookups.
    """
    # Classify up front so we can filter planes before any enrichment.
    typed = [(v, classify_type(v, aircraft_db)) for v in vectors]
    METRICS.incr("requests.nearby")

    if filter_grounded_planes:
        min_speed_ms = plane_min_speed_mph * MPH_TO_MS
        kept = [
            (v, t)
            for (v, t) in typed
            if not _should_drop_plane(v, t, min_speed_ms)
        ]
        skipped = len(typed) - len(kept)
        if skipped:
            METRICS.incr("enrich.planes_filtered", skipped)
            logger.info(
                "Filtered %d plane(s) (on-ground or below %.0f mph) before enrichment",
                skipped, plane_min_speed_mph,
            )
        typed = kept

    async def one(vector: StateVector, vehicle_type: str) -> AircraftPayload:
        meta = await _resolve_metadata(
            vector.callsign, cache, providers, negative_ttl_ms
        )
        return _build_payload(vector, meta, vehicle_type, aircraft_db)

    payloads = await asyncio.gather(*(one(v, t) for (v, t) in typed))
    METRICS.incr("aircraft.returned", len(payloads))
    return payloads
