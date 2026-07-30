#pragma once

// Local tuner on/off tracking + latest decoded frame, driving the display's
// tuner view. Unlike the effect-toggle slots (spark_state), there's no
// preset data to seed an initial tuner state from - the device doesn't
// report whether the tuner is on anywhere except by streaming data frames
// while it is. So this is a locally-tracked toggle, flipped each time a
// "Toggle Tuner" CC message arrives (footswitches are configured to send one
// message per press, not separate on/off messages - see PROTOCOL.md/README).

#include "spark_protocol.h"

namespace tuner {

void begin();

// Call on every incoming "Toggle Tuner" CC message. Flips the local on/off
// state and sends the corresponding BLE command via spark_ble. Returns the
// new state (true = now on).
bool toggle();

bool isOn();

// Turns the tuner off if it's currently on (sends tunerStop() and resets the
// reading), a no-op otherwise. Unlike toggle(), never turns it on. Call this
// on any incoming MIDI command other than the tuner toggle itself (patch
// change, effect toggle) - mirrors a real pedal, where you can't be tuning
// and switching patches/effects at the same time; any other footswitch
// press implicitly exits tuner mode first.
void forceOff();

// Feed a decoded tuner data frame in (wire this to spark_ble::onTunerFrame).
// Has no effect if the tuner is currently considered off locally.
void handleFrame(const spark_protocol::TunerFrame& frame);

// Latest known reading, for the display to render. hasSignal is false if the
// tuner is off, or on but no note has been detected yet ("idle" frames).
struct Reading {
  bool hasSignal = false;
  const char* noteName = "-";
  float cents = 0;
};
Reading currentReading();

}  // namespace tuner
