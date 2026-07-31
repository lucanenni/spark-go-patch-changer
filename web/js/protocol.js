"use strict";

// ---- Spark GO GATT profile ----
const SERVICE_UUID = "0000ffc0-0000-1000-8000-00805f9b34fb";
const WRITE_CHAR_UUID = "0000ffc1-0000-1000-8000-00805f9b34fb";  // write / write-without-response / read
const NOTIFY_CHAR_UUID = "0000ffc2-0000-1000-8000-00805f9b34fb"; // notify / read

// ---- Protocol ----
const PRESET_HEADER = new Uint8Array([0x01,0xFE,0x00,0x00,0x53,0xFE,0x1A,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00]);
const TUNER_HEADER = new Uint8Array([0x01,0xFE,0x00,0x00,0x53,0xFE,0x19,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00]);
let seq = 0x20;

function concatBytes(a, b){
  const out = new Uint8Array(a.length + b.length);
  out.set(a, 0);
  out.set(b, a.length);
  return out;
}

function buildPatchPayload(patchNumber){
  if (![1,2,3,4].includes(patchNumber)) throw new Error("patchNumber must be 1..4");
  const patchId = patchNumber - 1;
  const inner = new Uint8Array([0xF0, 0x01, seq & 0xFF, patchId, 0x01, 0x38, 0x00, 0x00, patchId, 0xF7]);
  seq = (seq + 1) & 0xFF;
  return concatBytes(PRESET_HEADER, inner);
}

// SEQ is the same shared, continuously-incrementing counter used by buildPatchPayload -
// the device tracks one sequence number across every command regardless of type, and
// mixing an independent counter in here previously desynced it and silently broke
// subsequent patch changes (see PROTOCOL.md).
function buildTunerStartPayload(){
  const inner = new Uint8Array([0xF0, 0x01, seq & 0xFF, 0x42, 0x01, 0x65, 0x01, 0x43, 0xF7]);
  seq = (seq + 1) & 0xFF;
  return concatBytes(TUNER_HEADER, inner);
}

function buildTunerStopPayload(){
  const inner = new Uint8Array([0xF0, 0x01, seq & 0xFF, 0x43, 0x01, 0x65, 0x01, 0x42, 0xF7]);
  seq = (seq + 1) & 0xFF;
  return concatBytes(TUNER_HEADER, inner);
}

function buildHeader(innerLen){
  const totalLen = 16 + innerLen;
  return new Uint8Array([0x01, 0xFE, 0x00, 0x00, 0x53, 0xFE, totalLen & 0xFF, 0,0,0,0,0,0,0,0,0]);
}

// ---- Effect toggle / preset read (see PROTOCOL.md "Individual effect toggling" and
// "Reading the current preset"). Every command/response inner payload beyond
// F0 01 SEQ CHECKSUM CMD SUB_CMD is packed 8-bit -> 7-bit, SysEx-style: split into
// groups of up to 7 bytes, each group prefixed with a "bit8" byte recording which of
// the 7 bytes had their top bit set (so every byte on the wire stays under 0x80).
// CHECKSUM is the XOR of every byte in that packed payload - confirmed against real
// hardware for multiple pedal names, both On and Off.
const SLOT_LABELS = ["Gate", "Comp/Wah", "Drive", "Amp", "MOD/EQ", "Delay", "Reverb"];

function pack7bit(data8){
  const out = [];
  for (let start = 0; start < data8.length; start += 7){
    const group = data8.slice(start, start + 7);
    let bit8 = 0;
    const packed = [];
    for (let idx = 0; idx < group.length; idx++){
      const b = group[idx];
      if (b & 0x80) bit8 |= (1 << idx);
      packed.push(b & 0x7F);
    }
    out.push(bit8, ...packed);
  }
  return new Uint8Array(out);
}

function unpack7bit(data7){
  const out = [];
  let i = 0;
  while (i < data7.length){
    const bit8 = data7[i];
    const group = data7.slice(i + 1, i + 8);
    i += 1 + group.length;
    for (let idx = 0; idx < group.length; idx++){
      let b = group[idx];
      if (bit8 & (1 << idx)) b |= 0x80;
      out.push(b);
    }
  }
  return new Uint8Array(out);
}

