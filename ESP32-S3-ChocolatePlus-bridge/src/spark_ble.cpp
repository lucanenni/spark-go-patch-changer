// Written against NimBLE-Arduino ~1.4.x's API (pinned in platformio.ini).
// Confirmed working end-to-end on real hardware against a Spark GO: connect,
// patch change + confirmation + resulting preset read (multi-chunk
// reassembly), active-patch query, tuner start/stop + data frames. Two
// non-obvious things it took real-hardware testing to find, see the two
// comments below where they're handled:
// - subscribe()'s CCCD write must be write-WITH-response (the `response`
//   param) - write-without-response reported success but the Spark GO never
//   actually started sending notifications (rawNotificationCount() stuck at
//   0 forever despite cccdFound()/lastSubscribeOk() both true).
// - a patch-change command is sometimes acked with the generic CMD 0x04
//   ack (no payload) instead of the richer CMD 0x03 confirmation
//   PROTOCOL.md documents (which carries the new patch number) - handle
//   both, since which one arrives isn't consistent.

#include "spark_ble.h"

#include <NimBLEDevice.h>

#include <algorithm>
#include <cstddef>
#include <vector>

#include "config.h"

namespace spark_ble {

namespace {

const NimBLEUUID kServiceUuid("0000ffc0-0000-1000-8000-00805f9b34fb");
const NimBLEUUID kWriteCharUuid("0000ffc1-0000-1000-8000-00805f9b34fb");
const NimBLEUUID kNotifyCharUuid("0000ffc2-0000-1000-8000-00805f9b34fb");

ConnectionState g_state = ConnectionState::kDisconnected;
NimBLEClient* g_client = nullptr;
NimBLERemoteCharacteristic* g_writeChar = nullptr;
spark_protocol::SeqCounter g_seq;

uint32_t g_lastAttemptMs = 0;
uint32_t g_rawNotificationCount = 0;
bool g_lastSubscribeOk = false;
bool g_cccdFound = false;
// The patch number (0-based) most recently requested via sendPatch(), so a
// *generic* ack (CMD 0x04/SUB_CMD 0x38, no payload) can still be resolved to
// "which patch is now active" - confirmed on real hardware that the Spark GO
// sometimes acks a patch change this way instead of the richer CMD 0x03
// confirmation PROTOCOL.md documents (which does carry the new patch number
// itself). -1 if no patch change is currently outstanding.
int g_pendingPatchNumber0Based = -1;
bool g_forceReconnectRequested = false;

ConnectionStateCallback g_onConnectionState;
PatchConfirmedCallback g_onPatchConfirmed;
PresetCallback g_onPreset;
EffectStateCallback g_onEffectState;
TunerFrameCallback g_onTunerFrame;

// BLE notifications don't align to message boundaries - a logical
// F0 01 ... F7 chunk can span several separate notification packets, so raw
// bytes are accumulated here and split on F7, mirroring
// BleBackend._handle_notification_bytes in the Python reference.
std::vector<uint8_t> g_rxStream;

// Multi-chunk preset-read reassembly state (CMD 0x01/0x03, SUB_CMD 0x01).
std::vector<uint8_t> g_presetAccum;
int g_presetSeqInFlight = -1;

void setState(ConnectionState newState) {
  if (g_state == newState) return;
  g_state = newState;
  if (g_onConnectionState) g_onConnectionState(newState);
}

bool writeRaw(const spark_protocol::Bytes& payload) {
  if (g_state != ConnectionState::kConnected || !g_writeChar) return false;
  return g_writeChar->writeValue(payload.data(), payload.size(), false);
}

// Called whenever we learn which patch is active - either the device's own
// confirmation after a patch-change command (CMD 0x03/SUB_CMD 0x38) or the
// answer to an explicit "which patch is active" query (SUB_CMD 0x10). Both
// cases end the same way in the reference client: notify the caller, then
// (after a short settle pause, since the switch may not have finished
// applying yet) read that patch's chain so effect toggles have fresh names
// to work with.
//
// Note: this runs inside the NimBLE notification callback (the NimBLE host
// task, not the Arduino loop() task), so the delay() below briefly blocks
// that task rather than the whole firmware. 300ms is short and matches the
// reference client's own settle pause, but if real-hardware testing shows
// missed/delayed notifications right after a patch change, replace this
// with a non-blocking timer armed here and polled from spark_ble::loop().
void handleActivePatchKnown(uint8_t patch0Based) {
  if (g_onPatchConfirmed) g_onPatchConfirmed(patch0Based);
  delay(config::kPostPatchSettleMs);
  requestPreset(patch0Based);
}

void processChunk(const spark_protocol::Bytes& chunk) {
  // Find the F0 01 frame start within the chunk (mirrors the reference's
  // chunk.find(b"\xF0\x01") - in practice it's always at offset 0 once
  // split on F7, but this stays defensive against leading garbage).
  constexpr size_t kNotFound = static_cast<size_t>(-1);
  size_t start = kNotFound;
  for (size_t i = 0; i + 1 < chunk.size(); ++i) {
    if (chunk[i] == 0xF0 && chunk[i + 1] == 0x01) {
      start = i;
      break;
    }
  }
  if (start == kNotFound || chunk.size() - start < 7) return;

  spark_protocol::Bytes frame(chunk.begin() + start, chunk.end());
  uint8_t seq = frame[2];
  uint8_t cmd = frame[4];
  uint8_t subCmd = frame[5];
  spark_protocol::Bytes packed(frame.begin() + 6, frame.end() - 1);  // drop trailing F7
  spark_protocol::Bytes data8 = spark_protocol::unpack7Bit(packed);

  if ((cmd == 0x01 || cmd == 0x03) && subCmd == 0x01 && data8.size() >= 3) {
    if (static_cast<int>(seq) != g_presetSeqInFlight) {
      // Belongs to a request we're no longer waiting on - accumulating it
      // anyway would corrupt the current reassembly.
      return;
    }
    uint8_t numChunks = data8[0];
    uint8_t thisChunk = data8[1];
    g_presetAccum.insert(g_presetAccum.end(), data8.begin() + 3, data8.end());
    if (thisChunk >= numChunks - 1) {
      spark_protocol::PresetData preset;
      if (spark_protocol::parsePresetData(g_presetAccum, preset) && g_onPreset) {
        g_onPreset(preset);
      }
      g_presetAccum.clear();
      g_presetSeqInFlight = -1;
    }
  } else if (cmd == 0x03 && subCmd == 0x38 && data8.size() >= 2) {
    // Patch-change confirmation: [1 byte unknown][1 byte: new preset number].
    g_pendingPatchNumber0Based = -1;
    handleActivePatchKnown(data8[1]);
  } else if (cmd == 0x04 && subCmd == 0x38) {
    // Generic ack for a patch-change command - no payload, so the new patch
    // number isn't in this message at all. Use what we ourselves asked for
    // (see sendPatch()) instead of the device's echo.
    if (g_pendingPatchNumber0Based >= 0) {
      uint8_t patch0Based = static_cast<uint8_t>(g_pendingPatchNumber0Based);
      g_pendingPatchNumber0Based = -1;
      handleActivePatchKnown(patch0Based);
    }
  } else if (cmd == 0x03 && subCmd == 0x15 && data8.size() >= 2) {
    spark_protocol::EffectStateEvent event;
    if (spark_protocol::parseEffectStateEvent(data8, event) && g_onEffectState) {
      g_onEffectState(event);
    }
  } else if (cmd == 0x03 && subCmd == 0x10 && data8.size() >= 2) {
    uint8_t patch0Based;
    if (spark_protocol::parseActivePatchEvent(data8, patch0Based)) {
      handleActivePatchKnown(patch0Based);
    }
  }
}

void handleNotificationBytes(const uint8_t* data, size_t length) {
  g_rxStream.insert(g_rxStream.end(), data, data + length);

  // Tuner data frames are sent as raw (non-7bit-packed) 14-byte messages, so
  // try that parse first on each freshly-completed F7-terminated chunk
  // before falling through to the packed-message path above.
  while (true) {
    auto it = std::find(g_rxStream.begin(), g_rxStream.end(), 0xF7);
    if (it == g_rxStream.end()) break;
    spark_protocol::Bytes chunk(g_rxStream.begin(), it + 1);
    g_rxStream.erase(g_rxStream.begin(), it + 1);

    spark_protocol::TunerFrame tunerFrame;
    if (spark_protocol::parseTunerFrame(chunk, tunerFrame)) {
      if (g_onTunerFrame) g_onTunerFrame(tunerFrame);
      continue;
    }
    processChunk(chunk);
  }
}

void notifyCallback(NimBLERemoteCharacteristic* /*pChar*/, uint8_t* pData, size_t length,
                     bool /*isNotify*/) {
  ++g_rawNotificationCount;
  // Harmless to always compile in: goes out over Serial (UART pins unless a
  // build has CDC enabled, e.g. the bletest env - see platformio.ini), never
  // blocks anything. Having the actual raw bytes of every notification is
  // what actually let a real bug get diagnosed here, as opposed to counters
  // alone.
  Serial.printf("[BLE RX %u] ", (unsigned)length);
  for (size_t i = 0; i < length; ++i) Serial.printf("%02X ", pData[i]);
  Serial.println();
  handleNotificationBytes(pData, length);
}

class ClientCallbacks : public NimBLEClientCallbacks {
  void onDisconnect(NimBLEClient* /*pClient*/) override {
    g_writeChar = nullptr;
    g_rxStream.clear();
    g_presetAccum.clear();
    g_presetSeqInFlight = -1;
    setState(ConnectionState::kDisconnected);
  }
};

ClientCallbacks g_clientCallbacks;

// Blocking scan + connect attempt. Returns true on success. Kept as a single
// synchronous step (rather than a fully async state machine) since it only
// runs at startup and on rare reconnects - see the header's documented
// limitation about USB-MIDI not being serviced meanwhile.
bool attemptConnect() {
  setState(ConnectionState::kScanning);

  NimBLEScan* pScan = NimBLEDevice::getScan();
  pScan->setActiveScan(true);
  // NimBLEScanResults::getDevice(i) returns by value, so the match is copied
  // out as an address rather than kept as a pointer into the (soon to go out
  // of scope) results object.
  NimBLEScanResults results = pScan->start(config::kBleScanTimeoutMs / 1000, false);

  bool found = false;
  NimBLEAddress targetAddress;
  for (int i = 0; i < results.getCount(); ++i) {
    NimBLEAdvertisedDevice device = results.getDevice(i);
    if (device.haveName()) {
      String name = device.getName().c_str();
      if (name.indexOf(config::kSparkNameFilter) >= 0) {
        targetAddress = device.getAddress();
        found = true;
        break;
      }
    }
  }

  if (!found) {
    setState(ConnectionState::kDisconnected);
    return false;
  }

  setState(ConnectionState::kConnecting);

  if (!g_client) {
    g_client = NimBLEDevice::createClient();
    g_client->setClientCallbacks(&g_clientCallbacks, false);
  }
  g_client->setConnectTimeout(config::kBleConnectTimeoutMs / 1000);

  if (!g_client->connect(targetAddress)) {
    setState(ConnectionState::kDisconnected);
    return false;
  }

  NimBLERemoteService* service = g_client->getService(kServiceUuid);
  if (!service) {
    g_client->disconnect();
    setState(ConnectionState::kDisconnected);
    return false;
  }

  g_writeChar = service->getCharacteristic(kWriteCharUuid);
  NimBLERemoteCharacteristic* notifyChar = service->getCharacteristic(kNotifyCharUuid);

  if (!g_writeChar || !notifyChar || !notifyChar->canNotify()) {
    g_client->disconnect();
    setState(ConnectionState::kDisconnected);
    return false;
  }

  g_rxStream.clear();
  g_presetAccum.clear();
  g_presetSeqInFlight = -1;

  // NimBLERemoteCharacteristic::subscribe() silently reports success even
  // when it can't find the CCCD (0x2902) descriptor to actually write - it
  // just sets the local callback and returns true, without ever telling the
  // peripheral to start sending notifications (confirmed by reading this
  // exact NimBLE-Arduino version's source: setNotify() returns true on "CCCD
  // not found" as well as on a real successful write). Forcing a fresh
  // descriptor discovery first (getDescriptors(true)) did NOT fix
  // rawNotificationCount() staying at 0 on real hardware even with
  // subscribe() reporting true - so checking for the CCCD explicitly here,
  // separately from subscribe()'s own ambiguous return value, to find out
  // whether it's genuinely present or not.
  notifyChar->getDescriptors(true);
  NimBLERemoteDescriptor* cccd = notifyChar->getDescriptor(NimBLEUUID((uint16_t)0x2902));
  g_cccdFound = (cccd != nullptr);
  // sub:Y and cccd:Y confirmed on real hardware (CCCD found, write reported
  // success) yet rawNotificationCount() still stayed at 0 - trying a
  // write-WITH-response for the CCCD (default is write-without-response) in
  // case the peripheral silently drops the unacknowledged write.
  g_lastSubscribeOk = notifyChar->subscribe(true, notifyCallback, true /* response */);

  g_seq = spark_protocol::SeqCounter();
  setState(ConnectionState::kConnected);

  delay(config::kPostConnectSettleMs);
  requestActivePatch();
  return true;
}

}  // namespace

void begin() { NimBLEDevice::init(""); }

void loop() {
  if (g_state == ConnectionState::kConnected && !g_forceReconnectRequested) return;

  uint32_t now = millis();
  if (g_state == ConnectionState::kConnected && g_forceReconnectRequested) {
    g_forceReconnectRequested = false;
    if (g_client) g_client->disconnect();
    return;  // onDisconnect() callback will move state to kDisconnected
  }

  if (now - g_lastAttemptMs < config::kReconnectRetryIntervalMs) return;
  g_lastAttemptMs = now;
  attemptConnect();
}

bool isConnected() { return g_state == ConnectionState::kConnected; }
ConnectionState state() { return g_state; }

uint32_t rawNotificationCount() { return g_rawNotificationCount; }
bool lastSubscribeOk() { return g_lastSubscribeOk; }
bool cccdFound() { return g_cccdFound; }

bool sendPatch(uint8_t patchNumber1Based) {
  spark_protocol::Bytes payload = spark_protocol::buildPatchPayload(patchNumber1Based, g_seq.consume());
  if (payload.empty()) return false;
  g_pendingPatchNumber0Based = patchNumber1Based - 1;
  return writeRaw(payload);
}

bool tunerStart() {
  return writeRaw(spark_protocol::buildTunerStartPayload(g_seq.consume()));
}

bool tunerStop() {
  return writeRaw(spark_protocol::buildTunerStopPayload(g_seq.consume()));
}

bool toggleEffect(const String& internalName, bool on) {
  return writeRaw(spark_protocol::buildEffectTogglePayload(internalName, on, g_seq.consume()));
}

bool requestPreset(uint8_t presetNum0Based) {
  uint8_t seq = g_seq.consume();
  g_presetSeqInFlight = seq;
  g_presetAccum.clear();
  return writeRaw(spark_protocol::buildPresetRequestPayload(presetNum0Based, seq));
}

bool requestActivePatch() {
  return writeRaw(spark_protocol::buildActivePatchRequestPayload(g_seq.consume()));
}

bool setGuitarVolume(float value) {
  return writeRaw(spark_protocol::buildMixerPayload(spark_protocol::kMixerChannelGuitar, value,
                                                      g_seq.consume()));
}

bool tapTempo(float bpm) {
  return writeRaw(spark_protocol::buildTapTempoPayload(bpm, g_seq.consume()));
}

void forceReconnect() { g_forceReconnectRequested = true; }

void onConnectionStateChanged(ConnectionStateCallback cb) { g_onConnectionState = std::move(cb); }
void onPatchConfirmed(PatchConfirmedCallback cb) { g_onPatchConfirmed = std::move(cb); }
void onPreset(PresetCallback cb) { g_onPreset = std::move(cb); }
void onEffectState(EffectStateCallback cb) { g_onEffectState = std::move(cb); }
void onTunerFrame(TunerFrameCallback cb) { g_onTunerFrame = std::move(cb); }

}  // namespace spark_ble
