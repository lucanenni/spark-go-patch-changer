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