function xorAll(data){
  let x = 0;
  for (const b of data) x ^= b;
  return x;
}

// Toggle the pedal identified by its internal codename (NOT the display name shown in
// the app - see PROTOCOL.md). Use a preset read to find the real current name/state
// for a slot instead of guessing.
function buildEffectTogglePayload(internalName, on){
  const nameBytes = new TextEncoder().encode(internalName);
  const data8 = new Uint8Array(2 + nameBytes.length + 2);
  data8[0] = nameBytes.length;
  data8[1] = nameBytes.length + 0xA0;
  data8.set(nameBytes, 2);
  data8[2 + nameBytes.length] = on ? 0xC3 : 0xC2;
  data8[3 + nameBytes.length] = 0x00;
  const data7 = pack7bit(data8);
  const checksum = xorAll(data7);
  const inner = new Uint8Array(6 + data7.length + 1);
  inner.set([0xF0, 0x01, seq & 0xFF, checksum, 0x01, 0x15], 0);
  inner.set(data7, 6);
  inner[6 + data7.length] = 0xF7;
  seq = (seq + 1) & 0xFF;
  return concatBytes(buildHeader(inner.length), inner);
}

// Ask the device to send back the full pedal chain of saved patch presetNum (0-based,
// same numbering as buildPatchPayload's patchId). The response is a multi-chunk
// CMD 0x03/SUB_CMD 0x01 message reassembled in app.js's handleNotificationBytes/processChunk.
function buildPresetRequestPayload(presetNum){
  const inner = new Uint8Array(9 + 32 + 3);
  inner.set([0xF0, 0x01, seq & 0xFF, 0x00, 0x02, 0x01, 0x00, 0x00, presetNum & 0xFF], 0);
  inner[inner.length - 1] = 0xF7; // last byte; the padding + the two before it stay 0x00
  seq = (seq + 1) & 0xFF;
  return concatBytes(buildHeader(inner.length), inner);
}

// Ask the device which patch is actually active right now (CMD 0x02/SUB_CMD 0x10) -
// unlike buildPresetRequestPayload, which reads a specific saved slot by number and
// has no way to confirm that's the one really loaded. The response is a single short
// CMD 0x03/SUB_CMD 0x10 message, not multi-chunk.
function buildStateRequestPayload(){
  const inner = new Uint8Array(6 + 37 + 1);
  inner.set([0xF0, 0x01, seq & 0xFF, 0x00, 0x02, 0x10], 0);
  inner[inner.length - 1] = 0xF7;
  seq = (seq + 1) & 0xFF;
  return concatBytes(buildHeader(inner.length), inner);
}

function readString(data, pos){
  let aByte = data[pos]; pos++;
  let strLen;
  if (aByte === 0xD9){ // str8: one length byte follows
    strLen = data[pos]; pos++;
  } else if (aByte === 0xDA){ // str16: two big-endian length bytes follow
    strLen = (data[pos] << 8) | data[pos + 1]; pos += 2;
  } else if (aByte === 0xDB){ // str32: four big-endian length bytes follow
    strLen = (data[pos] * 0x1000000) + (data[pos+1] << 16) + (data[pos+2] << 8) + data[pos+3]; pos += 4;
  } else if (aByte >= 0xA0 && aByte <= 0xBF){ // fixstr: length encoded in the byte itself
    strLen = aByte - 0xA0;
  } else {
    // Legacy fallback for the effect-toggle confirmation's wire shape (see
    // parseEffectStateNotification), which prepends a raw length byte before the
    // fixstr-style second byte - not a real preset-read string encoding.
    strLen = data[pos] - 0xA0; pos++;
  }
  const str = new TextDecoder().decode(data.slice(pos, pos + strLen));
  return [str, pos + strLen];
}

function readFloat(data, pos){
  pos++; // skip the 0xCA prefix byte
  const buf = new ArrayBuffer(4);
  const view = new DataView(buf);
  for (let i = 0; i < 4; i++) view.setUint8(i, data[pos + i]);
  return [view.getFloat32(0, false), pos + 4]; // big-endian
}

