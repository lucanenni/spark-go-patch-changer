#include <Arduino.h>

#include "config.h"
#include "display.h"
#include "midi_bridge.h"
#include "spark_ble.h"
#include "spark_state.h"
#include "tuner.h"

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

uint32_t g_lastBootButtonMs = 0;
bool g_wasTunerOn = false;

constexpr uint32_t kBootSplashHoldMs = 1200;

// Renders the pre-connection/connection-lost diagnostic view right now, from
// whatever spark_ble/spark_state currently report. Called both from loop()
// every iteration and (for two specific states - see
// handleConnectionStateChanged() below) directly from the connection-state
// callback, which is what actually lets "Scanning..."/"Connecting..." reach
// the screen at all.
void renderStatusView() {
  int patch0Based = spark_state::activePatch0Based();
  // rx/sub/cccd are diagnostics (see spark_ble::rawNotificationCount/
  // lastSubscribeOk/cccdFound) - only useful while still trying to connect.
  String connectionLine = String(connectionStateText(spark_ble::state())) + " rx:" +
                           spark_ble::rawNotificationCount() +
                           (spark_ble::lastSubscribeOk() ? " sub:Y" : " sub:N") +
                           (spark_ble::cccdFound() ? " cccd:Y" : " cccd:N");
  display::showStatus(connectionLine, patch0Based >= 0 ? patch0Based + 1 : -1,
                       midi_bridge::lastEventText());
}

// Serial goes out over the TX/RX pins (GPIO43/44), not the main USB-A plug
// (that one's dedicated to USB-MIDI) - so seeing these needs an external
// USB-serial adapter wired to those pins, not just the same USB cable used
// to flash. See README.md.
void handleConnectionStateChanged(spark_ble::ConnectionState state) {
  Serial.print("[BLE] ");
  Serial.println(connectionStateText(state));

  // attemptConnect() (scan, then connect) blocks on the main loop() task for
  // its whole duration before returning - without this, "Scanning..." and
  // "Connecting..." would never actually reach the screen, since loop()'s own
  // redraw only runs once attemptConnect() has already finished. Only these
  // two states are safe to draw from here: both are only ever set from
  // inside attemptConnect(), which only ever runs on the main task (called
  // synchronously from spark_ble::loop(), itself only called from this
  // file's loop()). kDisconnected can also arrive from NimBLE's own host
  // task (ClientCallbacks::onDisconnect, a different task than the one
  // driving this TFT_eSPI instance elsewhere) - deliberately left to loop()'s
  // next iteration instead, which happens fast enough anyway since nothing
  // blocks loop() once disconnected.
  bool isScanningOrConnecting = state == spark_ble::ConnectionState::kScanning ||
                                state == spark_ble::ConnectionState::kConnecting;
  if (isScanningOrConnecting && !tuner::isOn()) {
    renderStatusView();
  }
}

}  // namespace

void setup() {
  Serial.begin(115200);
  Serial.println("ESP32-S3 ChocolatePlus bridge starting...");
  Serial.printf("Free heap: %u bytes\n", ESP.getFreeHeap());

  // One checkpoint per init step, both on Serial and on the screen itself
  // (showStatus() doubles as a generic "one status line + one detail line"
  // display, reused here before the BLE/MIDI machinery it's normally fed by
  // even exists yet). If the board hangs or crashes during setup(), whatever
  // is still on screen (or the last Serial line) says exactly where -
  // useful without needing a USB-serial adapter at all, since the display is
  // already confirmed working on its own.
  display::begin();
  display::showBootSplash();
  delay(kBootSplashHoldMs);
  display::showStatus("Booting", -1, "display OK");
  Serial.println("display::begin() done");

  midi_bridge::begin();
  display::showStatus("Booting", -1, "USB-MIDI OK");
  Serial.println("midi_bridge::begin() done");

  tuner::begin();
  display::showStatus("Booting", -1, "tuner OK");
  Serial.println("tuner::begin() done");

  spark_ble::begin();
  display::showStatus("Booting", -1, "BLE init OK");
  Serial.println("spark_ble::begin() done");

  pinMode(config::kBootButtonPin, INPUT_PULLUP);

  // spark_state is the source of truth for effect-toggle slot state; keep it
  // fed from whatever the device tells us. Display refresh itself happens
  // unconditionally every loop() iteration (see below), not from these
  // callbacks - simpler than trying to catch every path that changes what's
  // on screen.
  spark_ble::onPreset(
      [](const spark_protocol::PresetData& preset) { spark_state::applyPreset(preset); });
  spark_ble::onEffectState(
      [](const spark_protocol::EffectStateEvent& event) { spark_state::applyEffectState(event); });
  spark_ble::onTunerFrame(tuner::handleFrame);
  spark_ble::onConnectionStateChanged(handleConnectionStateChanged);

  display::showStatus("Booting", -1, "setup() done");
  Serial.println("setup() complete, entering loop()");
  Serial.println("[BLE] Looking for Spark GO...");
}

void loop() {
  spark_ble::loop();
  midi_bridge::loop();

  bool tunerOn = tuner::isOn();
  if (tunerOn) {
    tuner::Reading reading = tuner::currentReading();
    display::showTuner(reading.noteName, reading.cents, reading.hasSignal);
  } else {
    if (g_wasTunerOn) display::invalidate();  // force a redraw after leaving the tuner view
    if (spark_ble::isConnected()) {
      // Once connected, the pre-connection diagnostics aren't interesting
      // anymore - show the actual patch number/name instead. Falls straight
      // back to the diagnostic view below on its own if the connection
      // drops (isConnected() becomes false again), no extra handling needed.
      int patch0Based = spark_state::activePatch0Based();
      display::showConnected(patch0Based >= 0 ? patch0Based + 1 : -1, spark_state::activePatchName(),
                             midi_bridge::lastEventText());
    } else {
      renderStatusView();
    }
  }
  g_wasTunerOn = tunerOn;

  // BOOT button (GPIO0) = manual "force BLE reconnect", debounced.
  if (digitalRead(config::kBootButtonPin) == LOW) {
    uint32_t now = millis();
    if (now - g_lastBootButtonMs > 1000) {
      g_lastBootButtonMs = now;
      spark_ble::forceReconnect();
    }
  }
}
