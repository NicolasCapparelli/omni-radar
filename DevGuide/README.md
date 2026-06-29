# DevGuide

Internal developer documentation for the Omni-Radar project.

## Contents
- [architecture.md](architecture.md) — how the middleware works end-to-end and
  all the local work it does to avoid external API usage.
- [web-console.md](web-console.md) — structure of the `web/` debug console
  (ES modules, HTML partials, dependency graph, how to extend).
- [external-dependencies.md](external-dependencies.md) — every external service /
  data source we depend on: auth, limits, costs, role, and how we mitigate them.
  Includes OpenSky credit budgets and polling guidance.