// Parse a reassembled preset-read response (see PROTOCOL.md "Reading the current
// preset") into {presetNum, uuid, name, version, description, icon, bpm, pedals:[...]}.
// Each pedal is {name (internal codename), on (bool), params: [{id, value}, ...]}.
function parsePresetData(data){
  let pos = 1; // skip one unknown leading byte
  const presetNum = data[pos]; pos++;
  let uuid, name, version, description, icon, bpm;
  [uuid, pos] = readString(data, pos);
  [name, pos] = readString(data, pos);
  [version, pos] = readString(data, pos);
  [description, pos] = readString(data, pos);
  [icon, pos] = readString(data, pos);
  [bpm, pos] = readFloat(data, pos);
  const numPedals = data[pos] - 0x90; pos++;
  const pedals = [];
  for (let i = 0; i < numPedals; i++){
    let pedalName;
    [pedalName, pos] = readString(data, pos);
    const on = data[pos] === 0xC3; pos++;
    const numParams = data[pos] - 0x90; pos++;
    const params = [];
    for (let p = 0; p < numParams; p++){
      const paramId = data[pos];
      pos += 2; // skip param_id and the fixed 0x91 spec byte
      let val;
      [val, pos] = readFloat(data, pos);
      params.push({ id: paramId, value: val });
    }
    pedals.push({ name: pedalName, on, params });
  }
  return { presetNum, uuid, name, version, description, icon, bpm, pedals };
}

// Parse a CMD 0x03/SUB_CMD 0x15 notification: the device's own real-time confirmation
// of an effect's new on/off state, sent unsolicited right after we (or the official
// app, or a footswitch) change it. Distinct from - and more reliable than - re-reading
// a saved preset, which reflects what's stored for that patch slot, not the live
// current state (toggling doesn't rewrite the saved preset).
function parseEffectStateNotification(data){
  const [name, pos] = readString(data, 0);
  return { name, on: data[pos] === 0xC3 };
}

// Parse a CMD 0x03/SUB_CMD 0x10 notification (response to buildStateRequestPayload):
// which patch is truly active on the device right now, 0-based. data[0] is an
// unknown/reserved byte.
function parseActivePatchNotification(data){
  return data[1];
}

// ---- Guitar volume and tap tempo ----
//
// Both reverse-engineered from paulhamsh/SparkIO6 (a newer, more complete community
// firmware than the repos everything else in this file is based on - its own
// comments explicitly cover "40 / GO / MINI") and CONFIRMED on real Spark GO
// hardware. The source project's "MIXER" enum also documents a channel 5 ("MUSIC"),
// but the Spark GO's physical Music Volume buttons turned out to be plain Bluetooth
// AVRCP volume commands sent to the paired phone/audio source - nothing to do with
// this GATT protocol at all - so there's no reason to believe channel 5 controls
// anything meaningful here, and it's not exposed by either reference client. See
// PROTOCOL.md's "Mixer" section for the full story.
const MIXER_CHANNEL_GUITAR = 0; // "IN1" in the source comments - CONFIRMED

function buildFloat(value){
  const buf = new ArrayBuffer(4);
  new DataView(buf).setFloat32(0, value, false); // big-endian
  return concatBytes(new Uint8Array([0xCA]), new Uint8Array(buf));
}

// Set a mixer channel's volume (CMD 0x01/SUB_CMD 0x33). `value` is 0.0-1.0, matching
// every other float parameter in this protocol. CONFIRMED on real Spark GO hardware
// for MIXER_CHANNEL_GUITAR - see PROTOCOL.md's "Mixer" section. No confirmation/ack
// for this command has been observed in the source project, so clients apply it
// optimistically rather than waiting for one.
function buildMixerPayload(channel, value){
  const data8 = concatBytes(new Uint8Array([channel & 0xFF]), buildFloat(value));
  const data7 = pack7bit(data8);
  const checksum = xorAll(data7);
  const inner = new Uint8Array(6 + data7.length + 1);
  inner.set([0xF0, 0x01, seq & 0xFF, checksum, 0x01, 0x33], 0);
  inner.set(data7, 6);
  inner[6 + data7.length] = 0xF7;
  seq = (seq + 1) & 0xFF;
  return concatBytes(buildHeader(inner.length), inner);
}

