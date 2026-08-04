#include "spark_state.h"

namespace spark_state {

namespace {

struct SlotCache {
  String name;
  bool on = false;
  bool known = false;
};

SlotCache g_slots[spark_protocol::kSlotCount];
int g_activePatch0Based = -1;
String g_activePatchName;

}  // namespace

void reset() {
  for (auto& slot : g_slots) {
    slot.name = "";
    slot.on = false;
    slot.known = false;
  }
  g_activePatch0Based = -1;
  g_activePatchName = "";
}

void applyPreset(const spark_protocol::PresetData& preset) {
  // REAL BUG, found on real hardware 2026-08-04 (via the NM-TV-154 ports,
  // which copied this file unchanged): a preset read reflects saved data
  // for whichever slot was requested at request time, but the read itself
  // is slow (multi-chunk reassembly over BLE) - if the active patch
  // changes again (a real-time CMD 0x03/SUB_CMD 0x38 confirmation, handled
  // fast via setActivePatch()) before this read finishes arriving,
  // applying it unconditionally overwrites the already-correct, more
  // recent patch number *and* name with stale data for a patch that's no
  // longer active. Confirmed on real hardware (NM-TV-154): rapid patch
  // changes left the display showing a patch number and name belonging to
  // two different, both-stale patches, neither matching the amp's actual
  // active patch. Fixed by only applying a preset read if its patch number
  // still matches what's currently considered active - a stale read is
  // dropped instead, and a fresh read for the now-current patch (already
  // requested via the same settle-timer mechanism in spark_ble.cpp)
  // supersedes it correctly once it arrives. Likely present here all along
  // too (this file is unchanged) but probably not noticed, since
  // footswitch-driven patch changes over USB-MIDI are naturally slower/more
  // deliberate than the amp-panel button testing that exposed it.
  if (preset.presetNum != g_activePatch0Based) return;
  g_activePatchName = preset.name;
  for (uint8_t i = 0; i < spark_protocol::kSlotCount; ++i) {
    if (i < preset.pedalCount) {
      g_slots[i].name = preset.pedals[i].name;
      g_slots[i].on = preset.pedals[i].on;
      g_slots[i].known = true;
    } else {
      g_slots[i].known = false;
    }
  }
}

void applyEffectState(const spark_protocol::EffectStateEvent& event) {
  // The confirmation only carries a pedal name, not a slot index - find
  // whichever cached slot currently holds that name, same as the reference
  // client's apply_effect_state.
  for (auto& slot : g_slots) {
    if (slot.known && slot.name == event.name) {
      slot.on = event.on;
    }
  }
}

void setActivePatch(uint8_t patch0Based) { g_activePatch0Based = patch0Based; }

bool getSlot(uint8_t slotIndex, String& outName, bool& outOn) {
  if (slotIndex >= spark_protocol::kSlotCount) return false;
  const SlotCache& slot = g_slots[slotIndex];
  if (!slot.known) return false;
  outName = slot.name;
  outOn = slot.on;
  return true;
}

int activePatch0Based() { return g_activePatch0Based; }
String activePatchName() { return g_activePatchName; }

}  // namespace spark_state
