# Omni-Radar Hardware Firmware

> *Migrated into Continuity on 2026-10-02 from `hardware/README.md`; original text unchanged apart from link repair and this note. Its status table and touch-bus note are stale (radar view, touch buttons, and SET settings are implemented; touch shares the display SPI bus). Paths such as `include/` are relative to `hardware/`. Differences from current code: [status → Documentation drift](../status.md#documentation-drift).*

Firmware for the physical Omni-Radar device — an **ESP32-3248S035** (Hosyond /
Sunton 3.5" board): ESP32-WROOM + 480×320 **ST7796** SPI TFT + XPT2046 resistive
touch, micro-USB. It polls the middleware's `GET /api/nearby` over WiFi and shows
the tracked aircraft on the LCD, cycling through targets every 5s.

This is the real-hardware counterpart to the `web/` emulator, which previews the
same layout in a browser.

## Status

| Feature | State |
| --- | --- |
| WiFi connect | ✅ |
| Poll `/api/nearby` + adaptive interval (`X-Recommended-Poll-Seconds`) | ✅ |
| JSON parse (field-filtered for a PSRAM-less heap) | ✅ |
| AIR data card (mirrors `device.js#renderAircraftCard`) | ✅ |
| Auto-cycle through targets (5s) | ✅ |
| MARINE mode (`/api/marine`) | ⏳ TODO |
| Radar view | ⏳ TODO |
| Touch "buttons" (power / mode / view / action) | ⏳ TODO |

## Prerequisites

- [PlatformIO](https://platformio.org/) (VS Code extension or `pio` CLI).
- The middleware running and reachable on your LAN (`python -m app.main`).
- A **data-capable micro-USB cable** (not charge-only).

## Setup

```powershell
cd hardware
Copy-Item include/config.example.h include/config.h
# edit include/config.h:
#   WIFI_SSID / WIFI_PASSWORD
#   MIDDLEWARE_BASE_URL  -> http://<your-PC-LAN-IP>:8000   (not localhost!)
#   HOME_LAT / HOME_LON / RADIUS_MILES (optional; else middleware .env defaults)
```

## Build & flash

```powershell
pio run                 # compile
pio run --target upload # flash over USB
pio device monitor      # serial log @ 115200
```

If PlatformIO doesn't auto-detect the port, pass it: `pio run -t upload --upload-port COM5`.

## Pin map (ESP32-3248S035)

Display pins are set for TFT_eSPI in `platformio.ini` (`build_flags`); the rest
live in `include/board_pins.h`.

| Function | GPIO | Notes |
| --- | --- | --- |
| TFT MISO / MOSI / SCLK | 12 / 13 / 14 | ST7796, HSPI |
| TFT CS / DC / RST | 15 / 2 / -1 | RST tied to EN |
| TFT backlight | 27 | active HIGH |
| Touch (XPT2046) MOSI/MISO/CLK/CS/IRQ | 32 / 39 / 25 / 33 / 36 | separate SPI bus |
| RGB LED R/G/B | 4 / 16 / 17 | active LOW |
| LDR (light sensor) | 34 | analog |
| Speaker | 26 | via transistor |

> ⚠ **Verify on arrival.** These are the standard ESP32-3248S035 GPIOs. If the
> screen stays white/blank after flashing, the pin map or driver is the usual
> culprit — recheck against the schematic/sticker that shipped with the board.
> Also confirm it's the **ST7796** driver (some batches ship ILI9488).

## Troubleshooting

- **White screen** → wrong display pins or driver; see the note above.
- **Blank/black but backlit** → check `TFT_BL` (27) and `setRotation(1)`.
- **WiFi connects, no data** → `MIDDLEWARE_BASE_URL` must be the PC's LAN IP and
  the middleware must be bound to `0.0.0.0` (it is by default). Test the URL in a
  browser: `http://<PC-IP>:8000/api/nearby?radius=15`.
- **Colours inverted / mirrored** → tune `setRotation()` or add `TFT_INVERSION_ON`.
