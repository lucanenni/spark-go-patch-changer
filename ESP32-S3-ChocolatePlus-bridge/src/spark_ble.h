#pragma once

// NimBLE central role: finds and connects to the Spark GO, writes commands,
// and reassembles/parses its notifications. Mirrors ble_backend.py's shape
// (scan/connect/disconnect/send_patch/tuner_start/tuner_stop/toggle_effect/
// request_preset/request_active_patch) with one difference: characteristics
// are discovered by UUID rather than hardcoded handles, which is more robust
// for an unattended embedded client than the desktop app's fixed-handle
// shortcut.
//
// Known limitation: (re)connect attempts (scan + connect) block for their
// duration - acceptable since they're rare (startup + occasional
// reconnects), but USB-MIDI input isn't serviced while one is in flight.

#include <Arduino.h>

#include <functional>

#include "spark_protocol.h"

namespace spark_ble {

enum class ConnectionState { kDisconnected, kScanning, kConnecting, kConnected };

// Fired whenever ConnectionState changes.
using ConnectionStateCallback = std::function<void(ConnectionState)>;
// Fired when a patch-change confirmation (CMD 0x03/SUB_CMD 0x38) arrives.
using PatchConfirmedCallback = std::function<void(uint8_t patch0Based)>;
// Fired on a fully reassembled preset read.
using PresetCallback = std::function<void(const spark_protocol::PresetData&)>;
// Fired on a real-time effect-state confirmation.
using EffectStateCallback = std::function<void(const spark_protocol::EffectStateEvent&)>;
// Fired on every reassembled tuner data frame.
using TunerFrameCallback = std::function<void(const spark_protocol::TunerFrame&)>;

void begin();
// Drives the connection state machine (scan/connect/reconnect) and drains
// any pending BLE work. Call every loop() iteration.
void loop();

bool isConnected();
ConnectionState state();

// Diagnostic: total BLE notification callback invocations since boot,
// regardless of content/type. If this stays at 0 while connected, the
// notify subscription itself never delivers anything (a BLE-level issue,
// independent of any parsing); if it grows, notifications are arriving but
// something downstream (chunk framing, 7-bit unpack, dispatch) is failing.
uint32_t rawNotificationCount();
// Diagnostic: whether the last subscribe() call at connect time reported
// success. Note this can be misleadingly true even when the CCCD descriptor
// was never actually found/written - see the comment at its call site.
bool lastSubscribeOk();
// Diagnostic: whether the CCCD (0x2902) descriptor was actually found on
// the notify characteristic at connect time - a more precise signal than
// lastSubscribeOk() alone, which can be true even when this is false.
bool cccdFound();

// Fire-and-forget command senders. No-ops (return false) if not connected.
bool sendPatch(uint8_t patchNumber1Based);
bool tunerStart();
bool tunerStop();
bool toggleEffect(const String& internalName, bool on);
bool requestPreset(uint8_t presetNum0Based);
bool requestActivePatch();

// value is 0.0-1.0. Only the Guitar channel (spark_protocol::kMixerChannelGuitar)
// is confirmed to do anything on real hardware - see PROTOCOL.md's "Mixer" section.
bool setGuitarVolume(float value);
// bpm is a plain beats-per-minute float, computed by the caller from tap
// intervals - this function just sends it, no timing logic of its own.
bool tapTempo(float bpm);

// Ask the state machine to drop the current connection and reconnect from
// scratch (used by the BOOT-button "force reconnect" trigger).
void forceReconnect();

void onConnectionStateChanged(ConnectionStateCallback cb);
void onPatchConfirmed(PatchConfirmedCallback cb);
void onPreset(PresetCallback cb);
void onEffectState(EffectStateCallback cb);
void onTunerFrame(TunerFrameCallback cb);

}  // namespace spark_ble
