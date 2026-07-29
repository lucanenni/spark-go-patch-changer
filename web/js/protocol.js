"use strict";

// ---- Spark GO GATT profile ----
const SERVICE_UUID = "0000ffc0-0000-1000-8000-00805f9b34fb";
const WRITE_CHAR_UUID = "0000ffc1-0000-1000-8000-00805f9b34fb";  // write / write-without-response / read
const NOTIFY_CHAR_UUID = "0000ffc2-0000-1000-8000-00805f9b34fb"; // notify / read

// ---- Protocol ----
const PRESET_HEADER = new Uint8Array([0x01,0xFE,0x00,0x00,0x53,0xFE,0x1A,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00]);
let seq = 0x20;

function buildPatchPayload(patchNumber){
  if (![1,2,3,4].includes(patchNumber)) throw new Error("patchNumber must be 1..4");
  const patchId = patchNumber - 1;
  const inner = new Uint8Array([0xF0, 0x01, seq & 0xFF, patchId, 0x01, 0x38, 0x00, 0x00, patchId, 0xF7]);
  seq = (seq + 1) & 0xFF;
  const payload = new Uint8Array(PRESET_HEADER.length + inner.length);
  payload.set(PRESET_HEADER, 0);
  payload.set(inner, PRESET_HEADER.length);
  return payload;
}

function fmtHex(bytes){
  return Array.from(bytes).map(b => b.toString(16).toUpperCase().padStart(2,"0")).join(" ");
}
