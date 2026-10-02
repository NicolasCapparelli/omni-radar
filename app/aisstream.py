"""aisstream.io WebSocket client — live AIS ingest (marine's required source).

The marine analog of ``opensky.py``, but a *push* stream rather than a poll.
A long-lived task connects to ``wss://stream.aisstream.io/v0/stream``, sends a
subscription (API key + bounding box + message-type filter), then feeds every
position / static-data message into a :class:`VesselStore`. On any drop it
reconnects with capped exponential backoff.

Subscription + message shapes verified against the aisstream models:
https://github.com/aisstream/ais-message-models
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

import websockets

from .geo import BoundingBox
from .metrics import METRICS
from .vessel_store import VesselStore

logger = logging.getLogger("traffic_radar.aisstream")

DEFAULT_WS_URL = "wss://stream.aisstream.io/v0/stream"

POSITION_TYPES = {"PositionReport", "StandardClassBPositionReport",
                  "ExtendedClassBPositionReport"}
STATIC_TYPES = {"ShipStaticData"}
SUBSCRIBE_TYPES = ["PositionReport", "StandardClassBPositionReport",
                   "ExtendedClassBPositionReport", "ShipStaticData"]

# Reconnect backoff bounds (seconds).
_BACKOFF_START_S = 2.0
_BACKOFF_MAX_S = 60.0


def _available(value, limit: float) -> Optional[float]:
    """Return ``value``, or ``None`` for AIS's "not available" sentinels.

    AIS encodes missing fields as out-of-range values (ITU-R M.1371): latitude
    91, longitude 181, SOG 102.3 kn and COG 360. ``limit`` is the first
    sentinel value; anything at or beyond it in magnitude is unavailable.
    """
    if not isinstance(value, (int, float)) or abs(value) >= limit:
        return None
    return value


def _format_eta(eta: Optional[dict]) -> str:
    """Format an AIS ETA object ({Month,Day,Hour,Minute}) as 'MM-DD HH:MM'."""
    if not isinstance(eta, dict):
        return ""
    month, day = eta.get("Month") or 0, eta.get("Day") or 0
    hour, minute = eta.get("Hour") or 0, eta.get("Minute") or 0
    if not month and not day:
        return ""
    return f"{month:02d}-{day:02d} {hour:02d}:{minute:02d}"


class AisStreamClient:
    """Maintains one aisstream subscription for a bounding box, feeding a store."""

    def __init__(
        self,
        api_key: str,
        box: BoundingBox,
        store: VesselStore,
        ws_url: str = DEFAULT_WS_URL,
    ) -> None:
        self._api_key = api_key
        self._box = box
        self._store = store
        self._ws_url = ws_url

    def _subscription(self) -> dict:
        return {
            "APIKey": self._api_key,
            "BoundingBoxes": self._box.as_aisstream_bbox(),
            "FilterMessageTypes": SUBSCRIBE_TYPES,
        }

    async def run(self) -> None:
        """Connect-subscribe-ingest loop with reconnect backoff.

        Runs until cancelled. Each successful connection resets the backoff.
        """
        backoff = _BACKOFF_START_S
        while True:
            try:
                async with websockets.connect(
                    self._ws_url, ping_interval=20, ping_timeout=20
                ) as ws:
                    await ws.send(json.dumps(self._subscription()))
                    METRICS.set_gauge("ais.ws_connected", 1)
                    logger.info("aisstream connected for box %s", self._box)
                    backoff = _BACKOFF_START_S
                    async for raw in ws:
                        await self._handle_message(raw)
            except asyncio.CancelledError:
                METRICS.set_gauge("ais.ws_connected", 0)
                logger.info("aisstream ingest cancelled for box %s", self._box)
                raise
            except Exception as exc:  # noqa: BLE001
                METRICS.set_gauge("ais.ws_connected", 0)
                METRICS.incr("ais.ws_reconnects")
                logger.warning(
                    "aisstream connection lost (%s); reconnecting in %.0fs",
                    exc, backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _BACKOFF_MAX_S)

    async def _handle_message(self, raw: str | bytes) -> None:
        """Parse one aisstream frame and merge it into the store."""
        try:
            msg = json.loads(raw)
        except (ValueError, TypeError):
            return
        if not isinstance(msg, dict):
            return

        # An error frame (e.g. bad subscription) arrives as {"error": "..."}.
        if "error" in msg and "MessageType" not in msg:
            logger.error("aisstream error frame: %s", msg.get("error"))
            return

        msg_type = msg.get("MessageType")
        body = (msg.get("Message") or {}).get(msg_type) or {}
        meta = msg.get("MetaData") or {}
        mmsi = body.get("UserID") or meta.get("MMSI")
        if not mmsi:
            return
        METRICS.incr("ais.messages_received")
        # aisstream includes ShipName in the metadata of every frame, so names
        # populate immediately rather than waiting for the ~6-min static report.
        meta_name = (meta.get("ShipName") or "").strip()

        if msg_type in POSITION_TYPES:
            await self._store.update_position(
                mmsi=int(mmsi),
                latitude=_available(body.get("Latitude"), 91),
                longitude=_available(body.get("Longitude"), 181),
                sog_knots=_available(body.get("Sog"), 102.3),
                cog_degrees=_available(body.get("Cog"), 360),
                true_heading=body.get("TrueHeading"),
                nav_status=body.get("NavigationalStatus"),
                name=meta_name,
            )
            METRICS.incr("ais.position_reports")
        elif msg_type in STATIC_TYPES:
            await self._store.update_static(
                mmsi=int(mmsi),
                name=body.get("Name", "") or meta_name,
                callsign=body.get("CallSign", "") or "",
                imo_number=body.get("ImoNumber", 0) or 0,
                ship_type=body.get("Type", 0) or 0,
                dimension=body.get("Dimension"),
                draught_m=body.get("MaximumStaticDraught", 0.0) or 0.0,
                destination=body.get("Destination", "") or "",
                eta=_format_eta(body.get("Eta")),
            )
            METRICS.incr("ais.static_reports")
