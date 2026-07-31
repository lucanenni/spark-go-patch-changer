#pragma once

// 0.96" ST7735 status screen. Deliberately "dumb" - callers (main.cpp) decide
// what to show and when; this module only knows how to draw it. Three views:
// - status: connection/rx/subscribe diagnostics - shown before a BLE
//   connection is established (or if it's lost), since that's when knowing
//   what's going on actually matters.
// - connected: big patch number + patch name + last MIDI command, shown once
//   connected - the diagnostics aren't interesting anymore once things are
//   confirmed working.
// - tuner: detected note + a rough cents bar, shown while the tuner is
//   toggled on (see tuner.h) - takes priority over both of the above.

#include <Arduino.h>

namespace display {

void begin();

// One-shot startup splash (product name), shown once right after begin()
// before the boot checkpoint sequence starts. Caller decides how long to
// hold it - this just draws it once.
void showBootSplash();

// Pre-connection (or connection-lost) diagnostic view: connection state,
// rx/subscribe/CCCD counters, whatever midi_bridge last did. Safe to call on
// every change - it's a tiny display.
void showStatus(const String& connectionLine, int currentPatch1Based, const String& lastEventLine);

// Connected view: current patch number (large) + patch name, and the last
// MIDI command received. Safe to call on every change.
void showConnected(int currentPatch1Based, const String& patchName, const String& lastEventLine);

// Tuner view. Internally rate-limited (tuner data frames can stream faster
// than the SPI link comfortably redraws) - safe to call on every frame.
void showTuner(const char* noteName, float cents, bool hasSignal);

// Call once when switching back from the tuner view to whichever of
// status/connected applies, so the next call redraws even if its content
// happens to be identical to whatever was last shown before the tuner view
// took over.
void invalidate();

}  // namespace display
