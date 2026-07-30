// Minimal, standalone BLE-only test - deliberately has NO dependency on
// USB-MIDI/display, so it isolates the Spark GO BLE connection question
// without needing the Chocolate Plus at all, and (unlike the real firmware)
// CAN have Serial-over-USB enabled, since there's no Adafruit_TinyUSB in
// this build to conflict with CDC. Every raw BLE notification byte is
// logged directly from spark_ble.cpp (see notifyCallback there) - visible
// here without needing an external USB-serial adapter.
//
// Build and flash ONLY this with:
//   pio run -e esp32-s3-dongle-bletest --target upload
// Then open a serial monitor (no BOOT-holding needed for this one, since
// CDC allows normal reset-to-run):
//   pio device monitor -e esp32-s3-dongle-bletest -b 115200
//
// Type a command + Enter into the monitor to trigger it:
//   patch 1        - send patch change (1-4)
//   active         - query which patch is active
//   tuner on/off   - start/stop the tuner
//   status         - print connection/rx/sub/cccd diagnostics

#include <Arduino.h>

#include "spark_ble.h"
#include "spark_protocol.h"
#include "spark_state.h"

namespace {

const char* connectionStateText(spark_ble::ConnectionState state) {
  switch (state) {
    case spark_ble::ConnectionState::kDisconnected:
      return "Disconnected";
    case spark_ble::ConnectionState::kScanning:
      return "Scanning...";
    case spark_ble::ConnectionState::kConnecting:
      return "Connecting...";
    case spark_ble::ConnectionState::kConnected:
      return "Connected";
  }
  return "?";
}

void printStatus() {
  Serial.printf("[status] state=%s rx=%u sub=%s cccd=%s activePatch0=%d\n",
                connectionStateText(spark_ble::state()), (unsigned)spark_ble::rawNotificationCount(),
                spark_ble::lastSubscribeOk() ? "Y" : "N", spark_ble::cccdFound() ? "Y" : "N",
                spark_state::activePatch0Based());
}

void handleLine(const String& line) {
  if (line == "status") {
    printStatus();
  } else if (line == "active") {
    Serial.println("[cmd] requestActivePatch()");
    spark_ble::requestActivePatch();
  } else if (line == "tuner on") {
    Serial.println("[cmd] tunerStart()");
    spark_ble::tunerStart();
  } else if (line == "tuner off") {
    Serial.println("[cmd] tunerStop()");
    spark_ble::tunerStop();
  } else if (line.startsWith("patch ")) {
    int n = line.substring(6).toInt();
    Serial.printf("[cmd] sendPatch(%d)\n", n);
    spark_ble::sendPatch(static_cast<uint8_t>(n));
  } else if (line.length() > 0) {
    Serial.println("[cmd] unknown - try: status, active, tuner on, tuner off, patch <1-4>");
  }
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("BLE test starting...");

  spark_ble::onConnectionStateChanged(
      [](spark_ble::ConnectionState s) { Serial.printf("[event] connection -> %s\n", connectionStateText(s)); });
  spark_ble::onPatchConfirmed(
      [](uint8_t p) { Serial.printf("[event] patch confirmed/active: %u (1-based: %u)\n", p, p + 1); });
  spark_ble::onPreset([](const spark_protocol::PresetData& preset) {
    spark_state::applyPreset(preset);
    Serial.printf("[event] preset read: num=%u name=%s bpm=%.1f pedals=%u\n", preset.presetNum,
                  preset.name.c_str(), preset.bpm, preset.pedalCount);
  });
  spark_ble::onEffectState([](const spark_protocol::EffectStateEvent& e) {
    spark_state::applyEffectState(e);
    Serial.printf("[event] effect state: %s -> %s\n", e.name.c_str(), e.on ? "ON" : "OFF");
  });
  spark_ble::onTunerFrame([](const spark_protocol::TunerFrame& f) {
    Serial.printf("[event] tuner frame: idle=%d note=%s counter=%u cents=%.1f\n", f.idle,
                  spark_protocol::noteName(f.note), f.counter, f.cents);
  });

  spark_ble::begin();
  Serial.println("setup() done - looking for Spark GO...");
}

void loop() {
  spark_ble::loop();

  static String line;
  while (Serial.available()) {
    char c = static_cast<char>(Serial.read());
    if (c == '\n' || c == '\r') {
      if (line.length() > 0) {
        handleLine(line);
        line = "";
      }
    } else {
      line += c;
    }
  }
}
