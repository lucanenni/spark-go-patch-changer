#pragma once

#include <cstdint>

// Board/protocol configuration. Kept separate from the modules that use it so
// the mapping table and hardware pins can be tweaked without touching logic.
namespace config {

// --- BLE (Spark GO) ---
inline constexpr const char* kSparkNameFilter = "Spark";  // substring match, case-insensitive
inline constexpr uint32_t kBleScanTimeoutMs = 5000;
inline constexpr uint32_t kBleConnectTimeoutMs = 15000;
inline constexpr uint32_t kReconnectRetryIntervalMs = 3000;
inline constexpr uint32_t kPostConnectSettleMs = 300;  // mirrors the reference client's pause
inline constexpr uint32_t kPostPatchSettleMs = 300;
// How long a preset-read request is given to fully arrive before it's
// treated as abandoned/lost and a new one is allowed to be sent - see
// spark_ble.cpp's loop() comment for the real bug this avoids (overlapping
// preset-read requests during rapid patch changes left the display's patch
// name stuck forever - found on the NM-TV-154 ports, this file unchanged).
inline constexpr uint32_t kPresetReadTimeoutMs = 4000;

// --- USB-MIDI (from the Chocolate Plus's HOST port) ---
// 0 = omni (listen on every channel). Set 1-16 to restrict to a single
// channel if the Chocolate Plus is configured to send on a specific one.
inline constexpr uint8_t kMidiChannel = 0;

// --- MIDI -> Spark mapping (see PROTOCOL.md / plan for the source table) ---
// Program Change 0-3 = presets 1-4 (confirmed on real hardware, matches
// main's patch-change scope - the Spark GO only exposes 4 addressable patch
// slots, so there's no PC 4-7/"Green bank" here).
inline constexpr uint8_t kPatchProgramChangeBase = 0;  // PC 0 -> patch 1
inline constexpr uint8_t kPatchCount = 4;

// Control Change 0-6 toggle the 7 fixed pedal-chain slots, in the device's
// own fixed order (see spark_protocol::kSlotLabels).
inline constexpr uint8_t kEffectToggleCcBase = 0;
inline constexpr uint8_t kEffectToggleCcCount = 7;

// Control Change 7 toggles the tuner on/off and switches the display to the
// tuner view.
inline constexpr uint8_t kTunerToggleCc = 7;

// Control Change 8 taps tempo. There's no protocol-level start/stop concept -
// each tap computes a fresh BPM locally (from up to the last
// kTapTempoMaxSamples intervals, reset if the gap since the previous tap
// exceeds kTapTempoResetGapMs) and sends it immediately. Confirmed working on
// real Spark GO hardware; matches desktop/spark_go_gui.py's tap_tempo().
inline constexpr uint8_t kTapTempoCc = 8;
inline constexpr uint32_t kTapTempoResetGapMs = 2000;
inline constexpr uint8_t kTapTempoMaxSamples = 4;
inline constexpr float kTapTempoMinBpm = 30.0f;
inline constexpr float kTapTempoMaxBpm = 300.0f;

// Control Change 21 sets Guitar Volume (mixer channel
// spark_protocol::kMixerChannelGuitar), confirmed working on real Spark GO
// hardware - value/127 maps MIDI's 0-127 to the protocol's 0.0-1.0 float.
inline constexpr uint8_t kChannelVolumeCc = 21;

// Control Change 20 (Master Volume) is deliberately NOT implemented: there is
// no Spark GO BLE command for it. The amp's physical Music Volume buttons are
// plain Bluetooth AVRCP commands sent to the paired phone, a mechanism
// entirely separate from this GATT service - confirmed by watching the
// phone's own volume change when pressing them. Received but logged as
// unsupported rather than silently ignored, so it's visible on-screen if a
// pedal is mapped to it by mistake.
inline constexpr uint8_t kMasterVolumeCc = 20;

// --- Display SPI pins ---
// Community-reported for this exact AliExpress/GNPE clone of the LilyGO
// T-Dongle-S3 (from a verified buyer review of the listing), NOT from an
// official schematic. Confirm on your actual board before trusting these.
// These also need to match the -DTFT_* build flags in platformio.ini.
inline constexpr int8_t kTftSclk = 10;
inline constexpr int8_t kTftMosi = 11;
inline constexpr int8_t kTftCs = 12;
inline constexpr int8_t kTftDc = 13;
inline constexpr int8_t kTftRst = 14;
// Left unmanaged (always on, whatever the board's default wiring is) -
// confirmed via the manufacturer's own support package/demo firmware
// (Pocket-Dongle-S3-0.96-demo): their working TFT_eSPI User_Setup.h defines
// no TFT_BL pin either, so the backlight isn't GPIO-controlled on this
// board at all.
inline constexpr int8_t kTftBacklightPin = -1;

// GPIO0 = BOOT button, confirmed usable as a plain input at runtime by
// multiple buyer reviews. Wired as a manual "force BLE reconnect" trigger.
inline constexpr int8_t kBootButtonPin = 0;

// TFT_eSPI rotation (0-3, 90 degrees apart). Landscape (rotation 1) was the
// original default; the dongle mounts on the Chocolate Plus rotated 90
// degrees from that, so this is one step away (0 or 2 - whichever reads
// right-side-up once actually mounted; try the other if it's upside down).
inline constexpr uint8_t kDisplayRotation = 0;

}  // namespace config
