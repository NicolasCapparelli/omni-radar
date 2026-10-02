"""Bounding-box geometry for converting a home coordinate + radius into the
fractional lat/lon box that OpenSky's ``/states/all`` endpoint expects.

Spatial approximations (flat-earth, fine at radar-sized radii):
    1 degree of latitude  ~= 69.0 miles
    1 degree of longitude ~= 69.0 * cos(latitude) miles
(the spec's fixed 53.0 mi/deg longitude is this value at ~40 deg N).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MILES_PER_DEG_LAT = 69.0
# Floor for cos(latitude) so the longitude span stays finite near the poles.
_MIN_COS_LAT = 0.01


@dataclass(frozen=True)
class BoundingBox:
    """An axis-aligned WGS-84 bounding box in decimal degrees."""

    lamin: float  # min latitude
    lamax: float  # max latitude
    lomin: float  # min longitude
    lomax: float  # max longitude

    def as_opensky_bbox(self) -> tuple[float, float, float, float]:
        """Return the box ordered as OpenSky expects: (lamin, lamax, lomin, lomax)."""
        return (self.lamin, self.lamax, self.lomin, self.lomax)

    def as_aisstream_bbox(self) -> list[list[list[float]]]:
        """Return the box as aisstream.io expects it.

        aisstream subscribes to ``BoundingBoxes`` of ``[[lat, lon], [lat, lon]]``
        corner pairs (SW corner then NE corner), wrapped in an outer list so a
        single subscription can carry multiple boxes.
        """
        return [[[self.lamin, self.lomin], [self.lamax, self.lomax]]]

    def contains(self, lat: float, lon: float) -> bool:
        """True if ``(lat, lon)`` falls inside this box (inclusive)."""
        return self.lamin <= lat <= self.lamax and self.lomin <= lon <= self.lomax


def compute_bounding_box(
    home_lat: float, home_lon: float, radius_miles: float
) -> BoundingBox:
    """Convert a home coordinate and radius (miles) into a lat/lon bounding box.

    Uses:
        latOffset = radiusMiles / 69.0
        lonOffset = radiusMiles / (69.0 * cos(homeLat))
    so the box covers the radius east-west at any latitude, not just ~40 deg N.
    """
    if radius_miles <= 0:
        raise ValueError("radius_miles must be positive")

    lat_offset = radius_miles / MILES_PER_DEG_LAT
    cos_lat = max(_MIN_COS_LAT, math.cos(math.radians(home_lat)))
    lon_offset = radius_miles / (MILES_PER_DEG_LAT * cos_lat)

    # Clamp to valid WGS-84 ranges so we never hand OpenSky an out-of-range box.
    lamin = max(-90.0, home_lat - lat_offset)
    lamax = min(90.0, home_lat + lat_offset)
    lomin = max(-180.0, home_lon - lon_offset)
    lomax = min(180.0, home_lon + lon_offset)

    return BoundingBox(lamin=lamin, lamax=lamax, lomin=lomin, lomax=lomax)
