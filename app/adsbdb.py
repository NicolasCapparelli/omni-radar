"""adsbdb.com route provider (free, keyless, primary route source).

Looks up a callsign's origin/destination via the public adsbdb API:
    GET https://api.adsbdb.com/v0/callsign/{callsign}
Returns 404 ("unknown callsign") when no route is known. We throttle politely
and never retry in-line — transient failures defer to the next poll.

API shape: https://github.com/mrjackwills/adsbdb
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from .cache import FlightMeta
from .routes import RouteRateLimited, RouteUnavailable, Throttle
from .static_data import airline_from_callsign

logger = logging.getLogger("traffic_radar.adsbdb")


def _airport_code(node: dict) -> str:
    return node.get("iata_code") or node.get("icao_code") or "N/A"


def _airport_name(node: dict) -> str:
    return node.get("name") or node.get("municipality") or "Unknown Route"


class AdsbdbClient:
    """Async client for adsbdb callsign -> route lookups."""

    name = "adsbdb"

    def __init__(
        self,
        base_url: str = "https://api.adsbdb.com/v0",
        enabled: bool = True,
        timeout: float = 15.0,
        max_concurrency: int = 2,
        min_interval_ms: int = 200,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._enabled = enabled
        self._client = httpx.AsyncClient(
            timeout=timeout, headers={"Accept": "application/json"}
        )
        self._throttle = Throttle(max_concurrency, min_interval_ms / 1000.0)

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_route(self, callsign: str) -> Optional[FlightMeta]:
        ident = callsign.strip()
        if not ident:
            return None
        url = f"{self._base_url}/callsign/{ident}"
        try:
            async with self._throttle:
                resp = await self._client.get(url)
        except httpx.HTTPError as exc:
            raise RouteUnavailable(f"adsbdb transport error: {exc}") from exc

        if resp.status_code == 429:
            raise RouteRateLimited(f"adsbdb 429 for {ident}")
        if resp.status_code == 404:
            return None  # unknown callsign -> definitively no route
        if resp.status_code >= 500:
            raise RouteUnavailable(f"adsbdb {resp.status_code} for {ident}")
        if resp.status_code != 200:
            raise RouteUnavailable(f"adsbdb {resp.status_code} for {ident}")

        response = resp.json().get("response")
        if not isinstance(response, dict):
            return None
        flightroute = response.get("flightroute")
        if not flightroute:
            return None
        origin = flightroute.get("origin")
        destination = flightroute.get("destination")
        if not origin or not destination:
            return None

        airline_node = flightroute.get("airline") or {}
        airline = (
            airline_from_callsign(callsign)
            or airline_node.get("name")
            or "Unknown Airline"
        )
        return FlightMeta(
            airline=airline,
            model="Unknown",  # filled from the offline aircraft DB
            origin=_airport_code(origin),
            origin_name=_airport_name(origin),
            destination=_airport_code(destination),
            destination_name=_airport_name(destination),
        )
