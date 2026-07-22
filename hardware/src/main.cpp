// ─────────────────────────────────────────────────────────────────────────────
// Omni-Radar device firmware — ESP32-3248S035 (3.5" 480x320 ST7796)
//
// Reproduces the web console's LCD design (web/styles.css + partials/console.html)
// on real hardware: gold-olive header bar, dark phosphor body, glowing accent
// callsign, bordered telemetry box, operator-class chips, and a status footer —
// plus a bottom strip of four touch "buttons" (POWER / MODE / ACTION / ALT) that
// mirror the emulator's hardware buttons.
//
// Data path: WiFi → GET /api/nearby (adaptive poll) → filtered JSON → render.
//
// Implemented: AIR data card, auto-cycle, POWER (sleep/wake), ACTION (auto ↔
//   manual lock + step), touch input with serial-logged raw coords for calibration.
// Stubbed (next): MARINE mode (MODE btn), radar view (ALT btn) — both show a
//   clearly-labelled placeholder for now.
// ─────────────────────────────────────────────────────────────────────────────
#include <Arduino.h>
#include <math.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <TFT_eSPI.h>
#include <Preferences.h>

#include "config.h"
#include "board_pins.h"
#include "fonts/font_big.h"     // jbBig   — JetBrains Mono Bold 40 (headline)
#include "fonts/font_med.h"     // jbMed   — JetBrains Mono Bold 20 (callsign, values)
#include "fonts/font_small.h"   // jbSmall — JetBrains Mono Regular 13 (chrome, names)
#include "flags.h"              // country flag atlas (RGB565, flagcdn)

// ── Serial logging ────────────────────────────────────────────────────────────
#define LOG(...)  do { Serial.printf(__VA_ARGS__); Serial.println(); } while (0)

// ── Display + touch ─────────────────────────────────────────────────────────────
// Touch (XPT2046) shares the display SPI bus and is driven by TFT_eSPI itself
// (TOUCH_CS=33 in platformio.ini) — no separate library/bus needed.
static TFT_eSPI tft = TFT_eSPI();

// Backlight PWM (LEDC channel 0). 5 kHz, 8-bit duty.
static const int BL_CHANNEL = 0;
static void setBacklight(uint8_t level) { ledcWrite(BL_CHANNEL, level); }

static const int SCREEN_W = 480;
static const int SCREEN_H = 320;

// Layout bands (px). The LCD chrome fills the top; touch buttons live below it.
static const int HEADER_H  = 24;
static const int BTN_BAR_H = 46;
static const int FOOTER_H  = 22;
static const int BTN_TOP   = SCREEN_H - BTN_BAR_H;   // 274
static const int FOOTER_TOP = BTN_TOP - FOOTER_H;    // 252
static const int BODY_TOP  = HEADER_H;               // 24
static const int BODY_H    = FOOTER_TOP - HEADER_H;  // 228

