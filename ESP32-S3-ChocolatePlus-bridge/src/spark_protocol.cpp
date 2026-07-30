#include "spark_protocol.h"

#include <algorithm>
#include <cstring>

namespace spark_protocol {

const char* const kSlotLabels[kSlotCount] = {
    "Gate", "Comp/Wah", "Drive", "Amp", "MOD/EQ", "Delay", "Reverb",
};

namespace {

const char* kNoteNames[12] = {"C", "C#", "D", "D#", "E",  "F",
                               "F#", "G", "G#", "A", "A#", "B"};

// From PROTOCOL.md's calibration notes: "0 cents" consistently sits at
// ~8064 regardless of note (matches the idle-frame default), and +-50 cents
// roughly spans +-345 counter units. Both provisional, not a confirmed scale.
constexpr int kTunerCenter = 8064;
constexpr int kTunerHalfRange = 345;

Bytes buildHeader(size_t innerLen) {
  Bytes header = {0x01, 0xFE, 0x00, 0x00, 0x53, 0xFE,
                   static_cast<uint8_t>(16 + innerLen)};
  header.resize(16, 0x00);
  return header;
}

Bytes withHeader(Bytes inner) {
  Bytes out = buildHeader(inner.size());
  out.insert(out.end(), inner.begin(), inner.end());
  return out;
}

// Mirrors the Python reference's _read_string: returns false (rather than
// throwing) if the buffer runs out before the declared string does.
bool readString(const Bytes& data, size_t& pos, String& out) {
  if (pos >= data.size()) return false;
  uint8_t firstByte = data[pos++];
  size_t strLen;
  if (firstByte == 0xD9) {
    if (pos >= data.size()) return false;
    strLen = data[pos++];
  } else if (firstByte >= 0xA0) {
    strLen = firstByte - 0xA0;
  } else {
    if (pos >= data.size()) return false;
    strLen = data[pos++] - 0xA0;
  }
  if (pos + strLen > data.size()) return false;
  out = "";
  for (size_t i = 0; i < strLen; ++i) out += static_cast<char>(data[pos + i]);
  pos += strLen;
  return true;
}

// Mirrors _read_float: one 0xCA prefix byte + 4 big-endian IEEE754 bytes.
bool readFloat(const Bytes& data, size_t& pos, float& out) {
  if (pos + 1 + 4 > data.size()) return false;
  pos += 1;  // skip 0xCA prefix
  uint32_t bits = (static_cast<uint32_t>(data[pos]) << 24) |
                  (static_cast<uint32_t>(data[pos + 1]) << 16) |
                  (static_cast<uint32_t>(data[pos + 2]) << 8) |
                  static_cast<uint32_t>(data[pos + 3]);
  static_assert(sizeof(float) == sizeof(uint32_t), "expects 32-bit float");
  memcpy(&out, &bits, sizeof(out));
  pos += 4;
  return true;
}

}  // namespace

Bytes buildPatchPayload(uint8_t patchNumber, uint8_t seq) {
  if (patchNumber < 1 || patchNumber > 4) return {};
  uint8_t patchId = patchNumber - 1;
  Bytes inner = {0xF0, 0x01, seq, patchId, 0x01, 0x38, 0x00, 0x00, patchId, 0xF7};
  return withHeader(std::move(inner));
}

Bytes buildTunerStartPayload(uint8_t seq) {
  Bytes inner = {0xF0, 0x01, seq, 0x42, 0x01, 0x65, 0x01, 0x43, 0xF7};
  return withHeader(std::move(inner));
}

Bytes buildTunerStopPayload(uint8_t seq) {
  Bytes inner = {0xF0, 0x01, seq, 0x43, 0x01, 0x65, 0x01, 0x42, 0xF7};
  return withHeader(std::move(inner));
}

Bytes pack7Bit(const Bytes& data8) {
  Bytes out;
  for (size_t start = 0; start < data8.size(); start += 7) {
    size_t groupLen = std::min<size_t>(7, data8.size() - start);
    uint8_t bit8 = 0;
    Bytes packed;
    for (size_t i = 0; i < groupLen; ++i) {
      uint8_t b = data8[start + i];
      if (b & 0x80) bit8 |= static_cast<uint8_t>(1 << i);
      packed.push_back(b & 0x7F);
    }
    out.push_back(bit8);
    out.insert(out.end(), packed.begin(), packed.end());
  }
  return out;
}

Bytes unpack7Bit(const Bytes& data7) {
  Bytes out;
  size_t i = 0;
  while (i < data7.size()) {
    uint8_t bit8 = data7[i];
    size_t groupLen = std::min<size_t>(7, data7.size() - i - 1);
    i += 1;
    for (size_t idx = 0; idx < groupLen; ++idx) {
      uint8_t b = data7[i + idx];
      if (bit8 & (1 << idx)) b |= 0x80;
      out.push_back(b);
    }
    i += groupLen;
  }
  return out;
}

uint8_t xorAll(const Bytes& data) {
  uint8_t x = 0;
  for (uint8_t b : data) x ^= b;
  return x;
}

Bytes buildEffectTogglePayload(const String& internalName, bool on, uint8_t seq) {
  Bytes data8;
  uint8_t nameLen = static_cast<uint8_t>(internalName.length());
  data8.push_back(nameLen);
  data8.push_back(static_cast<uint8_t>(nameLen + 0xA0));
  for (size_t i = 0; i < internalName.length(); ++i) {
    data8.push_back(static_cast<uint8_t>(internalName[i]));
  }
  data8.push_back(on ? 0xC3 : 0xC2);
  data8.push_back(0x00);

  Bytes data7 = pack7Bit(data8);
  uint8_t checksum = xorAll(data7);

  Bytes inner = {0xF0, 0x01, seq, checksum, 0x01, 0x15};
  inner.insert(inner.end(), data7.begin(), data7.end());
  inner.push_back(0xF7);
  return withHeader(std::move(inner));
}

Bytes buildPresetRequestPayload(uint8_t presetNum, uint8_t seq) {
  Bytes inner = {0xF0, 0x01, seq, 0x00, 0x02, 0x01, 0x00, 0x00, presetNum};
  inner.insert(inner.end(), 32, 0x00);  // padding, purpose unconfirmed upstream
  inner.push_back(0x00);
  inner.push_back(0x00);
  inner.push_back(0xF7);
  return withHeader(std::move(inner));
}

Bytes buildActivePatchRequestPayload(uint8_t seq) {
  Bytes inner = {0xF0, 0x01, seq, 0x00, 0x02, 0x10};
  inner.insert(inner.end(), 37, 0x00);
  inner.push_back(0xF7);
  return withHeader(std::move(inner));
}

bool parsePresetData(const Bytes& data8, PresetData& out) {
  size_t pos = 1;  // skip one unknown leading byte
  if (pos >= data8.size()) return false;
  out.presetNum = data8[pos++];

  String uuid, version, description, icon;
  if (!readString(data8, pos, uuid)) return false;
  if (!readString(data8, pos, out.name)) return false;
  if (!readString(data8, pos, version)) return false;
  if (!readString(data8, pos, description)) return false;
  if (!readString(data8, pos, icon)) return false;
  if (!readFloat(data8, pos, out.bpm)) return false;

  if (pos >= data8.size()) return false;
  int numPedals = data8[pos++] - 0x90;
  if (numPedals < 0 || static_cast<size_t>(numPedals) > kSlotCount) return false;
  out.pedalCount = static_cast<uint8_t>(numPedals);

  for (int i = 0; i < numPedals; ++i) {
    PedalState& pedal = out.pedals[i];
    if (!readString(data8, pos, pedal.name)) return false;
    if (pos >= data8.size()) return false;
    pedal.on = (data8[pos++] == 0xC3);
    if (pos >= data8.size()) return false;
    int numParams = data8[pos++] - 0x90;
    if (numParams < 0) return false;
    for (int p = 0; p < numParams; ++p) {
      if (pos + 2 > data8.size()) return false;
      pos += 2;  // param_id + fixed 0x91 spec byte
      float value;
      if (!readFloat(data8, pos, value)) return false;
      (void)value;  // params aren't used by this bridge, only presence/shape
    }
  }
  return true;
}

bool parseEffectStateEvent(const Bytes& data8, EffectStateEvent& out) {
  size_t pos = 0;
  if (!readString(data8, pos, out.name)) return false;
  if (pos >= data8.size()) return false;
  out.on = (data8[pos] == 0xC3);
  return true;
}

bool parseActivePatchEvent(const Bytes& data8, uint8_t& outPatch0Based) {
  if (data8.size() < 2) return false;
  outPatch0Based = data8[1];
  return true;
}

bool parseTunerFrame(const Bytes& raw, TunerFrame& out) {
  if (raw.size() != 14 || raw[0] != 0xF0 || raw[1] != 0x01) return false;
  if (raw[4] != 0x03 || raw[5] != 0x64) return false;

  out.note = raw[7];
  uint8_t hi = raw[9] & 0x7F;
  uint8_t lo = raw[10] & 0x7F;
  out.idle = (raw[6] == 0x0E && hi == 0x3F && raw[10] == 0 && raw[11] == 0 && raw[12] == 0);
  out.counter = static_cast<uint16_t>((hi << 7) | lo);
  out.cents = (static_cast<float>(out.counter) - kTunerCenter) / kTunerHalfRange * 50.0f;
  return true;
}

const char* noteName(uint8_t note) {
  return note < 12 ? kNoteNames[note] : "?";
}

}  // namespace spark_protocol