// Parse an unsolicited CMD 0x01 or 0x03/SUB_CMD 0x33 message reporting a mixer
// channel's current value - same shape as buildMixerPayload's own request, since the
// source project's parser doesn't distinguish a separate response shape for this
// command (unlike patch change or effect toggle).
function parseMixerNotification(data){
  const channel = data[0];
  const [value] = readFloat(data, 1);
  return { channel, value };
}

// Ask the device for a mixer channel's current value (CMD 0x02/SUB_CMD 0x33) - the
// source project documents this pairing as Spark LIVE-specific (the classic
// 40/GO/MINI section has no read/request command for the mixer at all). CONFIRMED
// NOT TO WORK on real Spark GO hardware: sends fine (TX logged) but never gets any
// response back, for the Guitar channel either. Currently unused - kept only in case
// a future BLE sniff of the official app finds the real request shape.
function buildMixerRequestPayload(channel){
  const data8 = new Uint8Array([channel & 0xFF]);
  const data7 = pack7bit(data8);
  const checksum = xorAll(data7);
  const inner = new Uint8Array(6 + data7.length + 1);
  inner.set([0xF0, 0x01, seq & 0xFF, checksum, 0x02, 0x33], 0);
  inner.set(data7, 6);
  inner[6 + data7.length] = 0xF7;
  seq = (seq + 1) & 0xFF;
  return concatBytes(buildHeader(inner.length), inner);
}

// Parse a CMD 0x03/SUB_CMD 0x33 response to buildMixerRequestPayload: just a float,
// no channel byte - unlike parseMixerNotification's shape, the caller has to already
// know which channel it asked about (see app.js's mixerChannelsPending queue).
function parseMixerValueResponse(data){
  const [value] = readFloat(data, 0);
  return value;
}

// Send a computed tap-tempo BPM to sync tempo-based effects (CMD 0x01/SUB_CMD 0x62).
// CONFIRMED on real Spark GO hardware, despite the source project itself flagging
// this sub-command with a "is this right??" comment and no code in that project
// actually calling it. `bpm` is a plain beats-per-minute float; the trailing
// 0x3F 0x3F is a fixed/reserved suffix copied verbatim from the source, purpose
// still unknown but works as-is.
function buildTapTempoPayload(bpm){
  const data8 = concatBytes(buildFloat(bpm), new Uint8Array([0x3F, 0x3F]));
  const data7 = pack7bit(data8);
  const checksum = xorAll(data7);
  const inner = new Uint8Array(6 + data7.length + 1);
  inner.set([0xF0, 0x01, seq & 0xFF, checksum, 0x01, 0x62], 0);
  inner.set(data7, 6);
  inner[6 + data7.length] = 0xF7;
  seq = (seq + 1) & 0xFF;
  return concatBytes(buildHeader(inner.length), inner);
}

// ---- Tuner frame parsing (rough, uncalibrated) ----
const NOTE_NAMES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"];
// From PROTOCOL.md's tuner calibration notes: "0 cents" consistently sits at ~8064
// regardless of note (matches the idle frame's default), and +-50 cents roughly spans
// +-345 counter units. Both numbers are provisional, not a confirmed scale.
const TUNER_CENTER = 8064;
const TUNER_HALF_RANGE = 345; // counter units corresponding to ~50 cents

function parseTunerFrame(bytes){
  // Expected shape: F0 01 CTR ?? 03 64 ?? NOTE 4A HI LO ?? ?? F7  (14 bytes)
  if (bytes.length !== 14 || bytes[0] !== 0xF0 || bytes[1] !== 0x01) return null;
  if (bytes[4] !== 0x03 || bytes[5] !== 0x64) return null;
  const note = bytes[7];
  const hi = bytes[9] & 0x7F;
  const lo = bytes[10] & 0x7F;
  const idle = (bytes[6] === 0x0e && hi === 0x3f && bytes[10] === 0 && bytes[11] === 0 && bytes[12] === 0);
  const counter = (hi << 7) | lo;
  const cents = ((counter - TUNER_CENTER) / TUNER_HALF_RANGE) * 50;
  return { idle, note, noteName: NOTE_NAMES[note] || "?", counter, cents };
}

function fmtHex(bytes){
  return Array.from(bytes).map(b => b.toString(16).toUpperCase().padStart(2,"0")).join(" ");
}
