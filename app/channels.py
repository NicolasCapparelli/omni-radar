"""Marine channels: independently-addressable monitored areas.

Each channel (``/api/marine/{channel}/...``) owns its own bounding box, its own
:class:`VesselStore`, and its own aisstream ingest task. Channels are:

  * **lazily opened** on first request (a cold channel re-warms from the stream);
  * **idle-expired** after ``idle_ttl_ms`` (default 8h) without a request, so we
    don't hold WebSockets for areas nobody is watching;
  * **re-pointable** to new coordinates (tears down + reopens the subscription).

A single background reaper closes idle channels and sweeps each store. This is
the marine counterpart to the AIR ``run_gc_loop``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from .aisstream import AisStreamClient, DEFAULT_WS_URL
from .geo import BoundingBox
from .metrics import METRICS
from .vessel_store import VesselState, VesselStore

logger = logging.getLogger("traffic_radar.channels")


def _now_ms() -> float:
    return time.time() * 1000.0


@dataclass
class Channel:
    """One active monitored area: box + store + ingest task + idle clock."""

    key: str
    box: BoundingBox
    store: VesselStore
    task: asyncio.Task
    last_access_ms: float = field(default_factory=_now_ms)

    def touch(self) -> None:
        self.last_access_ms = _now_ms()


class ChannelManager:
    """Registry of lazily-opened, idle-expiring marine channels."""

    def __init__(
        self,
        api_key: str,
        vessel_ttl_ms: int,
        idle_ttl_ms: int,
        ws_url: str = DEFAULT_WS_URL,
    ) -> None:
        self._api_key = api_key
        self._vessel_ttl_ms = vessel_ttl_ms
        self._idle_ttl_ms = idle_ttl_ms
        self._ws_url = ws_url
        self._channels: dict[str, Channel] = {}
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    def _open(self, key: str, box: BoundingBox) -> Channel:
        """Create a store + ingest task for a new channel (caller holds lock)."""
        store = VesselStore(ttl_ms=self._vessel_ttl_ms)
        client = AisStreamClient(self._api_key, box, store, ws_url=self._ws_url)
        task = asyncio.create_task(client.run(), name=f"ais-channel-{key}")
        logger.info("Opened marine channel %r for box %s", key, box)
        return Channel(key=key, box=box, store=store, task=task)

    async def snapshot(
        self, key: str, box: BoundingBox
    ) -> tuple[list[VesselState], BoundingBox]:
        """Return a store snapshot for ``key``, opening the channel if cold.

        Resets the channel's idle clock. Returns the snapshot plus the channel's
        actual subscription box (which the caller uses to filter).
        """
        async with self._lock:
            channel = self._channels.get(key)
            if channel is None or channel.task.done():
                channel = self._open(key, box)
                self._channels[key] = channel
            channel.touch()
        return await channel.store.snapshot(), channel.box

    async def repoint(self, key: str, box: BoundingBox) -> None:
        """Move a channel to a new box: tear down and reopen its subscription."""
        async with self._lock:
            existing = self._channels.get(key)
            if existing is not None:
                await self._cancel(existing)
            self._channels[key] = self._open(key, box)
        logger.info("Re-pointed marine channel %r to box %s", key, box)

    @staticmethod
    async def _cancel(channel: Channel) -> None:
        """Cancel a channel's ingest task and await its shutdown."""
        channel.task.cancel()
        try:
            await channel.task
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # noqa: BLE001
            logger.warning("Channel %r task errored on close: %s", channel.key, exc)

    async def reap_once(self) -> int:
        """Close idle channels and sweep stores. Returns channels closed."""
        now = _now_ms()
        async with self._lock:
            idle = [
                ch for ch in self._channels.values()
                if now - ch.last_access_ms > self._idle_ttl_ms
            ]
            for ch in idle:
                await self._cancel(ch)
                self._channels.pop(ch.key, None)
                logger.info("Closed idle marine channel %r (8h+ no requests)", ch.key)
            # Sweep surviving stores so stale vessels age out.
            for ch in self._channels.values():
                await ch.store.sweep()
            METRICS.set_gauge("marine.channels_active", len(self._channels))
        return len(idle)

    async def close_all(self) -> None:
        """Cancel every channel's ingest task (used on shutdown)."""
        async with self._lock:
            for ch in self._channels.values():
                await self._cancel(ch)
            self._channels.clear()

    def stats(self) -> dict:
        """Per-channel sizes + active count, for /health and metrics."""
        return {
            "active": len(self._channels),
            "channels": {
                key: {
                    "vessels": ch.store.size,
                    "idle_seconds": int((_now_ms() - ch.last_access_ms) / 1000),
                    "connected": ch.task is not None and not ch.task.done(),
                }
                for key, ch in self._channels.items()
            },
        }


async def run_reaper_loop(manager: ChannelManager, interval_ms: int) -> None:
    """Background task: periodically reap idle channels and sweep stores."""
    interval_s = interval_ms / 1000.0
    logger.info("Marine channel reaper started (every %.0fs)", interval_s)
    try:
        while True:
            await asyncio.sleep(interval_s)
            await manager.reap_once()
    except asyncio.CancelledError:
        logger.info("Marine channel reaper stopped")
        raise
