#include "display.h"

#include <TFT_eSPI.h>

#include <algorithm>

#include "config.h"

namespace display {

namespace {

TFT_eSPI tft;

constexpr uint16_t kBg = TFT_BLACK;
constexpr uint16_t kFg = TFT_WHITE;
constexpr uint16_t kAccent = TFT_CYAN;
constexpr uint16_t kInTune = TFT_GREEN;

uint32_t g_lastTunerDrawMs = 0;
constexpr uint32_t kTunerRedrawIntervalMs = 40;  // ~25 fps cap on the SPI link

String g_lastStatusKey;  // skip redundant redraws when nothing actually changed
String g_lastConnectedKey;

// Portrait orientation (config::kDisplayRotation) is narrower (80px) than
// the original landscape layout this was designed for - long strings (e.g.
// the last MIDI event line) need to wrap across a couple of lines instead
// of running off the right edge. ~13 chars fit per line at text size 1.
constexpr size_t kCharsPerLine = 13;

// Word-wraps at the last space within each ~kCharsPerLine-wide chunk (falls
// back to a hard break only if a single word is itself longer than that).
void printWrapped(const String& text, int16_t x, int16_t y, int16_t lineHeight,
                  size_t maxLines) {
  size_t start = 0;
  for (size_t line = 0; line < maxLines && start < text.length(); ++line) {
    size_t end = start;
    size_t lastSpace = start;
    while (end < text.length() && (end - start) < kCharsPerLine) {
      if (text[end] == ' ') lastSpace = end;
      ++end;
    }

    size_t breakAt = end;
    if (end < text.length() && lastSpace > start) {
      breakAt = lastSpace;
    }

    tft.setCursor(x, y + static_cast<int16_t>(line) * lineHeight);
    tft.print(text.substring(start, breakAt));

    start = breakAt;
    while (start < text.length() && text[start] == ' ') ++start;
  }
}

// Draws text at the current text size/color, horizontally centered.
void printCentered(const String& text, int16_t y) {
  int16_t w = tft.textWidth(text);
  tft.setCursor((tft.width() - w) / 2, y);
  tft.print(text);
}

}  // namespace

void begin() {
  if (config::kTftBacklightPin >= 0) {
    pinMode(config::kTftBacklightPin, OUTPUT);
    digitalWrite(config::kTftBacklightPin, HIGH);
  }
  tft.init();
  tft.setRotation(config::kDisplayRotation);
  tft.fillScreen(kBg);
  tft.setTextColor(kFg, kBg);
}

void showBootSplash() {
  tft.fillScreen(kBg);

  tft.setTextSize(2);
  tft.setTextColor(kAccent, kBg);
  printCentered("SPARK", 30);
  printCentered("GO", 55);

  tft.setTextSize(1);
  tft.setTextColor(kFg, kBg);
  printCentered("Bridge", 92);

  // "MVave -> Spark GO" as one line is wider than the 80px portrait screen
  // (17 chars * 6px/char at text size 1 = 102px) - centering it then draws
  // starting at a negative X, clipping the first ~2 characters off the left
  // edge. Split across two lines instead, each well under the ~13-char
  // budget this screen actually has room for.
  tft.setTextColor(TFT_DARKGREY, kBg);
  printCentered("MVave ->", 112);
  printCentered("Spark GO", 124);
}

void showStatus(const String& connectionLine, int currentPatch1Based, const String& lastEventLine) {
  String key = connectionLine + "|" + String(currentPatch1Based) + "|" + lastEventLine;
  if (key == g_lastStatusKey) return;  // nothing actually changed, skip the redraw
  g_lastStatusKey = key;

  tft.fillScreen(kBg);

  tft.setTextSize(1);
  tft.setTextColor(kAccent, kBg);
  printWrapped(connectionLine, 2, 2, 12, 3);

  tft.setTextColor(kFg, kBg);
  tft.setCursor(2, 40);
  if (currentPatch1Based >= 1) {
    tft.print("Patch ");
    tft.print(currentPatch1Based);
  } else {
    tft.print("Patch --");
  }

  tft.drawFastHLine(0, 54, tft.width(), TFT_DARKGREY);

  printWrapped(lastEventLine, 2, 60, 12, 3);
}

void showConnected(int currentPatch1Based, const String& patchName, const String& lastEventLine) {
  String key = String(currentPatch1Based) + "|" + patchName + "|" + lastEventLine;
  if (key == g_lastConnectedKey) return;  // nothing actually changed, skip the redraw
  g_lastConnectedKey = key;

  tft.fillScreen(kBg);

  tft.setTextSize(5);
  tft.setTextColor(kFg, kBg);
  String patchText = currentPatch1Based >= 1 ? String(currentPatch1Based) : "-";
  int16_t numWidth = tft.textWidth(patchText);
  tft.setCursor((tft.width() - numWidth) / 2, 6);
  tft.print(patchText);
  tft.setTextSize(1);

  tft.setTextColor(kAccent, kBg);
  printWrapped(patchName.length() > 0 ? patchName : "(unnamed)", 2, 50, 12, 2);

  tft.drawFastHLine(0, 78, tft.width(), TFT_DARKGREY);

  tft.setTextColor(kFg, kBg);
  printWrapped(lastEventLine, 2, 84, 12, 3);
}

void showTuner(const char* noteName, float cents, bool hasSignal) {
  uint32_t now = millis();
  if (now - g_lastTunerDrawMs < kTunerRedrawIntervalMs) return;
  g_lastTunerDrawMs = now;

  tft.fillScreen(kBg);

  tft.setTextSize(1);
  tft.setTextColor(kAccent, kBg);
  tft.setCursor(2, 2);
  tft.print("TUNER");

  tft.setTextSize(3);
  tft.setTextColor(hasSignal ? kFg : TFT_DARKGREY, kBg);
  int16_t noteWidth = tft.textWidth(hasSignal ? noteName : "--");
  tft.setCursor((tft.width() - noteWidth) / 2, 20);
  tft.print(hasSignal ? noteName : "--");
  tft.setTextSize(1);

  // Cents bar: -50..+50, drawn as a vertical bar (flat at the bottom, sharp
  // at the top - "dal basso verso l'alto") with a center tick and a moving
  // needle, sized for the portrait orientation. Provisional/uncalibrated
  // scale - see PROTOCOL.md.
  constexpr int16_t kBarW = 20;
  constexpr int16_t kBarTop = 70;
  constexpr int16_t kBarBottom = 150;
  int16_t barX = (tft.width() - kBarW) / 2;
  int16_t barHeight = kBarBottom - kBarTop;
  int16_t centerY = kBarTop + barHeight / 2;

  tft.drawRect(barX, kBarTop, kBarW, barHeight, TFT_DARKGREY);
  tft.drawFastHLine(barX, centerY, kBarW, TFT_DARKGREY);

  if (hasSignal) {
    float clamped = cents < -50 ? -50 : (cents > 50 ? 50 : cents);
    int16_t needleY = centerY - static_cast<int16_t>((clamped / 50.0f) * (barHeight / 2));
    uint16_t needleColor = (clamped > -5 && clamped < 5) ? kInTune : kAccent;
    tft.fillRect(barX, needleY - 1, kBarW, 3, needleColor);
  }
}

void invalidate() {
  g_lastStatusKey = "\x01invalid\x01";
  g_lastConnectedKey = "\x01invalid\x01";
}

}  // namespace display
