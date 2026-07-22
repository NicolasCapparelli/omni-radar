# MARINE DevGuide

Internal developer documentation for the **marine** half of Omni-Radar — live
vessel tracking via AIS, mirroring the aircraft ("AIR") implementation as
closely as possible while keeping a **hard external cutoff** between the two.

> Status: **design / planning**. This folder captures the agreed design before
> implementation. No marine code exists yet.

## The guiding principle: mirror AIR, separate externally

The marine side reuses AIR's philosophy and, where sensible, its backend
building blocks (bounding-box math, throttling, metrics, the FastAPI app). But
**everything user-facing is fully separated**:

- Marine lives under its own URI namespace: `/api/marine/...` (AIR stays on
  `/api/nearby`).
- Marine has its own payload schema (`VesselPayload`), distinct from
  `AircraftPayload` — overlapping concepts (speed, heading, country) but
  different fields (draught, ETA, nav status, dimensions; no altitude/squawk).
- Marine has its own metrics namespace and its own docs (this folder).

There is no shared external surface: an AIR client never sees marine data and
vice-versa.

## The other big difference: push, not poll

AIR's source (OpenSky) is a REST bounding-box **poll** — one call per client
request. Marine's source (aisstream.io) is a persistent **WebSocket** that
*pushes* AIS messages for a subscribed area. We can't poll it per request, so
the marine side maintains long-lived WebSocket connections that feed an
in-memory vessel store, and serves client requests out of that store with **zero
per-request external calls**. See [architecture.md](architecture.md).

## Channels

Rather than a single mutable "home" area, marine exposes **channels** — multiple
independently-addressable monitored areas, each with its own coordinates and its
own WebSocket subscription:

```
/api/marine/{channel}/nearby?lat&lon&radius
```

Each channel's WebSocket is opened lazily on first request and stays alive for
**8 hours from the last request** to that channel, then shuts down to save on
monitoring. A later request re-opens it for a fresh 8 hours. See the "Channels"
section of [architecture.md](architecture.md).

## Contents

- [architecture.md](architecture.md) — how the marine middleware works
  end-to-end: the WebSocket ingest, the in-memory vessel store, channel
  lifecycle, local enrichment, and the AIR↔MARINE module mapping.
- [external-dependencies.md](external-dependencies.md) — every external service /
  data source the marine side relies on: aisstream.io (free primary), the
  optional paid fallback, and the offline AIS reference tables.

## Relationship to the AIR DevGuide

This folder is the marine counterpart to the top-level DevGuide
([../architecture.md](../architecture.md),
[../external-dependencies.md](../external-dependencies.md)). Read the AIR docs
first if you haven't — the marine design is deliberately a parallel of it.
