#include "midi_bridge.h"

#include <Adafruit_TinyUSB.h>
#include <MIDI.h>
#include <USB.h>

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

  if (number == config::kTapTempoCc || number == config::kMasterVolumeCc ||
      number == config::kChannelVolumeCc) {
    // No known Spark GO command for these anywhere in this repo's protocol
    // notes - see README/plan. Logged rather than guessed at.
    g_lastEvent = String("CC") + number + " unsupported";
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
