// ─────────────────────────────────────────────────────────────────────────────
// ESP32-3248S035 pin reference (Hosyond / Sunton 3.5" ST7796 board).
//
// The DISPLAY pins are configured for TFT_eSPI in platformio.ini (build_flags),
// not here — this header documents the rest of the board (touch, LED, LDR,
// speaker) for the features we'll wire up next (touch buttons, radar view).
//
// ⚠ VERIFY ON ARRIVAL against the board's own schematic/sticker.
// ─────────────────────────────────────────────────────────────────────────────
#pragma once

// ── Display (ST7796, HSPI) — mirrored from platformio.ini for reference ──────
// TFT_MISO 12 · TFT_MOSI 13 · TFT_SCLK 14 · TFT_CS 15 · TFT_DC 2 · TFT_RST -1

// Backlight — driven by firmware via LEDC PWM (NOT TFT_eSPI's TFT_BL), so
// brightness is adjustable. Active HIGH.
#define BL_PIN   27

// ── Resistive touch (XPT2046) ─────────────────────────────────────────────────
// On THIS 3.5" board the XPT2046 SHARES the display SPI bus (SCLK 14, MOSI 13,
// MISO 12); only CS and IRQ are separate. TFT_eSPI drives it via TOUCH_CS=33
// (set in platformio.ini) — no dedicated SPI bus/library. IRQ is unused.
#define XPT2046_CS     33
#define XPT2046_IRQ    36   // not currently used

// Raw touch range → screen mapping (landscape, rotation 1). Starting estimates;
// the firmware logs raw touch values to serial so we can tap the corners and
// dial these in.
// This panel's touch axes are SWAPPED vs the display and both inverted:
// getTouchRaw(rx, ry) -> rx tracks the vertical axis, ry the horizontal axis.
// Measured from button taps: left ry~3650, right ry~600, top rx~3600, bottom rx~350.
#define TS_RAW_X_LEFT    3650   // ry at the left screen edge
#define TS_RAW_X_RIGHT   600    // ry at the right screen edge
#define TS_RAW_Y_TOP     3600   // rx at the top screen edge
#define TS_RAW_Y_BOTTOM  350    // rx at the bottom screen edge

// ── On-board RGB LED (common anode → active LOW) ─────────────────────────────
#define LED_RED        4
#define LED_GREEN      16
#define LED_BLUE       17

// ── Ambient light sensor (LDR, analog) ───────────────────────────────────────
#define LDR_PIN        34

// ── Speaker / buzzer (via transistor) ────────────────────────────────────────
#define SPEAKER_PIN    26
