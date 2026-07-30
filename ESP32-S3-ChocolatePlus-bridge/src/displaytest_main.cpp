// Minimal, standalone TFT_eSPI test - deliberately has NO dependency on
// BLE/USB-MIDI/any other module in this firmware, so it isolates one
// question: does the display (pins + driver variant in platformio.ini) work
// at all on this specific board, independent of everything else that could
// be hanging/crashing in the real firmware's setup()?
//
// Build and flash ONLY this with:
//   pio run -e esp32-s3-dongle-displaytest --target upload
//
// What to expect: the screen should flash solid RED, then GREEN, then BLUE
// (each for ~1s), then go black and show "HELLO" + "Display test OK" in
// white text, then a small yellow square in the corner should blink on/off
// once a second forever (proof loop() is still running, not just that
// setup() ran once before hanging).
//
// - Nothing at all (no color flashes) -> real display/pin/driver problem,
//   unrelated to BLE or MIDI code.
// - Colors/text show up fine -> the display + its pin config are correct,
//   and whatever's wrong in the real firmware is elsewhere in setup()
//   (most likely midi_bridge::begin()'s TinyUSB init or spark_ble::begin()'s
//   NimBLEDevice::init()).

#include <Arduino.h>
#include <TFT_eSPI.h>

namespace {
TFT_eSPI tft;
uint32_t g_lastBlinkMs = 0;
bool g_blinkOn = true;
}  // namespace

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("Display test starting...");

  tft.init();
  tft.setRotation(1);

  tft.fillScreen(TFT_RED);
  delay(1000);
  tft.fillScreen(TFT_GREEN);
  delay(1000);
  tft.fillScreen(TFT_BLUE);
  delay(1000);

  tft.fillScreen(TFT_BLACK);
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
  tft.setTextSize(2);
  tft.setCursor(4, 4);
  tft.println("HELLO");
  tft.setTextSize(1);
  tft.setCursor(4, 30);
  tft.println("Display test OK");

  Serial.println("setup() done - color cycle + text drawn");
}

void loop() {
  if (millis() - g_lastBlinkMs > 1000) {
    g_lastBlinkMs = millis();
    g_blinkOn = !g_blinkOn;
    tft.fillRect(0, 50, 10, 10, g_blinkOn ? TFT_YELLOW : TFT_BLACK);
    Serial.println("loop() alive");
  }
}
