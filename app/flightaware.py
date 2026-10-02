"""FlightAware AeroAPI route provider (optional fallback after adsbdb).

Resolves a callsign's origin/destination via the AeroAPI ``/flights/{ident}``
endpoint. Used only as a fallback for routes adsbdb doesn't have. Calls are
throttled and never retried in-line: a 429/5xx defers to the next poll
(raising :class:`RouteRateLimited` / :class:`RouteUnavailable`) rather than
amplifying the load.

AeroAPI reference: https://www.flightaware.com/aeroapi/portal/documentation
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from .cache import FlightMeta
from .metrics import METRICS
from .routes import RouteRateLimited, RouteUnavailable, Throttle
from .static_data import airline_from_callsign, airline_from_icao

logger = logging.getLogger("traffic_radar.flightaware")


def _pick_active_flight(flights: list[dict]) -> Optional[dict]:
    """Choose the most relevant flight (prefer en route), else the first."""
    if not flights:
        return None
    for flight in flights:
        progress = flight.get("progress_percent")
        if isinstance(progress, (int, float)) and 0 < progress < 100:
            return flight
    return flights[0]


def _airport_code(node: Optional[dict]) -> Optional[str]:
    if not node:
        return None
    return node.get("code_iata") or node.get("code_icao") or node.get("code")


def _airport_name(node: Optional[dict]) -> str:
    if not node:
        return "Unknown Route"
    return node.get("name") or node.get("city") or "Unknown Route"


class FlightAwareClient:
    """Async AeroAPI ``/flights/{ident}`` route provider."""

    name = "flightaware"

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://aeroapi.flightaware.com/aeroapi",
        timeout: float = 15.0,
        max_concurrency: int = 2,
        min_interval_ms: int = 350,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"x-apikey": api_key, "Accept": "application/json"},
        )
        self._throttle = Throttle(max_concurrency, min_interval_ms / 1000.0)

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_route(self, callsign: str) -> Optional[FlightMeta]:
        ident = callsign.strip()
        if not ident:
            return None
        url = f"{self._base_url}/flights/{ident}"
        try:
            async with self._throttle:
                METRICS.incr("flightaware.requests")
                resp = await self._client.get(url)
        except httpx.HTTPError as exc:
            METRICS.incr("flightaware.errors")
            raise RouteUnavailable(f"AeroAPI transport error: {exc}") from exc

        if resp.status_code == 429:
            METRICS.incr("flightaware.rate_limited")
            raise RouteRateLimited(f"AeroAPI 429 for {ident}")
        if resp.status_code >= 500:
            METRICS.incr("flightaware.errors")
            raise RouteUnavailable(f"AeroAPI {resp.status_code} for {ident}")
        if resp.status_code == 404:
            METRICS.incr("flightaware.notfound")
            return None  # no flight record -> no route
        if resp.status_code != 200:
            METRICS.incr("flightaware.errors")
            raise RouteUnavailable(f"AeroAPI {resp.status_code} for {ident}")

        try:
            body = resp.json()
        except ValueError as exc:
            METRICS.incr("flightaware.errors")
            raise RouteUnavailable(f"AeroAPI returned invalid JSON for {ident}") from exc
        flights = body.get("flights") if isinstance(body, dict) else None
        flight = _pick_active_flight(flights if isinstance(flights, list) else [])
        if flight is None:
            METRICS.incr("flightaware.notfound")
            return None

        origin = _airport_code(flight.get("origin"))
        destination = _airport_code(flight.get("destination"))
        if not origin and not destination:
            METRICS.incr("flightaware.notfound")
            return None  # flight known but no usable route

        METRICS.incr("flightaware.found")
        airline = (
            airline_from_callsign(callsign)
            or airline_from_icao(flight.get("operator"))
            or flight.get("operator_iata")
            or flight.get("operator")
            or "Unknown Airline"
        )
        return FlightMeta(
            airline=airline,
            model=flight.get("aircraft_type") or "Unknown",
            origin=origin or "N/A",
            origin_name=_airport_name(flight.get("origin")),
            destination=destination or "N/A",
            destination_name=_airport_name(flight.get("destination")),
        )
