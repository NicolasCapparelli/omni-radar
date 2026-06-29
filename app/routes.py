"""Shared route-provider plumbing: throttle, exceptions, and resolution.

A *route provider* fetches the origin/destination for a callsign. Providers are
tried in priority order (adsbdb first, FlightAware as optional fallback). The
route is the only thing that needs a network call — everything else (model,
registration, owner, type, airline) comes from the offline aircraft DB and
static tables.

Providers implement:
    enabled: bool
    async fetch_route(callsign) -> FlightMeta | None   # None == known no route
and raise :class:`RouteRateLimited` / :class:`RouteUnavailable` on transient
failures (so resolution defers to the next poll rather than retrying in-line).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, Protocol, Sequence

from .cache import FlightMeta

logger = logging.getLogger("traffic_radar.routes")


class RouteRateLimited(Exception):
    """Provider returned HTTP 429 (rate limited)."""


class RouteUnavailable(Exception):
    """Provider had a transient failure (5xx / network / unexpected status)."""


class RouteProvider(Protocol):
    name: str

    @property
    def enabled(self) -> bool: ...

    async def fetch_route(self, callsign: str) -> Optional[FlightMeta]: ...


class Throttle:
    """Limits concurrency and enforces a minimum interval between request starts."""

    def __init__(self, max_concurrency: int, min_interval_s: float) -> None:
        self._sem = asyncio.Semaphore(max(1, max_concurrency))
        self._min_interval = max(0.0, min_interval_s)
        self._lock = asyncio.Lock()
        self._next_allowed = 0.0

    async def __aenter__(self) -> "Throttle":
        await self._sem.acquire()
        if self._min_interval > 0:
            async with self._lock:
                loop = asyncio.get_event_loop()
                now = loop.time()
                wait = self._next_allowed - now
                if wait > 0:
                    await asyncio.sleep(wait)
                    now = loop.time()
                self._next_allowed = now + self._min_interval
        return self

    async def __aexit__(self, *_exc) -> None:
        self._sem.release()


async def resolve_route(
    callsign: str, providers: Sequence[RouteProvider]
) -> tuple[Optional[FlightMeta], str]:
    """Try each enabled provider in order.

    Returns ``(meta, status)`` where status is one of:
      * ``"found"``       — a route was resolved (``meta`` set);
      * ``"notfound"``    — providers definitively have no route (``meta`` None);
      * ``"unavailable"`` — only transient failures; caller should retry later.
    """
    transient = False
    for provider in providers:
        if not provider.enabled:
            continue
        try:
            meta = await provider.fetch_route(callsign)
        except RouteRateLimited as exc:
            transient = True
            logger.debug("%s rate-limited for %s: %s", provider.name, callsign, exc)
            continue
        except RouteUnavailable as exc:
            transient = True
            logger.debug("%s unavailable for %s: %s", provider.name, callsign, exc)
            continue
        if meta is not None:
            return meta, "found"
    return (None, "unavailable") if transient else (None, "notfound")
