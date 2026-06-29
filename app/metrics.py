"""Lightweight in-process usage metrics (for the test console).

A single process-wide counter store tracks external API calls per provider and
the work served locally (cache hits, grounded-plane filtering, offline aircraft
DB enrichment). Counters are session-scoped — they reset on restart or via the
``/api/metrics/reset`` endpoint. Increments happen on the asyncio event loop
(single-threaded), so plain integer counters are safe without locking.
"""

from __future__ import annotations

import time
from collections import defaultdict


class Metrics:
    def __init__(self) -> None:
        self._c: dict[str, int] = defaultdict(int)
        self._g: dict[str, float] = {}
        self._started = time.time()

    def incr(self, key: str, n: int = 1) -> None:
        self._c[key] += n

    def set_gauge(self, key: str, value: float) -> None:
        self._g[key] = value

    def gauge(self, key: str, default=None):
        return self._g.get(key, default)

    def reset(self) -> None:
        self._c.clear()
        self._g.clear()
        self._started = time.time()

    def recommended_poll_seconds(self, default: int, minimum: int) -> int:
        """Suggest a poll interval that backs off as OpenSky credits run low."""
        remaining = self._g.get("opensky.credits_remaining")
        retry = self._g.get("opensky.retry_after_seconds")
        if remaining is None:
            rec = default
        elif remaining <= 0:
            rec = max(default, int(retry or 60))
        elif remaining < 200:
            rec = default * 4
        elif remaining < 1000:
            rec = default * 2
        else:
            rec = default
        return max(minimum, int(rec))

    def snapshot(self) -> dict:
        c = self._c
        opensky = c["opensky.requests"]
        adsbdb = c["adsbdb.requests"]
        fa = c["flightaware.requests"]
        total_external = opensky + adsbdb + fa

        cache_hits = c["routes.cache_hits"]
        filtered = c["enrich.planes_filtered"]
        offline_db = c["aircraftdb.hits"]
        avoided = cache_hits + filtered

        # Of all the route lookups a "naive" implementation would have made
        # (one per tracked aircraft), how many did we serve without a call?
        naive_lookups = cache_hits + filtered + c["routes.cache_misses"]
        local_ratio = (avoided / naive_lookups) if naive_lookups else 0.0

        return {
            "uptime_seconds": int(time.time() - self._started),
            "requests": {
                "nearby": c["requests.nearby"],
                "aircraft_returned": c["aircraft.returned"],
            },
            "external_calls": {
                "total": total_external,
                "opensky": {
                    "requests": opensky,
                    "errors": c["opensky.errors"],
                    "rate_limited": c["opensky.rate_limited"],
                    "credits_remaining": self._g.get("opensky.credits_remaining"),
                    "retry_after_seconds": self._g.get("opensky.retry_after_seconds"),
                },
                "adsbdb": {
                    "requests": adsbdb,
                    "found": c["adsbdb.found"],
                    "not_found": c["adsbdb.notfound"],
                    "rate_limited": c["adsbdb.rate_limited"],
                    "errors": c["adsbdb.errors"],
                },
                "flightaware": {
                    "requests": fa,
                    "found": c["flightaware.found"],
                    "not_found": c["flightaware.notfound"],
                    "rate_limited": c["flightaware.rate_limited"],
                    "errors": c["flightaware.errors"],
                },
            },
            "savings": {
                "cache_hits": cache_hits,
                "cache_misses": c["routes.cache_misses"],
                "planes_filtered": filtered,
                "offline_db_enrichments": offline_db,
                "calls_avoided_total": avoided,
                "local_served_ratio": round(local_ratio, 4),
            },
            "route_resolution": {
                "found": c["routes.resolved_found"],
                "not_found": c["routes.resolved_notfound"],
                "unavailable": c["routes.resolved_unavailable"],
            },
        }


METRICS = Metrics()
