"""In-memory look-aside cache for flight route metadata, keyed by callsign.

Caching taxonomy (set by the enrichment layer):
  * route found      -> long TTL (routes are static for a flight's life);
  * route not found  -> shorter "negative" TTL (don't re-query known-empty);
  * transient failure-> not cached (retry on the next poll).

The cache is persisted to disk so restarts reuse already-resolved routes
instead of re-hitting the upstream providers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("traffic_radar.cache")


@dataclass
class FlightMeta:
    """Enriched, cacheable metadata for a single callsign."""

    airline: str = "Unknown Airline"
    model: str = "Unknown"
    origin: str = "N/A"
    origin_name: str = "Unknown Route"
    destination: str = "N/A"
    destination_name: str = "Unknown Route"
    is_placeholder: bool = False


@dataclass
class _CacheEntry:
    value: FlightMeta
    expires_at_ms: float


def _now_ms() -> float:
    return time.time() * 1000.0


class MetadataCache:
    """Async cache of route metadata indexed by flight callsign, with disk persistence."""

    def __init__(self, default_ttl_ms: int, persist_path: Optional[str] = None) -> None:
        self._default_ttl_ms = default_ttl_ms
        self._persist_path = Path(persist_path) if persist_path else None
        self._store: dict[str, _CacheEntry] = {}
        self._lock = asyncio.Lock()

    async def get(self, callsign: str) -> Optional[FlightMeta]:
        """Return cached metadata if present and unexpired, else ``None``."""
        async with self._lock:
            entry = self._store.get(callsign)
            if entry is None:
                return None
            if entry.expires_at_ms <= _now_ms():
                self._store.pop(callsign, None)
                return None
            return entry.value

    async def set(
        self, callsign: str, value: FlightMeta, ttl_ms: Optional[int] = None
    ) -> None:
        """Store metadata; ``ttl_ms`` overrides the default TTL when given."""
        ttl = self._default_ttl_ms if ttl_ms is None else ttl_ms
        async with self._lock:
            self._store[callsign] = _CacheEntry(
                value=value, expires_at_ms=_now_ms() + ttl
            )

    async def sweep(self) -> int:
        """Evict all expired entries. Returns the number removed."""
        now = _now_ms()
        async with self._lock:
            expired = [k for k, e in self._store.items() if e.expires_at_ms <= now]
            for k in expired:
                self._store.pop(k, None)
        if expired:
            logger.debug("GC swept %d expired cache entries", len(expired))
        return len(expired)

    @property
    def size(self) -> int:
        return len(self._store)

    # ── Persistence ──────────────────────────────────────────────────────
    def load(self) -> int:
        """Load persisted entries (skipping expired). Returns count loaded.

        Synchronous and safe to call once at startup before serving. Failures
        are swallowed so a corrupt/missing file never blocks startup.
        """
        if not self._persist_path or not self._persist_path.exists():
            return 0
        try:
            raw = json.loads(self._persist_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not read route cache %s: %s", self._persist_path, exc)
            return 0

        now = _now_ms()
        loaded = 0
        for callsign, item in (raw or {}).items():
            try:
                expires = float(item["expires_at_ms"])
                if expires <= now:
                    continue
                meta = FlightMeta(**item["value"])
            except (KeyError, TypeError, ValueError):
                continue
            self._store[callsign] = _CacheEntry(value=meta, expires_at_ms=expires)
            loaded += 1
        logger.info("Loaded %d cached routes from %s", loaded, self._persist_path)
        return loaded

    async def save(self) -> None:
        """Persist unexpired entries to disk atomically (off the event loop)."""
        if not self._persist_path:
            return
        now = _now_ms()
        async with self._lock:
            snapshot = {
                callsign: {
                    "value": asdict(entry.value),
                    "expires_at_ms": entry.expires_at_ms,
                }
                for callsign, entry in self._store.items()
                if entry.expires_at_ms > now
            }
        await asyncio.to_thread(self._write_json, snapshot)

    def _write_json(self, snapshot: dict) -> None:
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._persist_path.with_suffix(self._persist_path.suffix + ".tmp")
            tmp.write_text(json.dumps(snapshot), encoding="utf-8")
            tmp.replace(self._persist_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not persist route cache: %s", exc)


async def run_gc_loop(
    cache: MetadataCache, interval_ms: int, persist: bool = True
) -> None:
    """Background task: periodically sweep expired entries and persist the cache."""
    interval_s = interval_ms / 1000.0
    logger.info("Cache GC loop started (every %.0fs)", interval_s)
    try:
        while True:
            await asyncio.sleep(interval_s)
            removed = await cache.sweep()
            if persist:
                await cache.save()
            logger.debug("GC pass complete; removed=%d size=%d", removed, cache.size)
    except asyncio.CancelledError:
        logger.info("Cache GC loop stopped")
        raise