// ── Palette (RGB565, matched to web/styles.css :root) ──────────────────────────
static constexpr uint16_t rgb565(uint8_t r, uint8_t g, uint8_t b) {
  return (uint16_t)(((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3));
}
static const uint16_t C_LCD_BG   = rgb565(0x14, 0x14, 0x14);  // --lcd-bg
static const uint16_t C_PRIMARY  = rgb565(0x74, 0x5b, 0x00);  // --primary (header)
static const uint16_t C_ACCENT   = rgb565(0xff, 0xd6, 0x33);  // --lcd-accent (callsign)
static const uint16_t C_DIM      = rgb565(0x9a, 0xa0, 0xa6);  // --lcd-dim
static const uint16_t C_LINE     = rgb565(0x33, 0x3a, 0x33);  // --lcd-line
static const uint16_t C_LGRAY    = rgb565(0xe7, 0xe7, 0xe7);
static const uint16_t C_ERROR    = rgb565(0xba, 0x1a, 0x1a);  // --error
static const uint16_t C_GOLD     = rgb565(0xeb, 0xc2, 0x46);  // --gold (descent)
static const uint16_t C_FOOTER   = rgb565(0x22, 0x22, 0x22);
static const uint16_t C_FOOTTXT  = rgb565(0x8a, 0x8a, 0x8a);
static const uint16_t C_TELE_BG  = rgb565(0x0a, 0x0d, 0x0a);
static const uint16_t C_BTN      = rgb565(0x2a, 0x2a, 0x2a);
static const uint16_t C_BTN_PWR  = rgb565(0xb3, 0x26, 0x1e);

// operator-class chip colors (--c-*)
static uint16_t chipColor(const String& c) {
  if (c == "Commercial") return rgb565(0x25, 0x63, 0xeb);
  if (c == "Cargo")      return rgb565(0xd9, 0x77, 0x06);
  if (c == "Private")    return rgb565(0x6b, 0x72, 0x80);
  if (c == "Military")   return rgb565(0x4d, 0x7c, 0x0f);
  if (c == "Government") return rgb565(0x0d, 0x94, 0x88);
  if (c == "Fishing")    return rgb565(0x08, 0x91, 0xb2);
  if (c == "Pleasure")   return rgb565(0x93, 0x33, 0xea);
  return rgb565(0x9c, 0xa3, 0xaf);  // --c-unknown
}

// Binary-search the flag atlas for an ISO alpha-2 code; nullptr if not found.
static const uint16_t* flagFor(const String& iso) {
  if (iso.length() != 2) return nullptr;
  char a = iso[0], b = iso[1];
  if (a >= 'A' && a <= 'Z') a += 32;
  if (b >= 'A' && b <= 'Z') b += 32;
  int lo = 0, hi = flagCount - 1;
  while (lo <= hi) {
    int m = (lo + hi) / 2;
    const FlagEntry& e = flagIndex[m];
    if (e.c0 < a || (e.c0 == a && e.c1 < b)) lo = m + 1;
    else if (e.c0 > a || (e.c0 == a && e.c1 > b)) hi = m - 1;
    else return &flagPixels[(uint32_t)e.ordinal * FLAG_W * FLAG_H];
  }
  return nullptr;
}

// ── Model ──────────────────────────────────────────────────────────────────────
struct Aircraft {
  String callsign, vehicleType, modelCode, modelName, operatorName;
  String origin, destination, originName, destName;
  String operatorClass, specialDesignation, emergency;
  String originCountry, destCountry;   // ISO alpha-2, for flags
  int altitudeFeet = 0, speedKnots = 0, headingDegrees = 0, verticalSpeed = 0;
  bool onGround = false;
  float lat = 0, lon = 0; bool hasPos = false;   // for the radar plot
};

static const size_t MAX_AIRCRAFT = 60;
static Aircraft aircraft[MAX_AIRCRAFT];
static size_t   aircraftCount = 0;
static int      selected      = 0;

// ── UI state (mirrors the emulator) ──────────────────────────────────────────────
static bool powered   = true;
static bool trackAuto = true;                 // auto-cycle vs manual lock
enum Mode { MODE_AIR, MODE_MARINE };
static Mode mode = MODE_AIR;
enum View { VIEW_DATA, VIEW_RADAR };
static View view = VIEW_DATA;
static bool settingsOpen = false;

// ── User settings (persisted to NVS; defaults from config.h) ──────────────────
struct Settings {
  int cycleSec;       // auto-cycle interval (s)
  int brightnessPct;  // backlight 10-100 %
  int radiusMiles;    // search radius
  int pollSec;        // baseline poll interval (s)
};
static Settings cfg;
static Preferences prefs;

// One editable row: label, unit, value pointer, and adjust range/step.
struct SettingDef { const char* label; const char* unit; int* val; int lo; int hi; int step; };
static SettingDef settingDefs[] = {
  { "Auto-cycle",    "s",  &cfg.cycleSec,      2,  60, 1  },
  { "Brightness",    "%",  &cfg.brightnessPct, 10, 100, 10 },
  { "Search radius", "mi", &cfg.radiusMiles,   5,  100, 5  },
  { "Poll interval", "s",  &cfg.pollSec,       POLL_MIN_SECONDS, 120, 5 },
};
static const int SETTING_COUNT = sizeof(settingDefs) / sizeof(settingDefs[0]);

static uint8_t brightnessDuty() { return (uint8_t)(cfg.brightnessPct * 255 / 100); }

static void loadSettings() {
  prefs.begin("omniradar", false);
  cfg.cycleSec      = prefs.getInt("cycle",  CYCLE_INTERVAL_MS / 1000);
  cfg.brightnessPct = prefs.getInt("bright", (BRIGHTNESS * 100 + 127) / 255);
  cfg.radiusMiles   = prefs.getInt("radius", RADIUS_MILES);
  cfg.pollSec       = prefs.getInt("poll",   POLL_DEFAULT_SECONDS);
}

static void saveSettings() {
  prefs.putInt("cycle",  cfg.cycleSec);
  prefs.putInt("bright", cfg.brightnessPct);
  prefs.putInt("radius", cfg.radiusMiles);
  prefs.putInt("poll",   cfg.pollSec);
}

// ── Timing ───────────────────────────────────────────────────────────────────────
static uint32_t pollIntervalMs = POLL_DEFAULT_SECONDS * 1000UL;
static uint32_t lastPollMs = 0, lastCycleMs = 0;
static bool     firstPollDone = false;
static bool     touchLatched  = false;

// Forward decls
static void renderAll();

// ─────────────────────────────────────────────────────────────────────────────
// WiFi
// ─────────────────────────────────────────────────────────────────────────────
static void connectWifi() {
  tft.fillScreen(C_LCD_BG);
  tft.setTextColor(C_ACCENT, C_LCD_BG);
  tft.setTextDatum(TL_DATUM);
  tft.drawString("OMNI-RADAR", 14, 16, 4);
  tft.setTextColor(C_LGRAY, C_LCD_BG);
  tft.drawString("Connecting to WiFi...", 14, 60, 2);
  tft.setTextColor(C_DIM, C_LCD_BG);
  tft.drawString(WIFI_SSID, 14, 82, 2);

  LOG("[wifi] connecting to SSID '%s'", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) delay(250);

  if (WiFi.status() == WL_CONNECTED) {
    LOG("[wifi] connected, IP=%s", WiFi.localIP().toString().c_str());
    tft.setTextColor(rgb565(0x16, 0xa3, 0x4a), C_LCD_BG);
    tft.drawString("Connected " + WiFi.localIP().toString(), 14, 104, 2);
  } else {
    LOG("[wifi] FAILED to connect");
    tft.setTextColor(C_ERROR, C_LCD_BG);
    tft.drawString("WiFi FAILED - retrying", 14, 104, 2);
  }
  delay(700);
}

// ─────────────────────────────────────────────────────────────────────────────
// Fetch + parse /api/nearby
// ─────────────────────────────────────────────────────────────────────────────
static String buildNearbyUrl() {
  String url = String(MIDDLEWARE_BASE_URL) + "/api/nearby?radius=" + String(cfg.radiusMiles);
  if (HOME_LAT != 0.0f || HOME_LON != 0.0f)
    url += "&lat=" + String(HOME_LAT, 4) + "&lon=" + String(HOME_LON, 4);
  return url;
}

static void buildFilter(JsonDocument& filter) {
  JsonObject o = filter.add<JsonObject>();
  const char* keys[] = {
    "callsign", "vehicle_type", "model_code", "model_name", "airline", "operator",
    "origin", "destination", "origin_name", "destination_name", "operator_class",
    "special_designation", "emergency", "altitude_feet", "speed_knots",
    "heading_degrees", "vertical_speed_fpm", "on_ground",
    "origin_country", "destination_country", "latitude", "longitude"
  };
  for (const char* k : keys) o[k] = true;
}

static void copyAircraft(JsonObjectConst src, Aircraft& dst) {
  dst.callsign           = src["callsign"] | "--------";
  dst.vehicleType        = src["vehicle_type"] | "Plane";
  dst.modelCode          = src["model_code"] | "Unknown";
  dst.modelName          = src["model_name"] | "Unknown";
  const char* op         = src["operator"] | "";
  dst.operatorName       = (op && op[0] && strcmp(op, "Unknown") != 0)
                             ? op : (src["airline"] | "Unknown Airline");
  dst.origin             = src["origin"] | "N/A";
  dst.destination        = src["destination"] | "N/A";
  dst.originName         = src["origin_name"] | "";
  dst.destName           = src["destination_name"] | "";
  dst.operatorClass      = src["operator_class"] | "Unknown";
  dst.specialDesignation = src["special_designation"] | "None";
  dst.emergency          = src["emergency"] | "None";
  dst.originCountry      = src["origin_country"] | "";
  dst.destCountry        = src["destination_country"] | "";
  dst.hasPos             = !src["latitude"].isNull() && !src["longitude"].isNull();
  dst.lat                = src["latitude"] | 0.0f;
  dst.lon                = src["longitude"] | 0.0f;
  dst.altitudeFeet       = src["altitude_feet"] | 0;
  dst.speedKnots         = src["speed_knots"] | 0;
  dst.headingDegrees     = src["heading_degrees"] | 0;
  dst.verticalSpeed      = src["vertical_speed_fpm"] | 0;
  dst.onGround           = src["on_ground"] | false;
}

static bool fetchNearby() {
  if (WiFi.status() != WL_CONNECTED) return false;

  HTTPClient http;
  http.begin(buildNearbyUrl());
  const char* headerKeys[] = { "X-Recommended-Poll-Seconds" };
  http.collectHeaders(headerKeys, 1);

  int code = http.GET();
  if (code != HTTP_CODE_OK) {
    LOG("[poll] HTTP %d", code);
    http.end();
    return false;
  }

  // Effective interval = max(user baseline, server recommendation), floored at min.
  long rec = cfg.pollSec;
  if (http.hasHeader("X-Recommended-Poll-Seconds")) {
    long h = http.header("X-Recommended-Poll-Seconds").toInt();
    if (h > rec) rec = h;
  }
  if (rec < POLL_MIN_SECONDS) rec = POLL_MIN_SECONDS;
  pollIntervalMs = (uint32_t)rec * 1000UL;

  JsonDocument filter; buildFilter(filter);
  JsonDocument doc;
  DeserializationError err = deserializeJson(
      doc, http.getStream(), DeserializationOption::Filter(filter));
  http.end();
  if (err) { LOG("[poll] JSON error: %s", err.c_str()); return false; }

  aircraftCount = 0;
  for (JsonObjectConst obj : doc.as<JsonArrayConst>()) {
    if (aircraftCount >= MAX_AIRCRAFT) break;
    copyAircraft(obj, aircraft[aircraftCount++]);
  }
  if (selected >= (int)aircraftCount) selected = 0;
  int withCountry = 0;
  for (size_t i = 0; i < aircraftCount; i++)
    if (aircraft[i].originCountry.length() || aircraft[i].destCountry.length()) withCountry++;
  LOG("[poll] ok, %u targets (%d with country/flag), next in %lus",
      (unsigned)aircraftCount, withCountry, (unsigned long)(pollIntervalMs / 1000));
  return true;
}

// ─────────────────────────────────────────────────────────────────────────────
// Render — chrome + AIR card, faithful to web/styles.css
// ─────────────────────────────────────────────────────────────────────────────
static void drawHeader(bool alert) {
  uint16_t bg = alert ? C_ERROR : C_PRIMARY;
  tft.fillRect(0, 0, SCREEN_W, HEADER_H, bg);
  tft.loadFont(jbSmall);
  tft.setTextColor(C_GOLD, bg);
  tft.setTextDatum(ML_DATUM);
  tft.drawString(mode == MODE_AIR ? "AIR" : "MARINE", 8, HEADER_H / 2);
  tft.setTextColor(TFT_WHITE, bg);
  tft.setTextDatum(MC_DATUM);
  tft.drawString(alert ? "! EMERGENCY !" : "OMNI-RADAR", SCREEN_W / 2, HEADER_H / 2);
  bool wifi = WiFi.status() == WL_CONNECTED;
  tft.setTextColor(wifi ? C_ACCENT : C_DIM, bg);
  tft.setTextDatum(MR_DATUM);
  tft.drawString(String(wifi ? "WiFi" : "----") + " v1.0", SCREEN_W - 8, HEADER_H / 2);
  tft.unloadFont();
}

static void drawFooterBar() {
  tft.fillRect(0, FOOTER_TOP, SCREEN_W, FOOTER_H, C_FOOTER);
  tft.loadFont(jbSmall);
  tft.setTextDatum(ML_DATUM);
  tft.setTextColor(C_FOOTTXT, C_FOOTER);
  String idx = aircraftCount
      ? String(selected + 1) + " / " + String(aircraftCount) + " TRACKED"
      : "0 / 0 TRACKED";
  tft.drawString(idx, 8, FOOTER_TOP + FOOTER_H / 2);
  tft.setTextDatum(MR_DATUM);
  tft.setTextColor(trackAuto ? C_ACCENT : C_GOLD, C_FOOTER);
  tft.drawString(trackAuto ? "AUTO-CYCLING" : "MANUAL LOCK",
                 SCREEN_W - 8, FOOTER_TOP + FOOTER_H / 2);
  tft.unloadFont();
}

// Number of bottom-strip touch buttons.
static const int BTN_COUNT = 5;

// One touch button in the bottom strip (label + sublabel, smooth font).
static void drawButton(int i, const char* label, const char* sub, bool active) {
  const int bw = SCREEN_W / BTN_COUNT;
  int x = i * bw + 3, y = BTN_TOP + 3, w = bw - 6, h = BTN_BAR_H - 6;
  uint16_t bg = (i == 0) ? C_BTN_PWR : C_BTN;
  tft.fillRoundRect(x, y, w, h, 5, bg);
  if (active) {
    tft.drawRoundRect(x, y, w, h, 5, C_GOLD);
    tft.drawRoundRect(x + 1, y + 1, w - 2, h - 2, 4, C_GOLD);
  }
  tft.setTextDatum(MC_DATUM);
  tft.setTextColor(TFT_WHITE, bg);
  tft.drawString(label, x + w / 2, y + h / 2 - 8);
  tft.setTextColor(C_DIM, bg);
  tft.drawString(sub, x + w / 2, y + h / 2 + 8);
}

static void drawButtons() {
  tft.loadFont(jbSmall);
  drawButton(0, "POWER",  "sleep",   !powered);
  drawButton(1, "MODE",   "air/mar", mode == MODE_MARINE);
  drawButton(2, "ACT",    "lock",    !trackAuto);
  drawButton(3, "ALT",    "radar",   view == VIEW_RADAR);
  drawButton(4, "SET",    "config",  settingsOpen);
  tft.unloadFont();
}

static void drawPlaceholder(const char* title, const char* sub) {
  tft.setTextDatum(MC_DATUM);
  tft.loadFont(jbMed);
  tft.setTextColor(C_DIM, C_LCD_BG);
  tft.drawString(title, SCREEN_W / 2, BODY_TOP + BODY_H / 2 - 14);
  tft.loadFont(jbSmall);
  tft.setTextColor(rgb565(0x6b, 0x64, 0x50), C_LCD_BG);
  tft.drawString(sub, SCREEN_W / 2, BODY_TOP + BODY_H / 2 + 12);
  tft.unloadFont();
}

// Draw an airport name into a FIXED two-line slot (greedy word wrap) so short
// names don't shift the layout. `right` right-aligns to x (else left-aligns).
static void drawName2(const String& text, int x, int y, int maxW, bool right, int lineH) {
  tft.setTextDatum(right ? TR_DATUM : TL_DATUM);
  String line1 = "", line2 = "", word = "";
  int filling = 1;
  for (int i = 0; i <= (int)text.length(); i++) {
    char ch = (i < (int)text.length()) ? text[i] : ' ';
    if (ch != ' ') { word += ch; continue; }
    if (!word.length()) continue;
    if (filling == 1) {
      String t = line1.length() ? line1 + " " + word : word;
      if (tft.textWidth(t) <= maxW) line1 = t;
      else { line2 = word; filling = 2; }
    } else {
      String t = line2.length() ? line2 + " " + word : word;
      if (tft.textWidth(t) <= maxW) line2 = t;  // else: overflow dropped
    }
    word = "";
  }
  if (line1.length()) tft.drawString(line1, x, y);
  if (line2.length()) tft.drawString(line2, x, y + lineH);
}

static void drawAircraftCard() {
  const Aircraft& a = aircraft[selected];
  const bool alert = a.emergency.length() && a.emergency != "None";

  // Telemetry box (graphics first; text drawn over it below).
  const int bx = 12, by = BODY_TOP + 162, bw = SCREEN_W - 24, bh = 44;
  const int cellW = bw / 3;
  tft.fillRoundRect(bx, by, bw, bh, 4, C_TELE_BG);
  tft.drawRoundRect(bx, by, bw, bh, 4, C_LINE);

  // Heading arrow: filled triangle pointing in the heading direction (N=up, CW).
  {
    float rad = a.headingDegrees * PI / 180.0f;
    float s = sinf(rad), c = cosf(rad);
    int hcx = bx + 2 * cellW + cellW - 20, hcy = by + 22, r = 9;
    int tipx = hcx + (int)(s * r),         tipy = hcy - (int)(c * r);
    int rearx = hcx - (int)(s * r * 0.7f), reary = hcy + (int)(c * r * 0.7f);
    float ps = sinf(rad + PI / 2), pc = cosf(rad + PI / 2);
    tft.fillTriangle(tipx, tipy,
                     rearx + (int)(ps * 5), reary - (int)(pc * 5),
                     rearx - (int)(ps * 5), reary + (int)(pc * 5), C_ACCENT);
  }

  // ── Big headline: [flag] ORIG > [flag] DEST, arrow in accent ──────────────
  tft.loadFont(jbBig);
  tft.setTextDatum(TL_DATUM);
  const uint16_t* fO = flagFor(a.originCountry);
  const uint16_t* fD = flagFor(a.destCountry);
  const int fgap = 6;
  int wO = tft.textWidth(a.origin), wA = tft.textWidth(" > "), wD = tft.textWidth(a.destination);
  int fOW = fO ? FLAG_W + fgap : 0, fDW = fD ? FLAG_W + fgap : 0;
  int sx = (SCREEN_W - (fOW + wO + wA + fDW + wD)) / 2, ry = BODY_TOP + 2;
  int flagY = ry + 12;
  tft.setSwapBytes(true);
  int x = sx;
  if (fO) { tft.pushImage(x, flagY, FLAG_W, FLAG_H, fO); x += FLAG_W + fgap; }
  tft.setTextColor(TFT_WHITE, C_LCD_BG);
  tft.drawString(a.origin, x, ry); x += wO;
  tft.setTextColor(C_ACCENT, C_LCD_BG);
  tft.drawString(" > ", x, ry); x += wA;
  if (fD) { tft.pushImage(x, flagY, FLAG_W, FLAG_H, fD); x += FLAG_W + fgap; }
  tft.setTextColor(TFT_WHITE, C_LCD_BG);
  tft.drawString(a.destination, x, ry);
  tft.setSwapBytes(false);

  // ── Medium: callsign (gold) + telemetry values ────────────────────────────
  tft.loadFont(jbMed);
  tft.setTextDatum(TC_DATUM);
  tft.setTextColor(alert ? C_ERROR : C_ACCENT, C_LCD_BG);
  tft.drawString(a.callsign, SCREEN_W / 2, BODY_TOP + 56);

  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(TFT_WHITE, C_TELE_BG);
  tft.drawString(String(a.altitudeFeet) + " ft", bx + 0 * cellW + 10, by + 18);
  tft.drawString(String(a.speedKnots) + " kt",  bx + 1 * cellW + 10, by + 18);
  tft.drawString(String(a.headingDegrees),      bx + 2 * cellW + 10, by + 18);

  // ── Small: names (2-line fixed), airline, model, labels, vspd, chips ───────
  tft.loadFont(jbSmall);
  tft.setTextColor(C_DIM, C_LCD_BG);
  drawName2(a.originName, 12, BODY_TOP + 86, 210, false, 16);
  drawName2(a.destName, SCREEN_W - 12, BODY_TOP + 86, 210, true, 16);

  tft.setTextDatum(TC_DATUM);
  tft.setTextColor(C_LGRAY, C_LCD_BG);
  tft.drawString(a.operatorName, SCREEN_W / 2, BODY_TOP + 122);
  tft.setTextColor(C_DIM, C_LCD_BG);
  tft.drawString(a.modelCode + " - " + a.modelName, SCREEN_W / 2, BODY_TOP + 140);

  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(C_DIM, C_TELE_BG);
  tft.drawString("ALT", bx + 0 * cellW + 10, by + 5);
  tft.drawString("SPD", bx + 1 * cellW + 10, by + 5);
  tft.drawString("HDG", bx + 2 * cellW + 10, by + 5);

  // vertical speed (left of the last row)
  int fry = by + bh + 6;
  tft.setTextDatum(ML_DATUM);
  if (a.verticalSpeed > 0) {
    tft.setTextColor(C_ACCENT, C_LCD_BG);
    tft.drawString("+" + String(a.verticalSpeed) + " fpm", 12, fry + 8);
  } else if (a.verticalSpeed < 0) {
    tft.setTextColor(C_GOLD, C_LCD_BG);
    tft.drawString(String(a.verticalSpeed) + " fpm", 12, fry + 8);
  } else {
    tft.setTextColor(C_DIM, C_LCD_BG);
    tft.drawString("- level", 12, fry + 8);
  }

  // chips, right-aligned: special designation then operator class
  int rightX = SCREEN_W - 12;
  auto chip = [&](const String& text, uint16_t cbg) {
    int w = tft.textWidth(text) + 12, h = 17, x = rightX - w;
    tft.fillRoundRect(x, fry, w, h, 3, cbg);
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(TFT_WHITE, cbg);
    tft.drawString(text, x + w / 2, fry + h / 2);
    tft.setTextDatum(ML_DATUM);
    rightX = x - 5;
  };
  if (a.specialDesignation.length() && a.specialDesignation != "None")
    chip(a.specialDesignation, chipColor("Military"));
  if (a.operatorClass.length() && a.operatorClass != "Unknown")
    chip(a.operatorClass, chipColor(a.operatorClass));

  tft.unloadFont();
}

// Radar view (North up), mirroring web/js/device.js#renderRadar: fixed compass
// scope with the SELECTED target plotted by bearing/distance from home.
static void drawRadar() {
  const int CX = SCREEN_W / 2;
  const int CY = BODY_TOP + (FOOTER_TOP - BODY_TOP) / 2;
  const int R  = 100;
  const uint16_t C_RING = rgb565(0x5a, 0x4c, 0x18);  // dim gold

  tft.drawCircle(CX, CY, R, C_RING);
  tft.drawCircle(CX, CY, R / 2, C_LINE);
  tft.drawFastHLine(CX - R, CY, 2 * R, C_LINE);
  tft.drawFastVLine(CX, CY - R, 2 * R, C_LINE);
  tft.fillCircle(CX, CY, 3, TFT_WHITE);   // user at center

  tft.loadFont(jbSmall);
  tft.setTextDatum(MC_DATUM);
  tft.setTextColor(C_ACCENT, C_LCD_BG); tft.drawString("N", CX, CY - R - 9);
  tft.setTextColor(C_DIM, C_LCD_BG);
  tft.drawString("S", CX, CY + R + 9);
  tft.drawString("E", CX + R + 10, CY);
  tft.drawString("W", CX - R - 10, CY);
  tft.setTextDatum(TR_DATUM);
  tft.drawString(String(cfg.radiusMiles) + " mi", SCREEN_W - 10, FOOTER_TOP - 16);

  bool homeSet = (HOME_LAT != 0.0f || HOME_LON != 0.0f);
  const Aircraft* a = aircraftCount ? &aircraft[selected] : nullptr;
  if (!homeSet || !a || !a->hasPos) {
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(C_DIM, C_LCD_BG);
    tft.drawString(!homeSet ? "no home set" : (a ? "no position" : "no targets"),
                   CX, CY + R / 2 + 20);
    tft.unloadFont();
    return;
  }

  // Relative bearing/distance (mid-latitude flat-earth approximation).
  float mpLon = 69.0f * cosf(HOME_LAT * PI / 180.0f);
  float dN = (a->lat - HOME_LAT) * 69.0f;
  float dE = (a->lon - HOME_LON) * mpLon;
  float dist = sqrtf(dN * dN + dE * dE);
  float bearing = atan2f(dE, dN);
  float rr = dist / cfg.radiusMiles; if (rr > 1.0f) rr = 1.0f;
  int px = CX + (int)(rr * R * sinf(bearing));
  int py = CY - (int)(rr * R * cosf(bearing));

  // Target glyph: triangle pointing in its heading direction.
  float rad = a->headingDegrees * PI / 180.0f;
  float s = sinf(rad), c = cosf(rad); int sz = 8;
  int rearx = px - (int)(s * sz * 0.7f), reary = py + (int)(c * sz * 0.7f);
  float ps = sinf(rad + PI / 2), pc = cosf(rad + PI / 2);
  tft.fillTriangle(px + (int)(s * sz), py - (int)(c * sz),
                   rearx + (int)(ps * 5), reary - (int)(pc * 5),
                   rearx - (int)(ps * 5), reary + (int)(pc * 5), C_ACCENT);

  // Info label, placed away from the scope edge.
  bool left = px > CX;
  int lx = left ? px - 10 : px + 10;
  tft.setTextDatum(left ? TR_DATUM : TL_DATUM);
  tft.setTextColor(C_ACCENT, C_LCD_BG);
  tft.drawString(a->callsign, lx, py - 7);
  tft.setTextColor(C_DIM, C_LCD_BG);
  tft.drawString(String(a->altitudeFeet) + " ft  " + String(dist, 1) + " mi", lx, py + 9);
  tft.unloadFont();
}

static String settingValueStr(int i) {
  const SettingDef& d = settingDefs[i];
  String s = String(*d.val);
  if (d.unit[0]) s += " " + String(d.unit);
  return s;
}

// Settings screen: one row per setting with [-] value [+] touch targets.
static const int SET_MINUS_CX = 300, SET_PLUS_CX = 430, SET_VALUE_CX = 365;

static void drawSettings() {
  tft.fillRect(0, 0, SCREEN_W, HEADER_H, C_PRIMARY);
  tft.loadFont(jbSmall);
  tft.setTextColor(TFT_WHITE, C_PRIMARY);
  tft.setTextDatum(MC_DATUM);
  tft.drawString("SETTINGS", SCREEN_W / 2, HEADER_H / 2);
  tft.setTextColor(C_GOLD, C_PRIMARY);
  tft.setTextDatum(MR_DATUM);
  tft.drawString("SET = close", SCREEN_W - 8, HEADER_H / 2);
  tft.unloadFont();

  tft.fillRect(0, BODY_TOP, SCREEN_W, BTN_TOP - BODY_TOP, C_LCD_BG);
  int rowH = (BTN_TOP - BODY_TOP) / SETTING_COUNT;
  for (int i = 0; i < SETTING_COUNT; i++) {
    int ry = BODY_TOP + i * rowH, cy = ry + rowH / 2;
    if (i) tft.drawFastHLine(8, ry, SCREEN_W - 16, C_LINE);

    tft.loadFont(jbSmall);
    tft.setTextColor(C_LGRAY, C_LCD_BG);
    tft.setTextDatum(ML_DATUM);
    tft.drawString(settingDefs[i].label, 16, cy);

    tft.loadFont(jbMed);
    auto box = [&](int cx, const char* sym) {
      tft.fillRoundRect(cx - 22, cy - 20, 44, 40, 5, C_BTN);
      tft.setTextColor(C_ACCENT, C_BTN);
      tft.setTextDatum(MC_DATUM);
      tft.drawString(sym, cx, cy - 1);
    };
    box(SET_MINUS_CX, "-");
    box(SET_PLUS_CX, "+");
    tft.setTextColor(TFT_WHITE, C_LCD_BG);
    tft.setTextDatum(MC_DATUM);
    tft.drawString(settingValueStr(i), SET_VALUE_CX, cy);
  }
  tft.unloadFont();
}

// Full paint. Repaints each band in place (no full-screen white flash).
static void renderAll() {
  if (!powered) { tft.fillScreen(TFT_BLACK); return; }
  if (settingsOpen) { drawSettings(); drawButtons(); return; }

  bool alert = aircraftCount && mode == MODE_AIR && view == VIEW_DATA &&
               aircraft[selected].emergency.length() &&
               aircraft[selected].emergency != "None";

  drawHeader(alert);
  tft.fillRect(0, BODY_TOP, SCREEN_W, BODY_H, C_LCD_BG);   // clear body

  if (mode == MODE_MARINE)        drawPlaceholder("MARINE MODE", "coming soon");
  else if (view == VIEW_RADAR)    drawRadar();
  else if (aircraftCount == 0)    drawPlaceholder("NO SIGNAL", "scanning for targets");
  else                            drawAircraftCard();

  drawFooterBar();
  drawButtons();
}

// ─────────────────────────────────────────────────────────────────────────────
// Touch
// ─────────────────────────────────────────────────────────────────────────────
static void handleButton(int i) {
  // While settings are open, only POWER and SET are active.
  if (settingsOpen && (i == 1 || i == 2 || i == 3)) return;
  switch (i) {
    case 0:  // POWER — sleep / wake (backlight off + blank)
      powered = !powered;
      LOG("[btn] POWER -> %s", powered ? "on" : "off");
      setBacklight(powered ? brightnessDuty() : 0);
      renderAll();
      break;
    case 1:  // MODE — AIR / MARINE (marine stubbed)
      mode = (mode == MODE_AIR) ? MODE_MARINE : MODE_AIR;
      LOG("[btn] MODE -> %s", mode == MODE_AIR ? "AIR" : "MARINE");
      renderAll();
      break;
    case 2:  // ACTION — auto-cycle -> manual lock; step while locked
      if (trackAuto) { trackAuto = false; LOG("[btn] ACTION -> manual lock"); }
      else if (aircraftCount) {
        selected = (selected + 1) % aircraftCount;
        LOG("[btn] ACTION -> step to %d", selected + 1);
      }
      renderAll();
      break;
    case 3:  // ALT — radar view toggle (radar stubbed)
      view = (view == VIEW_DATA) ? VIEW_RADAR : VIEW_DATA;
      LOG("[btn] ALT -> %s", view == VIEW_RADAR ? "radar" : "data");
      renderAll();
      break;
    case 4:  // SET — open / close settings
      settingsOpen = !settingsOpen;
      LOG("[btn] SET -> %s", settingsOpen ? "open" : "closed");
      renderAll();
      break;
  }
}

// A tap inside the settings body: hit-test the [-]/[+] targets for a row.
static void handleSettingsTouch(int x, int y) {
  int rowH = (BTN_TOP - BODY_TOP) / SETTING_COUNT;
  int row = (y - BODY_TOP) / rowH;
  if (row < 0 || row >= SETTING_COUNT) return;
  SettingDef& d = settingDefs[row];
  // Split the adjust area at the value center: left of it = minus, right = plus.
  // (Generous zones so touch-calibration slop can't land in a dead gap.)
  int delta = 0;
  if (x >= 230 && x < SET_VALUE_CX) delta = -d.step;
  else if (x >= SET_VALUE_CX) delta = d.step;
  LOG("[set] touch x=%d row=%d delta=%d", x, row, delta);
  if (!delta) return;

  int v = *d.val + delta;
  if (v < d.lo) v = d.lo;
  if (v > d.hi) v = d.hi;
  if (v == *d.val) return;
  *d.val = v;
  saveSettings();
  if (d.val == &cfg.brightnessPct) setBacklight(brightnessDuty());  // live preview
  LOG("[set] %s = %d", d.label, v);
  renderAll();
}

static void pollTouch() {
  uint16_t z = tft.getTouchRawZ();
  if (z < 400) { touchLatched = false; return; }   // not pressed
  if (touchLatched) return;                          // one action per press
  touchLatched = true;

  // Axes are swapped on this panel: ry -> horizontal (x), rx -> vertical (y).
  uint16_t rx = 0, ry = 0;
  tft.getTouchRaw(&rx, &ry);
  int x = map(ry, TS_RAW_X_LEFT, TS_RAW_X_RIGHT, 0, SCREEN_W);
  int y = map(rx, TS_RAW_Y_TOP, TS_RAW_Y_BOTTOM, 0, SCREEN_H);
  x = constrain(x, 0, SCREEN_W - 1);
  y = constrain(y, 0, SCREEN_H - 1);
  LOG("[touch] rawZ=%d raw=(%d,%d) -> screen=(%d,%d)", z, rx, ry, x, y);

  if (y >= BTN_TOP) {
    // Bottom strip: POWER always active (to wake); others only when powered.
    int i = x / (SCREEN_W / BTN_COUNT);
    if (i < 0) i = 0;
    if (i > BTN_COUNT - 1) i = BTN_COUNT - 1;
    if (powered || i == 0) handleButton(i);
  } else if (powered && settingsOpen) {
    handleSettingsTouch(x, y);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Arduino entry points
// ─────────────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(200);
  LOG("\n[boot] Omni-Radar device firmware");

  loadSettings();

  tft.init();
  tft.setRotation(1);
  tft.fillScreen(C_LCD_BG);

  // Attach the backlight PWM AFTER tft.init() so nothing steals the pin.
  ledcSetup(BL_CHANNEL, 5000, 8);
  ledcAttachPin(BL_PIN, BL_CHANNEL);
  setBacklight(brightnessDuty());
  LOG("[boot] display + touch initialised");

  connectWifi();
  renderAll();
}

void loop() {
  const uint32_t now = millis();

  if (WiFi.status() != WL_CONNECTED) { connectWifi(); renderAll(); return; }

  pollTouch();

  if (!firstPollDone || now - lastPollMs >= pollIntervalMs) {
    bool ok = fetchNearby();
    lastPollMs = now;
    firstPollDone = true;
    if (ok) { lastCycleMs = now; renderAll(); }
  }

  // Auto-cycle in AIR mode (data or radar) with auto track on, not in settings.
  if (powered && trackAuto && !settingsOpen && mode == MODE_AIR &&
      aircraftCount > 1 && now - lastCycleMs >= (uint32_t)cfg.cycleSec * 1000UL) {
    selected = (selected + 1) % aircraftCount;
    lastCycleMs = now;
    renderAll();
  }

  delay(20);
}
