"""Async OpenSky Network client.

Handles the OAuth2 *client credentials* flow (auto-refreshing the bearer token)
and fetches live state vectors for a bounding box from ``/states/all``.

Token endpoint and state-vector layout verified against the official OpenSky
API client:
https://github.com/openskynetwork/opensky-api
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

import httpx

from .geo import BoundingBox
from .metrics import METRICS

logger = logging.getLogger("traffic_radar.opensky")

TOKEN_URL = (
    "https://auth.opensky-network.org/auth/realms/"
    "opensky-network/protocol/openid-connect/token"
)
API_BASE = "https://opensky-network.org/api"
TOKEN_REFRESH_MARGIN_S = 30

# State-vector array indices (extended=true adds index 17).
IDX_ICAO24 = 0
IDX_CALLSIGN = 1
IDX_ORIGIN_COUNTRY = 2
IDX_LONGITUDE = 5
IDX_LATITUDE = 6
IDX_BARO_ALTITUDE = 7
IDX_ON_GROUND = 8
IDX_VELOCITY = 9
IDX_TRUE_TRACK = 10
IDX_VERTICAL_RATE = 11
IDX_GEO_ALTITUDE = 13
IDX_SQUAWK = 14
IDX_CATEGORY = 17

METERS_TO_FEET = 3.28084
MS_TO_MPH = 2.236936
MS_TO_KNOTS = 1.943844
MS_TO_FPM = 196.850394  # m/s -> feet per minute

# Emergency transponder (squawk) codes.
SQUAWK_EMERGENCY = {
    "7500": "Hijack",
    "7600": "Radio Failure",
    "7700": "Emergency",
}


@dataclass
class StateVector:
    """A trimmed, typed view of an OpenSky state vector."""

    icao24: str
    callsign: str
    origin_country: Optional[str]
    longitude: Optional[float]
    latitude: Optional[float]
    baro_altitude_m: Optional[float]
    on_ground: bool
    velocity: Optional[float]
    true_track: Optional[float]
    vertical_rate: Optional[float]
    squawk: Optional[str]
    category: Optional[int]

    @property
    def altitude_ft(self) -> int:
        if self.baro_altitude_m is None:
            return 0
        return round(self.baro_altitude_m * METERS_TO_FEET)

    @property
    def heading_deg(self) -> int:
        if self.true_track is None:
            return 0
        return round(self.true_track) % 360

    @property
    def speed_knots(self) -> int:
        if self.velocity is None:
            return 0
        return round(self.velocity * MS_TO_KNOTS)

    @property
    def vertical_rate_fpm(self) -> int:
        """Vertical speed in feet/min (positive = climbing, negative = descending)."""
        if self.vertical_rate is None:
            return 0
        return round(self.vertical_rate * MS_TO_FPM)

    @property
    def emergency(self) -> str:
        """Emergency status from the squawk code, or 'None'."""
        if not self.squawk:
            return "None"
        return SQUAWK_EMERGENCY.get(self.squawk.strip(), "None")

    @classmethod
    def from_array(cls, arr: list) -> "StateVector":
        def at(idx: int):
            return arr[idx] if idx < len(arr) else None

        raw_callsign = at(IDX_CALLSIGN)
        raw_squawk = at(IDX_SQUAWK)
        return cls(
            icao24=(at(IDX_ICAO24) or "").strip().lower(),
            callsign=(raw_callsign or "").strip(),
            origin_country=at(IDX_ORIGIN_COUNTRY),
            longitude=at(IDX_LONGITUDE),
            latitude=at(IDX_LATITUDE),
            baro_altitude_m=at(IDX_BARO_ALTITUDE),
            on_ground=bool(at(IDX_ON_GROUND)),
            velocity=at(IDX_VELOCITY),
            true_track=at(IDX_TRUE_TRACK),
            vertical_rate=at(IDX_VERTICAL_RATE),
            squawk=(raw_squawk.strip() if isinstance(raw_squawk, str) else raw_squawk),
            category=at(IDX_CATEGORY),
        )


class OpenSkyError(RuntimeError):
    """Raised when OpenSky cannot be reached or returns an error."""


class _TokenManager:
    """Lazily fetches and caches an OAuth2 access token."""

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: Optional[str] = None
        self._expires_at: float = 0.0

    async def token(self, client: httpx.AsyncClient) -> str:
        if self._token and time.time() < self._expires_at:
            return self._token
        return await self._refresh(client)

    async def _refresh(self, client: httpx.AsyncClient) -> str:
        resp = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        expires_in = int(data.get("expires_in", 1800))
        self._expires_at = time.time() + expires_in - TOKEN_REFRESH_MARGIN_S
        logger.debug("OpenSky OAuth2 token refreshed (valid %ds)", expires_in)
        return self._token


class OpenSkyClient:
    """Async client for fetching live state vectors within a bounding box."""

    def __init__(
        self,
        client_id: str = "",
        client_secret: str = "",
        timeout: float = 15.0,
    ) -> None:
        self._token_manager = (
            _TokenManager(client_id, client_secret)
            if client_id and client_secret
            else None
        )
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _auth_headers(self) -> dict:
        if self._token_manager is None:
            return {}
        token = await self._token_manager.token(self._client)
        return {"Authorization": f"Bearer {token}"}

    async def get_states_in_box(self, box: BoundingBox) -> list[StateVector]:
        """Return live state vectors within ``box``.

        Raises :class:`OpenSkyError` on transport or HTTP failures so the caller
        can decide how to degrade.
        """
        lamin, lamax, lomin, lomax = box.as_opensky_bbox()
        params = {
            "lamin": lamin,
            "lamax": lamax,
            "lomin": lomin,
            "lomax": lomax,
            "extended": "true",
        }
        try:
            headers = await self._auth_headers()
            METRICS.incr("opensky.requests")
            resp = await self._client.get(
                f"{API_BASE}/states/all", params=params, headers=headers
            )
        except httpx.HTTPError as exc:
            METRICS.incr("opensky.errors")
            raise OpenSkyError(f"OpenSky request failed: {exc}") from exc

        # Capture credit balance from the rate-limit headers when present.
        remaining = resp.headers.get("X-Rate-Limit-Remaining")
        if remaining is not None:
            try:
                METRICS.set_gauge("opensky.credits_remaining", int(remaining))
            except ValueError:
                pass

        if resp.status_code == 429:
            METRICS.incr("opensky.rate_limited")
            retry = resp.headers.get("X-Rate-Limit-Retry-After-Seconds")
            if retry is not None:
                try:
                    METRICS.set_gauge("opensky.retry_after_seconds", int(retry))
                except ValueError:
                    pass
            raise OpenSkyError("OpenSky rate limit exceeded (HTTP 429)")
        if resp.status_code != 200:
            METRICS.incr("opensky.errors")
            raise OpenSkyError(f"OpenSky returned HTTP {resp.status_code}")

        payload = resp.json()
        raw_states = payload.get("states") or []
        vectors = [StateVector.from_array(s) for s in raw_states]
        # Drop entries without a usable position or callsign.
        return [
            v
            for v in vectors
            if v.callsign and v.latitude is not None and v.longitude is not None
        ]
