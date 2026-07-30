#pragma once

// Positive Grid Spark GO BLE wire protocol: envelope, payload builders, and
// notification parsers. A direct port of the already hardware-validated
// Python reference (see PROTOCOL.md and the plan for the full writeup) - no
// protocol re-derivation happens here, just a change of language.
//
// Not covered (no known command exists anywhere in this repo's
// reverse-engineering notes): tap tempo, master/channel volume.

#include <Arduino.h>

#include <cstdint>
#include <vector>

namespace spark_protocol {

using Bytes = std::vector<uint8_t>;

inline constexpr uint8_t kDefaultSeq = 0x20;
inline constexpr size_t kSlotCount = 7;

// Fixed pedal-chain slot order the device itself uses - confirmed from a
// real decoded preset. Lines up 1:1 with the CC0-6 mapping.
extern const char* const kSlotLabels[kSlotCount];

// A single rolling sequence counter shared across *every* command sent in a
// session (patch change, tuner, effect toggle alike). Mixing independent
// counters per command family is a confirmed bug that silently breaks
// subsequent patch changes - see the plan/PROTOCOL.md notes on this.
class SeqCounter {
 public:
  explicit SeqCounter(uint8_t start = kDefaultSeq) : seq_(start) {}

  // Returns the current value and advances the counter, wrapping at 0xFF.
  uint8_t consume() {
    uint8_t s = seq_;
    seq_ = static_cast<uint8_t>(seq_ + 1);
    return s;
  }

 private:
  uint8_t seq_;
};

// --- Outgoing payload builders (each returns a full, ready-to-write frame:
// 16-byte header + inner F0 01 ... F7 payload) ---

// patchNumber is 1-based, 1-4 (confirmed on real hardware - the Spark GO
// only exposes 4 addressable patch slots). Returns an empty vector if
// patchNumber is out of range.
Bytes buildPatchPayload(uint8_t patchNumber, uint8_t seq);

Bytes buildTunerStartPayload(uint8_t seq);
Bytes buildTunerStopPayload(uint8_t seq);

// internalName must be the pedal's internal codename (e.g. "ChorusAnalog"),
// never the display name shown in the app - see spark_state for how the
// codename is learned from the device instead of guessed.
Bytes buildEffectTogglePayload(const String& internalName, bool on, uint8_t seq);

// presetNum is 0-based (matches buildPatchPayload's patchId, i.e. patchNumber - 1).
Bytes buildPresetRequestPayload(uint8_t presetNum, uint8_t seq);

Bytes buildActivePatchRequestPayload(uint8_t seq);

// --- 7-bit packing (SysEx-style: every on-wire byte stays under 0x80) ---
Bytes pack7Bit(const Bytes& data8);
Bytes unpack7Bit(const Bytes& data7);
uint8_t xorAll(const Bytes& data);

// --- Parsed notification shapes ---

struct PedalState {
  String name;  // internal codename
  bool on = false;
};

struct PresetData {
  uint8_t presetNum = 0;
  String name;
  float bpm = 0;
  uint8_t pedalCount = 0;
  PedalState pedals[kSlotCount];
};

struct EffectStateEvent {
  String name;
  bool on = false;
};

struct TunerFrame {
  bool idle = false;
  uint8_t note = 0;  // 0=C .. 11=B
  uint16_t counter = 0;
  float cents = 0;  // provisional/uncalibrated, see PROTOCOL.md
};

// data8 is the already-7bit-unpacked payload of a CMD 0x03/SUB_CMD 0x01
// reassembled preset dump (see spark_ble's chunk reassembly). Returns false
// on any parse/bounds failure rather than reading out of range.
bool parsePresetData(const Bytes& data8, PresetData& out);

// data8 is the unpacked payload of a CMD 0x03/SUB_CMD 0x15 notification.
bool parseEffectStateEvent(const Bytes& data8, EffectStateEvent& out);

// data8 is the unpacked payload of a CMD 0x03/SUB_CMD 0x10 notification.
bool parseActivePatchEvent(const Bytes& data8, uint8_t& outPatch0Based);

// raw is a single already-reassembled tuner frame (14 bytes, F0 01 ... F7,
// NOT 7-bit packed - tuner frames are sent as raw bytes unlike the
// preset/effect-toggle family). Returns false if this isn't a tuner data
// frame at all (e.g. it's some other short notification).
bool parseTunerFrame(const Bytes& raw, TunerFrame& out);

const char* noteName(uint8_t note);

}  // namespace spark_protocol
