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
  g_activePatch0Based = preset.presetNum;
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
