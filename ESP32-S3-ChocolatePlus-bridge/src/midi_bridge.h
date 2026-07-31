#pragma once

// USB-MIDI device role (TinyUSB) - this is what makes the dongle enumerate
// as a class-compliant MIDI device when plugged into the Chocolate Plus's
// USB HOST port. Parses incoming Program Change / Control Change messages
// per the mapping table in config.h and drives spark_ble / spark_state /
// tuner accordingly.

#include <Arduino.h>

namespace midi_bridge {

void begin();
// Polls for incoming USB-MIDI messages. Call every loop() iteration.
void loop();

// Human-readable description of the most recent MIDI message handled and
// what it did (or why it was ignored), for the status display.
String lastEventText();

}  // namespace midi_bridge
