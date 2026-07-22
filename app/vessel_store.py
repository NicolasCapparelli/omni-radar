"""In-memory store of the latest known state per vessel, keyed by MMSI.

The marine analog of the AIR route ``cache.py``, but inverted: instead of a
look-aside cache filled on demand, this is a *write-through* store fed
continuously by the aisstream WebSocket ingest task. AIS sends position and
static data as separate messages, so the store **merges** them per MMSI:

  * position reports update lat/lon/speed/course/heading/nav-status;
  * static-data reports update name/callsign/IMO/type/dimensions/destination.

Entries are evicted after ``ttl_ms`` of silence so vessels that sail out of
range or stop transmitting age out. Reads are served as a point-in-time
snapshot; the endpoint then filters by bounding box (zero network cost).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional


def _now_ms() -> float:
    return time.time() * 1000.0


@dataclass
class VesselState:
    """Merged latest-known state for one vessel (MMSI)."""

    mmsi: int
    # Position (from PositionReport / StandardClassBPositionReport)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    sog_knots: Optional[float] = None      # speed over ground
    cog_degrees: Optional[float] = None    # course over ground
    true_heading: Optional[int] = None
    nav_status: Optional[int] = None
    # Static (from ShipStaticData)
    name: str = ""
    callsign: str = ""
    imo_number: int = 0
    ship_type: int = 0
    dim_a: int = 0
    dim_b: int = 0
    dim_c: int = 0
    dim_d: int = 0
    draught_m: float = 0.0
    destination: str = ""
    eta: str = ""
    # Bookkeeping
    last_update_ms: float = field(default_factory=_now_ms)

    @property
    def length_m(self) -> int:
        return int(self.dim_a + self.dim_b)

    @property
    def beam_m(self) -> int:
        return int(self.dim_c + self.dim_d)


class VesselStore:
    """Async, MMSI-keyed store of merged vessel state with TTL eviction."""

    def __init__(self, ttl_ms: int) -> None:
        self._ttl_ms = ttl_ms
        self._store: dict[int, VesselState] = {}
        self._lock = asyncio.Lock()

    async def update_position(
        self,
        mmsi: int,
        latitude: Optional[float],
        longitude: Optional[float],
        sog_knots: Optional[float] = None,
        cog_degrees: Optional[float] = None,
        true_heading: Optional[int] = None,
        nav_status: Optional[int] = None,
        name: str = "",
    ) -> None:
        """Merge a position report into the vessel's state."""
        async with self._lock:
            v = self._store.get(mmsi) or VesselState(mmsi=mmsi)
            if latitude is not None:
                v.latitude = latitude
            if longitude is not None:
                v.longitude = longitude
            if sog_knots is not None:
                v.sog_knots = sog_knots
            if cog_degrees is not None:
                v.cog_degrees = cog_degrees
            if true_heading is not None:
                v.true_heading = true_heading
            if nav_status is not None:
                v.nav_status = nav_status
            # Static fields ride in metadata on every frame; keep the name fresh
            # but never overwrite a real name with a blank.
            if name and not v.name:
                v.name = name.strip()
            v.last_update_ms = _now_ms()
            self._store[mmsi] = v

    async def update_static(
        self,
        mmsi: int,
        *,
        name: str = "",
        callsign: str = "",
        imo_number: int = 0,
        ship_type: int = 0,
        dimension: Optional[dict] = None,
        draught_m: float = 0.0,
        destination: str = "",
        eta: str = "",
    ) -> None:
        """Merge a static-data report into the vessel's state."""
        async with self._lock:
            v = self._store.get(mmsi) or VesselState(mmsi=mmsi)
            if name:
                v.name = name.strip()
            if callsign:
                v.callsign = callsign.strip()
            if imo_number:
                v.imo_number = imo_number
            if ship_type:
                v.ship_type = ship_type
            if dimension:
                v.dim_a = dimension.get("A", v.dim_a)
                v.dim_b = dimension.get("B", v.dim_b)
                v.dim_c = dimension.get("C", v.dim_c)
                v.dim_d = dimension.get("D", v.dim_d)
            if draught_m:
                v.draught_m = draught_m
            if destination:
                v.destination = destination.strip()
            if eta:
                v.eta = eta
            v.last_update_ms = _now_ms()
            self._store[mmsi] = v

    async def snapshot(self) -> list[VesselState]:
        """Return a point-in-time copy of all unexpired vessel states."""
        now = _now_ms()
        async with self._lock:
            return [
                v
                for v in self._store.values()
                if now - v.last_update_ms <= self._ttl_ms
            ]

    async def sweep(self) -> int:
        """Evict vessels silent for longer than the TTL. Returns count removed."""
        now = _now_ms()
        async with self._lock:
            stale = [
                mmsi
                for mmsi, v in self._store.items()
                if now - v.last_update_ms > self._ttl_ms
            ]
            for mmsi in stale:
                self._store.pop(mmsi, None)
        return len(stale)

    @property
    def size(self) -> int:
        return len(self._store)
