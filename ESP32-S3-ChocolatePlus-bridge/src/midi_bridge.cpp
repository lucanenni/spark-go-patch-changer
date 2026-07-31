#include "midi_bridge.h"

#include <Adafruit_TinyUSB.h>
#include <MIDI.h>
#include <USB.h>

#include <algorithm>
#include <vector>

#include "config.h"
#include "spark_ble.h"
#include "spark_protocol.h"
#include "spark_state.h"
#include "tuner.h"

namespace midi_bridge {

namespace {

Adafruit_USBD_MIDI usb_midi;
MIDI_CREATE_INSTANCE(Adafruit_USBD_MIDI, usb_midi, MIDI);

String g_lastEvent = "Waiting for MIDI...";

// Tap-tempo state: timestamps (millis()) of the last few taps, mirrors
// desktop/spark_go_gui.py's tap_tempo() logic exactly (reset gap, sample
// count, min/max BPM clamp).
std::vector<uint32_t> g_tapTimes;

// Computes a fresh BPM from tap intervals and sends it. Returns false (no
// send) on the first tap of a new sequence, same as the reference client.
bool handleTapTempo() {
  uint32_t now = millis();
  if (!g_tapTimes.empty() && now - g_tapTimes.back() > config::kTapTempoResetGapMs) {
    g_tapTimes.clear();
  }
  g_tapTimes.push_back(now);
  if (g_tapTimes.size() > config::kTapTempoMaxSamples) {
    g_tapTimes.erase(g_tapTimes.begin());
  }
  if (g_tapTimes.size() < 2) return false;

  uint32_t totalIntervalMs = g_tapTimes.back() - g_tapTimes.front();
  float avgIntervalS = (totalIntervalMs / 1000.0f) / (g_tapTimes.size() - 1);
  float bpm = 60.0f / avgIntervalS;
  bpm = std::min(config::kTapTempoMaxBpm, std::max(config::kTapTempoMinBpm, bpm));

  bool ok = spark_ble::tapTempo(bpm);
  g_lastEvent = String("Tap Tempo ") + String(bpm, 1) + " BPM" + (ok ? "" : " (not connected)");
  return true;
}

bool channelMatches(uint8_t channel) {
  return config::kMidiChannel == 0 || channel == config::kMidiChannel;
}

void handleProgramChange(uint8_t channel, uint8_t number) {
  if (!channelMatches(channel)) return;

  // A patch change implicitly exits tuner mode first, same as a real pedal -
  // see tuner::forceOff().
  tuner::forceOff();

  if (number < config::kPatchProgramChangeBase ||
      number >= config::kPatchProgramChangeBase + config::kPatchCount) {
    g_lastEvent = String("PC ") + number + " (unmapped)";
    return;
  }

  uint8_t patchNumber1Based = number - config::kPatchProgramChangeBase + 1;
  bool ok = spark_ble::sendPatch(patchNumber1Based);
  g_lastEvent = String("PC ") + number + " -> Patch " + patchNumber1Based +
                (ok ? "" : " (not connected)");
}

void handleControlChange(uint8_t channel, uint8_t number, uint8_t value) {
  if (!channelMatches(channel)) return;

  if (number == config::kTunerToggleCc) {
    bool on = tuner::toggle();
    g_lastEvent = on ? "Tuner ON" : "Tuner OFF";
    return;
  }

  // Any other command implicitly exits tuner mode first, same as a real
  // pedal - see tuner::forceOff(). Must come after the tuner-toggle check
  // above, or toggling the tuner off would immediately force it back on.
  tuner::forceOff();

  if (number >= config::kEffectToggleCcBase &&
      number < config::kEffectToggleCcBase + config::kEffectToggleCcCount) {
    uint8_t slot = number - config::kEffectToggleCcBase;
    String internalName;
    bool currentlyOn;
    if (!spark_state::getSlot(slot, internalName, currentlyOn)) {
      g_lastEvent = String("CC") + number + " " + spark_protocol::kSlotLabels[slot] + " (state unknown)";
      return;
    }
    bool newOn = !currentlyOn;
    bool ok = spark_ble::toggleEffect(internalName, newOn);
    g_lastEvent = String(spark_protocol::kSlotLabels[slot]) + (newOn ? " ON" : " OFF") +
                  (ok ? "" : " (failed)");
    return;
  }

  if (number == config::kTapTempoCc) {
    handleTapTempo();
    return;
  }

  if (number == config::kChannelVolumeCc) {
    float normalized = value / 127.0f;
    bool ok = spark_ble::setGuitarVolume(normalized);
    g_lastEvent = String("Guitar Volume ") + static_cast<int>(normalized * 100) + "%" +
                  (ok ? "" : " (not connected)");
    return;
  }

  if (number == config::kMasterVolumeCc) {
    // Deliberately unimplemented - see config::kMasterVolumeCc's comment.
    g_lastEvent = "CC20 Master Volume (not supported)";
    return;
  }

  g_lastEvent = String("CC") + number + "=" + value + " (unmapped)";
}

}  // namespace

void begin() {
  // usb_midi.setStringDescriptor() has no effect on ESP32 (Adafruit_TinyUSB
  // defers descriptor-building to the core there) - set the product name via
  // the core's own USB object instead, before USB.begin().
  USB.productName("Spark GO Bridge");
  MIDI.begin(MIDI_CHANNEL_OMNI);
  MIDI.setHandleProgramChange(handleProgramChange);
  MIDI.setHandleControlChange(handleControlChange);

  // On ESP32, Adafruit_TinyUSB's begin()/MIDI.begin() only *register* the
  // MIDI interface with the core's descriptor builder (done automatically in
  // Adafruit_USBD_MIDI's constructor, before setup() even runs) - they do
  // NOT bring up the actual USB hardware or start the tud_task() loop. That
  // only happens inside the core's own USB.begin() (normally triggered
  // automatically by CDC-on-boot, which this firmware doesn't use) - without
  // this explicit call, the dongle never enumerates as a USB device at all,
  // confirmed on real hardware (TinyUSBDevice.mounted() stayed false
  // forever until this was added).
  USB.begin();
}

void loop() { MIDI.read(); }

String lastEventText() { return g_lastEvent; }

}  // namespace midi_bridge
