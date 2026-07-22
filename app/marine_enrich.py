"""Orchestration: turn vessel-store snapshots into the marine payload.

The marine analog of ``enrich.py``. Because AIS carries nearly every field on
the stream, this is entirely local — no per-vessel network calls:

  1. Bounding-box filter the snapshot to the requested radius.
  2. Classify + drop moored/slow vessels (analog of the grounded/slow-plane
     filter).
  3. Assemble each surviving vessel into a descriptive ``VesselPayload``.
"""

from __future__ import annotations

import logging

from .geo import BoundingBox
from .marine_static_data import (
    STATIONARY_NAV_STATUS,
    country_from_mmsi,
    nav_status_label,
    vessel_category,
    vessel_operator_class,
    vessel_special_designation,
)
from .metrics import METRICS
from .models import VesselPayload
from .vessel_store import VesselState

logger = logging.getLogger("traffic_radar.marine_enrich")

# Categories always kept regardless of speed/nav-status (mirrors AIR keeping
# helicopters and non-planes).
_ALWAYS_KEEP = {
    "Search and Rescue",
    "Law Enforcement",
    "Pilot Vessel",
    "Military",
}


def _should_drop_vessel(
    vessel: VesselState, category: str, min_speed_knots: float
) -> bool:
    """Drop a vessel that is moored/anchored/aground or barely moving.

    Special-service categories are always kept. A vessel with a stationary
    nav-status, or one whose speed is below the gate, is dropped.
    """
    if category in _ALWAYS_KEEP:
        return False
    if vessel.nav_status in STATIONARY_NAV_STATUS:
        return True
    sog = vessel.sog_knots
    return sog is None or sog < min_speed_knots


def _build_payload(vessel: VesselState, category: str) -> VesselPayload:
    country, iso = country_from_mmsi(vessel.mmsi)
    return VesselPayload(
        mmsi=str(vessel.mmsi),
        name=vessel.name or "Unknown",
        callsign=vessel.callsign or "",
        imo_number=str(vessel.imo_number) if vessel.imo_number else "Unknown",
        vessel_type=category,
        ship_type_code=vessel.ship_type,
        nav_status=nav_status_label(vessel.nav_status),
        destination=vessel.destination or "N/A",
        eta=vessel.eta or "",
        speed_knots=round(vessel.sog_knots) if vessel.sog_knots is not None else 0,
        course_degrees=round(vessel.cog_degrees) % 360
        if vessel.cog_degrees is not None else 0,
        heading_degrees=vessel.true_heading % 360
        if vessel.true_heading is not None and vessel.true_heading < 360 else 0,
        latitude=vessel.latitude,
        longitude=vessel.longitude,
        length_meters=vessel.length_m,
        beam_meters=vessel.beam_m,
        draught_meters=round(vessel.draught_m, 1),
        country=country,
        country_iso=iso,
        operator_class=vessel_operator_class(vessel.ship_type),
        special_designation=vessel_special_designation(vessel.ship_type),
    )


def build_vessel_payloads(
    vessels: list[VesselState],
    box: BoundingBox,
    filter_moored: bool = True,
    vessel_min_speed_knots: float = 0.5,
) -> list[VesselPayload]:
    """Filter a store snapshot by box + motion and assemble payloads (all local)."""
    METRICS.incr("requests.marine_nearby")

    # 1. Bounding-box filter (the per-request radius narrows the channel box).
    in_box = [
        v for v in vessels
        if v.latitude is not None and v.longitude is not None
        and box.contains(v.latitude, v.longitude)
    ]

    # 2. Classify, then drop moored/slow vessels.
    typed = [(v, vessel_category(v.ship_type)) for v in in_box]
    if filter_moored:
        kept = [
            (v, c) for (v, c) in typed
            if not _should_drop_vessel(v, c, vessel_min_speed_knots)
        ]
        skipped = len(typed) - len(kept)
        if skipped:
            METRICS.incr("marine.vessels_filtered", skipped)
        typed = kept

    payloads = [_build_payload(v, c) for (v, c) in typed]
    METRICS.incr("vessels.returned", len(payloads))
    logger.info(
        "Marine enrich: %d in store → %d in box → %d after motion filter",
        len(vessels), len(in_box), len(payloads),
    )
    return payloads
