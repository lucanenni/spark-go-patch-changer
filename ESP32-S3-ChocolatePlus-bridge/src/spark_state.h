#pragma once

// Live cache of "what's actually on the Spark GO right now": active patch
// number and, per fixed pedal-chain slot, the pedal's internal codename and
// current on/off state.
//
// Seeded by reading the active preset (spark_protocol::PresetData) on
// connect and after every patch change; updated afterward only from the
// device's own real-time effect-state confirmations, never by re-reading the
// preset (that reflects saved/flash data, not live state - see PROTOCOL.md).

#include <Arduino.h>

#include "spark_protocol.h"

namespace spark_state {

void reset();

void applyPreset(const spark_protocol::PresetData& preset);
void applyEffectState(const spark_protocol::EffectStateEvent& event);
void setActivePatch(uint8_t patch0Based);

// Returns false if slotIndex is out of range or nothing has been read into
// that slot yet (e.g. not connected, or preset not read).
bool getSlot(uint8_t slotIndex, String& outName, bool& outOn);

int activePatch0Based();  // -1 if unknown
String activePatchName();  // "" if unknown (preset not read yet)

}  // namespace spark_state
