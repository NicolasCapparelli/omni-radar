# Web Console Architecture

> *Migrated into Continuity on 2026-10-02 from `DevGuide/web-console.md`; original text unchanged apart from link repair and this note. It predates marine support in the console (see `console.js` `scanMarine`). Differences from current code: [status → Documentation drift](../status.md#documentation-drift).*

The web console (`web/`) is a dependency-free, no-build static app: native ES
modules + HTML partials served by a tiny stdlib Python proxy (`serve.py`). It
exists for development/debugging — to exercise the middleware API and preview
how each aircraft renders on the 320×240 hardware LCD.

> Run: start the API (`python -m app.main`), then `python serve.py` from `web/`,
> and open http://localhost:8080. See [user/web-console.md](../user/web-console.md).

## Layout

```
web/
├── index.html          # shell: <head> + three empty mount points
├── styles.css          # all styling (cream/gold chrome + dark LCD theme)
├── serve.py            # static server + /api & /health proxy (stdlib only)
├── partials/           # HTML fragments injected at runtime
│   ├── topbar.html     #   brand + Console/Usage nav + connection dot
│   ├── console.html    #   device emulator + test console (the two columns)
│   └── usage.html      #   usage/metrics dashboard
└── js/                 # ES modules
    ├── state.js        # shared mutable state + constants
    ├── dom.js          # $ = getElementById
    ├── format.js       # pure formatting/geometry helpers (no DOM, no state)
    ├── api.js          # fetch wrappers for the middleware endpoints
    ├── status.js       # connection dot + status strip (/health)
    ├── table.js        # aircraft results table (render + row clicks)
    ├── device.js       # the LCD emulator + hardware buttons + auto-cycle
    ├── console.js      # request bar, SCAN, adaptive live refresh
    ├── usage.js        # Usage tab: metrics fetch/render + tab switch
    └── main.js         # entry point: load partials, wire modules, init
```

## Why these boundaries

Each module owns one concern:

- **`state.js`** is the single source of truth (selected aircraft, mode, track
  mode, view, the last-scanned home position, timers). Everything else reads it.
- **`format.js`** is pure — formatting, icons, and the bearing/distance math.
  Trivially testable, no side effects.
- **`api.js`** is the only place that knows endpoint shapes/URLs.
- The **view modules** (`status`, `table`, `device`, `usage`) each own one
  region of the DOM and expose `render*`/`init*` functions. They read `state`
  and `format`; they do not talk to each other.
- **`console.js`** orchestrates a scan: fetch → render table → update status →
  select first result.
- **`main.js`** is the controller/composition root.

## Dependency graph (acyclic)

```
            state ── format ── dom        api
              ▲        ▲        ▲           ▲
              │        │        │           │
   ┌──────────┼────────┼────────┼───────────┼─────────┐
 status     table    device   console     usage
              ▲        ▲        ▲
              └────────┴────────┴──── main (defines select, wires everything)
```

The one piece of cross-cutting state — **which aircraft is selected** — is
deliberately *not* baked into any view. `select(i)` is defined in `main.js`,
which then refreshes the table highlight, the device, and the raw-JSON panel.
It is **injected** into the modules that need to change the selection:

- `device.initDevice(select)` — so the auto-cycle timer and the ACTION "step"
  button can advance the selection.
- `console.initConsole({ select, onRowSelect })` — so a scan can select the
  first result.
- `table.renderTable(onRowSelect)` — row clicks call back without the table
  knowing what selection means.

This injection is what keeps the graph acyclic: no view module imports another
view module. To add a new consumer of selection, inject the callback the same
way rather than importing a sibling.

## HTML partials

`index.html` is just a shell with three mount points:

```html
<header class="topbar" data-partial="topbar"></header>
<main class="workspace" id="consoleView" data-partial="console"></main>
<main class="usage-view" id="usageView" hidden data-partial="usage"></main>
```

On load, `main.js#loadPartials()` finds every `[data-partial]`, fetches
`partials/<name>.html`, and injects it. Only after all partials are in the DOM
does it wire up modules and run the first scan. This keeps markup in real,
editable `.html` files (not template strings) without needing a bundler. If a
partial fails to load, an error banner is shown instead of a half-wired UI.

## Data flow of a scan

```
SCAN / live tick ─► console.scan()
   ├─ api.getNearby()                 → aircraft[] + X-Recommended-Poll-Seconds
   ├─ table.renderTable(onRowSelect)  → rows (click → onRowSelect → lock + select)
   ├─ status strip update + status.refreshHealth()
   └─ select(0) ─► table.highlightRow() + device.renderDevice() + raw JSON
```

The device's auto-cycle timer and the ACTION button call the same `select`,
so the LCD, the table highlight, and the radar all stay in sync regardless of
how the selection changed.

## Adaptive live refresh

`console.js` schedules the next poll with `setTimeout` (not a fixed interval).
The effective interval is `max(user baseline, server recommendation, 5s)`,
where the server recommendation comes from the `X-Recommended-Poll-Seconds`
header on `/api/nearby` (the middleware raises it as OpenSky credits run low).

## serve.py

A ~90-line stdlib `ThreadingHTTPServer`:
- serves the static files in `web/`, and
- reverse-proxies `/api/*` and `/health` to the middleware (forwarding `X-`
  headers like `X-Recommended-Poll-Seconds`),

so the browser uses a single origin and the API needs no CORS changes. It has no
dependencies and is intentionally a single small script.

## Extending

- **New API field on the device card** → add markup to `partials/console.html`,
  populate it in `device.js#renderCard()`.
- **New table column** → `partials/console.html` header + `table.js#rowHtml()`
  (keep the `colspan` in sync).
- **New metric** → add it to `app/metrics.py`, render it in `usage.js`.
- **New view/tab** → add a partial + mount point, a render module, and a nav
  button handled in `usage.js#showView` (or generalize the switch).
