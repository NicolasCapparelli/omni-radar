// ─────────────────────────────────────────────────────────────────────────────
// Device configuration — copy this file to `config.h` and fill in your values.
//
//   cp include/config.example.h include/config.h    (then edit config.h)
//
// config.h is gitignored (it holds your WiFi password), mirroring the repo's
// .env / .env.example convention on the middleware side.
// ─────────────────────────────────────────────────────────────────────────────
#pragma once

// ── WiFi ────────────────────────────────────────────────────────────────────
#define WIFI_SSID       "your-ssid"
#define WIFI_PASSWORD   "your-password"

// ── Middleware ────────────────────────────────────────────────────────────────
// Base URL of the Omni-Radar middleware (the FastAPI app in app/main.py).
// Use the LAN IP of the machine running it, not "localhost" — the ESP32 needs a
// routable address. Default middleware port is 8000 (see .env → PORT).
#define MIDDLEWARE_BASE_URL   "http://192.168.1.100:8000"

// ── Search location + radius ─────────────────────────────────────────────────
// Sent as query params to /api/nearby. If left at 0/0 the device omits them and
// the middleware falls back to its own HOME_LAT / HOME_LON / DEFAULT_RADIUS_MILES.
#define HOME_LAT        40.7580f
#define HOME_LON        -73.9965f
#define RADIUS_MILES    15

// ── Timing ────────────────────────────────────────────────────────────────────
// Fallback poll interval (seconds) used until the middleware advertises one via
// the X-Recommended-Poll-Seconds response header. Floor is 5s (OpenSky refresh).
#define POLL_DEFAULT_SECONDS   30
#define POLL_MIN_SECONDS       5

// How often the display advances to the next tracked target (auto-cycle), in ms.
// Matches the emulator's 5s SCROLL_MS.
#define CYCLE_INTERVAL_MS      5000
