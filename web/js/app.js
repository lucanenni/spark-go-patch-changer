"use strict";

// ---- UI state ----
const els = {
  statusLed: document.getElementById("statusLed"),
  statusText: document.getElementById("statusText"),
  langSelect: document.getElementById("langSelect"),
  nameFilter: document.getElementById("nameFilter"),
  btnScan: document.getElementById("btnScan"),
  deviceSelect: document.getElementById("deviceSelect"),
  btnConnect: document.getElementById("btnConnect"),
  btnDisconnect: document.getElementById("btnDisconnect"),
  log: document.getElementById("log"),
  btnLogExport: document.getElementById("btnLogExport"),
  btnLogClear: document.getElementById("btnLogClear"),
  patchButtons: Array.from(document.querySelectorAll(".fsw")),
  btnTunerOn: document.getElementById("btnTunerOn"),
  btnTunerOff: document.getElementById("btnTunerOff"),
  tunerNote: document.getElementById("tunerNote"),
  tunerNeedle: document.getElementById("tunerNeedle"),
  tunerRaw: document.getElementById("tunerRaw"),
  chainPresetLabel: document.getElementById("chainPresetLabel"),
  chainRowsContainer: document.getElementById("chainRows"),
  guitarVolume: document.getElementById("guitarVolume"),
  guitarVolumeLabel: document.getElementById("guitarVolumeLabel"),
  btnTapTempo: document.getElementById("btnTapTempo"),
  tapTempoDisplay: document.getElementById("tapTempoDisplay"),
  patchBpmNote: document.getElementById("patchBpmNote"),
  patchNames: [0, 1, 2, 3].map(n => document.getElementById("patchName" + n)),
};

let currentDevice = null;
let gattServer = null;
let writeChar = null;
let notifyChar = null;
let tapTimes = [];
let lastTapBpm = null; // tracked so refreshDynamicText() can re-render it on language change

// ---- Pedal chain panel ----
const chainRows = [];
let lastPreset = null;

SLOT_LABELS.forEach((slotLabel, i) => {
  const row = document.createElement("div");
  row.className = "chain-row";

  const slotEl = document.createElement("div");
  slotEl.textContent = slotLabel;

  const nameEl = document.createElement("div");
  nameEl.textContent = "—";

  const stateEl = document.createElement("div");
  stateEl.className = "chain-state";
  stateEl.textContent = "—";

  const toggleBtn = document.createElement("button");
  toggleBtn.textContent = t("chain_toggle");
  toggleBtn.disabled = true;
  toggleBtn.addEventListener("click", () => toggleChainSlot(i));

  const paramsEl = document.createElement("div");
  paramsEl.className = "chain-params";

  row.append(slotEl, nameEl, stateEl, toggleBtn, paramsEl);
  els.chainRowsContainer.appendChild(row);

  chainRows.push({ nameEl, stateEl, toggleBtn, paramsEl, pedal: null });
});

function renderChainPresetLabel(){
  els.chainPresetLabel.textContent = t("chain_preset_label", {
    name: lastPreset.name || t("chain_unnamed"),
    n: lastPreset.presetNum + 1,
    bpm: lastPreset.bpm.toFixed(0),
  });
}

function updateChainDisplay(preset){
  lastPreset = preset;
  renderChainPresetLabel();
  els.patchBpmNote.textContent = t("patch_bpm_label", { bpm: preset.bpm.toFixed(0) });
  preset.pedals.forEach((pedal, i) => {
    const row = chainRows[i];
    if (!row) return;
    row.pedal = pedal;
    row.nameEl.textContent = pedal.name;
    row.stateEl.textContent = pedal.on ? t("chain_on") : t("chain_off");
    row.stateEl.className = "chain-state " + (pedal.on ? "on" : "off");
    row.toggleBtn.disabled = !writeChar;
    row.paramsEl.textContent = pedal.params.map(p => `P${p.id}=${p.value.toFixed(2)}`).join(" ");
  });
}

function resetChainDisplay(){
  lastPreset = null;
  els.chainPresetLabel.textContent = t("chain_none");
  els.patchBpmNote.textContent = t("patch_bpm_unknown");
  chainRows.forEach(row => {
    row.pedal = null;
    row.nameEl.textContent = "—";
    row.stateEl.textContent = "—";
    row.stateEl.className = "chain-state";
    row.toggleBtn.disabled = true;
    row.paramsEl.textContent = "";
  });
}

function applyEffectState(name, on){
  for (const row of chainRows){
    if (row.pedal && row.pedal.name === name){
      row.pedal.on = on;
      row.stateEl.textContent = on ? t("chain_on") : t("chain_off");
      row.stateEl.className = "chain-state " + (on ? "on" : "off");
    }
  }
}

function applyPatchName(n, name){
  if (els.patchNames[n]) els.patchNames[n].textContent = name || t("chain_unnamed");
}

function resetPatchNames(){
  els.patchNames.forEach(el => { if (el) el.textContent = "—"; });
}

// `purpose` is "chain" (repopulate the pedal-chain panel, the usual case) or "name"
// (just grab this patch's name for its button label, see readAllPatchNames below) -
// every successful read updates the name label regardless of purpose.
async function requestPreset(presetNum, purpose = "chain"){
  if (!writeChar) return;
  try{
    const payload = buildPresetRequestPayload(presetNum);
    // seq was already advanced by buildPresetRequestPayload, so the in-flight value
    // is the one it just used, i.e. one less than the current seq.
    presetSeqInFlight = (seq - 1) & 0xFF;
    presetAccum = [];
    presetPurpose = purpose;
    if (writeChar.properties.writeWithoutResponse){
      await writeChar.writeValueWithoutResponse(payload);
    } else {
      await writeChar.writeValue(payload);
    }
    log(t("log_tx_request_preset", { n: presetNum, hex: fmtHex(payload) }), "l-tx");
  } catch(e){
    log(t("log_request_preset_failed", { n: presetNum, name: e.name, message: e.message }), "l-err");
  }
}

// Like requestPreset, but waits (with a timeout) for that exact read to finish before
// returning - used wherever more than one preset might otherwise be requested back to
// back, since only one can be reassembled at a time (see presetAccum/presetSeqInFlight).
function readPresetAndWait(presetNum, purpose, timeoutMs = 2000){
  return new Promise((resolve) => {
    presetReadResolve = resolve;
    requestPreset(presetNum, purpose);
    setTimeout(() => {
      if (presetReadResolve === resolve){ presetReadResolve = null; resolve(); }
    }, timeoutMs);
  });
}

// Read all 4 saved patches just to grab their names for display under the patch
// buttons. `skip` is the active patch's number, already read in full via
// readPresetAndWait(..., "chain") - no need to read it again.
async function readAllPatchNames(skip){
  for (let n = 0; n < 4; n++){
    if (n === skip) continue;
    await readPresetAndWait(n, "name");
  }
}

async function requestActivePatch(){
  if (!writeChar) return;
  try{
    const payload = buildStateRequestPayload();
    if (writeChar.properties.writeWithoutResponse){
      await writeChar.writeValueWithoutResponse(payload);
    } else {
      await writeChar.writeValue(payload);
    }
    log(t("log_tx_active_patch", { hex: fmtHex(payload) }), "l-tx");
  } catch(e){
    log(t("log_active_patch_failed", { name: e.name, message: e.message }), "l-err");
  }
}

function requestActivePatchAndWait(timeoutMs = 2000){
  return new Promise((resolve) => {
    activePatchResult = null;
    activePatchResolve = () => resolve(activePatchResult);
    requestActivePatch();
    setTimeout(() => {
      if (activePatchResolve){ activePatchResolve = null; resolve(activePatchResult); }
    }, timeoutMs);
  });
}

// Would try to read the current Guitar volume instead of leaving the slider at an
// arbitrary default, but confirmed on real hardware that the Spark GO never responds
// to this (see buildMixerRequestPayload, currently unused) - kept in case that
// changes; see requestMixerValue below and its call site (currently commented out).
let mixerChannelsPending = [];

async function requestMixerValue(channel){
  if (!writeChar) return;
  try{
    const payload = buildMixerRequestPayload(channel);
    mixerChannelsPending.push(channel);
    if (writeChar.properties.writeWithoutResponse){
      await writeChar.writeValueWithoutResponse(payload);
    } else {
      await writeChar.writeValue(payload);
    }
    log(t("log_tx_mixer_request", { channel, hex: fmtHex(payload) }), "l-tx");
  } catch(e){
    log(t("log_mixer_request_failed", { name: e.name, message: e.message }), "l-err");
  }
}

async function toggleChainSlot(i){
  const row = chainRows[i];
  const pedal = row.pedal;
  if (!pedal || !writeChar) return;
  const newOn = !pedal.on;
  try{
    const payload = buildEffectTogglePayload(pedal.name, newOn);
    if (writeChar.properties.writeWithoutResponse){
      await writeChar.writeValueWithoutResponse(payload);
    } else {
      await writeChar.writeValue(payload);
    }
    log(t("log_tx_toggle", { name: pedal.name, hex: fmtHex(payload) }), "l-tx");
    // Apply optimistically as soon as the write succeeds, rather than waiting solely
    // on the device's real-time confirmation (CMD 0x03/SUB_CMD 0x15) - if that
    // notification is slow, dropped, or never applied, pedal.on would otherwise stay
    // stale and every subsequent click would keep recomputing the same (wrong)
    // direction. applyEffectState still runs if/when the live confirmation arrives,
    // correcting this if the command didn't actually take effect. No re-read of the
    // saved preset here either way - toggling doesn't rewrite what's stored for the
    // patch, so that read would just show the pre-toggle value.
    applyEffectState(pedal.name, newOn);
  } catch(e){
    log(t("log_toggle_failed", { name: pedal.name, err: e.name, message: e.message }), "l-err");
  }
}

// ---- BLE notification stream reassembly ----
// GATT notifications don't align to message boundaries - a single logical
// F0 01 ... F7 chunk can span several separate notification packets, so bytes are
// accumulated across calls and split on F7 here (mirrors the desktop app).
let rxStream = new Uint8Array(0);
let presetAccum = [];
let presetSeqInFlight = null;
let presetPurpose = "chain";
let presetReadResolve = null;
let activePatchResolve = null;
let activePatchResult = null;

function handleNotificationBytes(raw){
  rxStream = concatBytes(rxStream, raw);
  while (true){
    const idx = rxStream.indexOf(0xF7);
    if (idx === -1) break;
    const chunk = rxStream.slice(0, idx + 1);
    rxStream = rxStream.slice(idx + 1);
    processChunk(chunk);
  }
}

function processChunk(chunk){
  let start = -1;
  for (let i = 0; i + 1 < chunk.length; i++){
    if (chunk[i] === 0xF0 && chunk[i + 1] === 0x01){ start = i; break; }
  }
  if (start === -1 || chunk.length - start < 7) return;
  chunk = chunk.slice(start);
  const seqByte = chunk[2], cmd = chunk[4], subCmd = chunk[5];
  let data8;
  try{
    data8 = unpack7bit(chunk.slice(6, chunk.length - 1));
  } catch(e){ return; }
  // CMD 0x03 (and, per the source library this was ported from, also 0x01) with
  // SUB_CMD 0x01 is a multi-chunk preset dump: data8[0]=num_chunks, data8[1]=this
  // chunk's index, data8[2]=chunk_len, data8[3:]=this chunk's slice of the payload.
  if ((cmd === 0x01 || cmd === 0x03) && subCmd === 0x01 && data8.length >= 3){
    if (seqByte !== presetSeqInFlight){
      // Belongs to a request we're no longer waiting on (a stale/aborted read, or
      // one superseded by a newer one) - accumulating it anyway would corrupt the
      // current reassembly with a foreign response.
      return;
    }
    const numChunks = data8[0], thisChunk = data8[1];
    presetAccum.push(...data8.slice(3));
    if (thisChunk >= numChunks - 1){
      const full = new Uint8Array(presetAccum);
      presetAccum = [];
      presetSeqInFlight = null;
      const purpose = presetPurpose;
      try{
        const parsed = parsePresetData(full);
        // Every successful read updates that patch's name label, regardless of why
        // it was requested; only a "chain" read (the active patch, or after a
        // manual patch change) also repopulates the full pedal-chain panel.
        applyPatchName(parsed.presetNum, parsed.name);
        if (purpose === "chain") updateChainDisplay(parsed);
      } catch(e){
        log(t("log_preset_parse_failed", { message: e.message }), "l-err");
      } finally {
        if (presetReadResolve){ presetReadResolve(); presetReadResolve = null; }
      }
    }
  // CMD 0x03/SUB_CMD 0x15 (single message, not multi-chunk) is the device confirming
  // an effect's new live on/off state.
  } else if (cmd === 0x03 && subCmd === 0x15 && data8.length >= 2){
    try{
      const { name, on } = parseEffectStateNotification(data8);
      applyEffectState(name, on);
    } catch(e){ /* ignore malformed notification */ }
  // CMD 0x03/SUB_CMD 0x10 is the response to buildStateRequestPayload: which patch
  // is truly active right now.
  } else if (cmd === 0x03 && subCmd === 0x10 && data8.length >= 2){
    try{
      activePatchResult = parseActivePatchNotification(data8);
    } catch(e){
      activePatchResult = null;
    }
    if (activePatchResolve){ activePatchResolve(); activePatchResolve = null; }
  // CMD 0x03/SUB_CMD 0x33 with just a bare float (5 bytes: 0xCA + 4) would be a
  // response to requestMixerValue's CMD 0x02/SUB_CMD 0x33 - confirmed on real
  // hardware that the Spark GO never actually sends this (see
  // buildMixerRequestPayload, currently unused). Kept here in case that changes; no
  // channel byte in the response, so match it against whichever channel was asked
  // about first (FIFO, same assumption as a single BLE link delivering notifications
  // in request order).
  } else if (cmd === 0x03 && subCmd === 0x33 && data8.length === 5 && mixerChannelsPending.length){
    const channel = mixerChannelsPending.shift();
    try{
      applyMixerValue(channel, parseMixerValueResponse(data8));
    } catch(e){ /* ignore malformed notification */ }
  // CMD 0x01 or 0x03/SUB_CMD 0x33 with channel+value (6 bytes) is the confirmed
  // mixer-change shape (see buildMixerPayload in protocol.js and PROTOCOL.md) -
  // either our own optimistic echo or the amp reporting a physical button/encoder
  // change unsolicited.
  } else if ((cmd === 0x01 || cmd === 0x03) && subCmd === 0x33 && data8.length === 6){
    try{
      const { channel, value } = parseMixerNotification(data8);
      applyMixerValue(channel, value);
    } catch(e){ /* ignore malformed notification */ }
  }
}

function log(text, cls){
  const line = document.createElement("div");
  if (cls) line.className = cls;
  line.textContent = text;
  els.log.appendChild(line);
  els.log.scrollTop = els.log.scrollHeight;
}

els.btnLogClear.addEventListener("click", () => {
  els.log.innerHTML = "";
});

els.btnLogExport.addEventListener("click", () => {
  const blob = new Blob([els.log.innerText], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "spark_go_log.txt";
  a.click();
  URL.revokeObjectURL(url);
});

// Tracked so a language switch can re-render the current status without
// guessing - see refreshDynamicText(), called from i18n.js's setLanguage().
let currentStatus = { key: "status_ready", params: null, mode: null };

function setStatus(key, params, mode){
  currentStatus = { key, params, mode };
  els.statusText.textContent = t(key, params);
  els.statusLed.className = "led" + (mode ? " " + mode : "");
}

function refreshDynamicText(){
  els.statusText.textContent = t(currentStatus.key, currentStatus.params);
  if (lastPreset){
    renderChainPresetLabel();
    els.patchBpmNote.textContent = t("patch_bpm_label", { bpm: lastPreset.bpm.toFixed(0) });
  } else {
    els.chainPresetLabel.textContent = t("chain_none");
    els.patchBpmNote.textContent = t("patch_bpm_unknown");
  }
  chainRows.forEach(row => {
    row.toggleBtn.textContent = t("chain_toggle");
    if (row.pedal) row.stateEl.textContent = row.pedal.on ? t("chain_on") : t("chain_off");
  });
  if (lastTapBpm !== null) els.tapTempoDisplay.textContent = t("tap_tempo_bpm", { bpm: lastTapBpm.toFixed(1) });
  else if (tapTimes.length === 1) els.tapTempoDisplay.textContent = t("tap_tempo_waiting");
  else els.tapTempoDisplay.textContent = t("tap_tempo_none");
}

// ---- Language selector ----
els.langSelect.value = LANG;
els.langSelect.addEventListener("change", () => {
  setLanguage(els.langSelect.value);
});

// Initial render - now that els/currentStatus/refreshDynamicText all exist.
applyStaticTranslations();

function setConnectedUi(connected){
  els.btnConnect.disabled = connected || !els.deviceSelect.value;
  els.btnDisconnect.disabled = !connected;
  els.patchButtons.forEach(b => b.disabled = !connected);
  els.btnTunerOn.disabled = !connected;
  els.btnTunerOff.disabled = !connected;
  els.guitarVolume.disabled = !connected;
  els.btnTapTempo.disabled = !connected;
  chainRows.forEach(row => { row.toggleBtn.disabled = !connected || !row.pedal; });
  if (!connected){
    resetTunerDisplay();
    resetChainDisplay();
    resetMixerDisplay();
    resetPatchNames();
  }
}

// ---- Guitar volume and tap tempo - both CONFIRMED on real hardware, see PROTOCOL.md.
// Music Volume was removed: its physical buttons turned out to be standard AVRCP
// volume commands sent to the Bluetooth audio source (the phone), not anything
// going through the Spark GO's own control protocol at all.
async function setMixerVolume(channel, value){
  if (!writeChar) return;
  try{
    const payload = buildMixerPayload(channel, value);
    if (writeChar.properties.writeWithoutResponse){
      await writeChar.writeValueWithoutResponse(payload);
    } else {
      await writeChar.writeValue(payload);
    }
    log(t("log_tx_mixer", { channel, hex: fmtHex(payload) }), "l-tx");
  } catch(e){
    log(t("log_mixer_failed", { name: e.name, message: e.message }), "l-err");
  }
}

function applyMixerValue(channel, value){
  if (channel === MIXER_CHANNEL_GUITAR){
    els.guitarVolume.value = value;
    els.guitarVolumeLabel.textContent = Math.round(value * 100) + "%";
  }
}

function resetMixerDisplay(){
  els.guitarVolume.value = 0.5;
  els.guitarVolumeLabel.textContent = "50%";
  mixerChannelsPending = [];
  tapTimes = [];
  lastTapBpm = null;
  els.tapTempoDisplay.textContent = t("tap_tempo_none");
}

els.guitarVolume.addEventListener("input", () => {
  els.guitarVolumeLabel.textContent = Math.round(els.guitarVolume.value * 100) + "%";
});
els.guitarVolume.addEventListener("change", () => {
  setMixerVolume(MIXER_CHANNEL_GUITAR, parseFloat(els.guitarVolume.value));
});

const TAP_TEMPO_RESET_GAP_MS = 2000;
const TAP_TEMPO_MAX_SAMPLES = 4;
const TAP_TEMPO_MIN_BPM = 30;
const TAP_TEMPO_MAX_BPM = 300;

els.btnTapTempo.addEventListener("click", async () => {
  const now = performance.now();
  if (tapTimes.length && now - tapTimes[tapTimes.length - 1] > TAP_TEMPO_RESET_GAP_MS){
    tapTimes = [];
    lastTapBpm = null;
  }
  tapTimes.push(now);
  tapTimes = tapTimes.slice(-TAP_TEMPO_MAX_SAMPLES);
  if (tapTimes.length < 2){
    els.tapTempoDisplay.textContent = t("tap_tempo_waiting");
    return;
  }
  const intervals = [];
  for (let i = 1; i < tapTimes.length; i++) intervals.push(tapTimes[i] - tapTimes[i - 1]);
  const avgMs = intervals.reduce((a, b) => a + b, 0) / intervals.length;
  const bpm = Math.max(TAP_TEMPO_MIN_BPM, Math.min(TAP_TEMPO_MAX_BPM, 60000 / avgMs));
  lastTapBpm = bpm;
  els.tapTempoDisplay.textContent = t("tap_tempo_bpm", { bpm: bpm.toFixed(1) });

  if (!writeChar) return;
  try{
    const payload = buildTapTempoPayload(bpm);
    if (writeChar.properties.writeWithoutResponse){
      await writeChar.writeValueWithoutResponse(payload);
    } else {
      await writeChar.writeValue(payload);
    }
    log(t("log_tx_tap_tempo", { bpm: bpm.toFixed(1), hex: fmtHex(payload) }), "l-tx");
  } catch(e){
    log(t("log_tap_tempo_failed", { name: e.name, message: e.message }), "l-err");
  }
});

// ---- Tuner display ----
function resetTunerDisplay(){
  els.tunerNote.textContent = "—";
  els.tunerNote.classList.add("idle");
  els.tunerNeedle.style.left = "50%";
  els.tunerNeedle.classList.remove("centered");
  els.tunerRaw.textContent = t("tuner_no_signal");
}

function updateTunerDisplay(bytes){
  const parsed = parseTunerFrame(bytes);
  if (!parsed) return; // Not a tuner data frame (e.g. an ack for some other command).
  if (parsed.idle){
    resetTunerDisplay();
    return;
  }
  els.tunerNote.textContent = parsed.noteName;
  els.tunerNote.classList.remove("idle");
  const clampedCents = Math.max(-50, Math.min(50, parsed.cents));
  const leftPct = 50 + (clampedCents / 50) * 50;
  els.tunerNeedle.style.left = leftPct.toFixed(1) + "%";
  els.tunerNeedle.classList.toggle("centered", Math.abs(clampedCents) <= 5);
  els.tunerRaw.textContent = t("tuner_raw", {
    sign: parsed.cents >= 0 ? "+" : "",
    cents: parsed.cents.toFixed(0),
    counter: parsed.counter,
  });
}

// ---- Scan ----
els.btnScan.addEventListener("click", async () => {
  if (!navigator.bluetooth){
    log(t("log_web_bluetooth_unavailable"), "l-err");
    setStatus("status_not_supported", null, "err");
    return;
  }
  const namePrefix = els.nameFilter.value.trim();

  try{
    setStatus("status_selecting_device", null, "busy");
    log(t("log_opening_picker"), "l-info");

    const filters = namePrefix ? [{ namePrefix }] : undefined;
    const device = await navigator.bluetooth.requestDevice(filters
      ? { filters, optionalServices: [SERVICE_UUID] }
      : { acceptAllDevices: true, optionalServices: [SERVICE_UUID] }
    );

    currentDevice = device;
    els.deviceSelect.innerHTML = "";
    const opt = document.createElement("option");
    opt.value = device.id;
    opt.textContent = device.name || "(unnamed)";
    els.deviceSelect.appendChild(opt);
    els.deviceSelect.disabled = false;
    els.deviceSelect.value = device.id;
    els.btnConnect.disabled = false;

    log(t("log_selected", { name: device.name || "(unnamed)", id: device.id }), "l-info");
    setStatus("status_ready", null, null);
  } catch(e){
    if (e.name === "NotFoundError"){
      log(t("log_selection_cancelled"), "l-info");
      setStatus("status_ready", null, null);
    } else {
      log(t("log_device_selection_error", { name: e.name, message: e.message }), "l-err");
      setStatus("status_error", null, "err");
    }
  }
});

// ---- Connect ----
async function connectToDevice(device){
  try{
    setStatus("status_connecting", { name: device.name }, "busy");
    log(t("log_connecting", { name: device.name }), "l-info");

    device.addEventListener("gattserverdisconnected", onDisconnected);
    gattServer = await device.gatt.connect();

    const service = await gattServer.getPrimaryService(SERVICE_UUID);
    writeChar = await service.getCharacteristic(WRITE_CHAR_UUID);
    notifyChar = await service.getCharacteristic(NOTIFY_CHAR_UUID);

    rxStream = new Uint8Array(0);
    presetAccum = [];
    presetSeqInFlight = null;
    mixerChannelsPending = [];
    await notifyChar.startNotifications();
    notifyChar.addEventListener("characteristicvaluechanged", (ev) => {
      const raw = new Uint8Array(ev.target.value.buffer);
      log(t("log_rx", { hex: fmtHex(raw) }), "l-rx");
      updateTunerDisplay(raw);
      handleNotificationBytes(raw);
    });

    log(t("log_connected", { name: device.name }), "l-info");
    setStatus("status_connected", null, "on");
    setConnectedUi(true);
    // Find out which patch is really active (CMD 0x02/SUB_CMD 0x10) instead of
    // guessing/defaulting, then read its full chain and the other 3 patches' names
    // (shown under the patch buttons). A short pause first lets the BLE notification
    // subscription fully settle.
    setTimeout(() => {
      (async () => {
        const activeNum = await requestActivePatchAndWait();
        if (activeNum !== null) await readPresetAndWait(activeNum, "chain");
        await readAllPatchNames(activeNum);
      })();
    }, 300);
    // Reading the current Guitar volume on connect (CMD 0x02/SUB_CMD 0x33) is
    // disabled for now - confirmed on real hardware to never get a response
    // (TX-only, no RX ever, for both mixer channels). Left here commented out rather
    // than deleted in case a future sniff of the official app finds the real request
    // shape; requestMixerValue/parseMixerValueResponse are still defined and ready to
    // use. The Guitar slider instead picks up the live value passively, the moment
    // the physical rotary encoder is turned (the amp does broadcast that unsolicited
    // - see PROTOCOL.md).
    // setTimeout(() => requestMixerValue(MIXER_CHANNEL_GUITAR), 300);
  } catch(e){
    log(t("log_connection_error", { name: e.name, message: e.message }), "l-err");
    setStatus("status_error", null, "err");
    setConnectedUi(false);
  }
}

els.btnConnect.addEventListener("click", () => {
  if (!currentDevice) return;
  connectToDevice(currentDevice);
});

// ---- Disconnect ----
els.btnDisconnect.addEventListener("click", () => {
  if (currentDevice && currentDevice.gatt.connected){
    currentDevice.gatt.disconnect();
  }
});

function onDisconnected(){
  writeChar = null;
  notifyChar = null;
  log(t("log_disconnected"), "l-info");
  setStatus("status_disconnected", null, null);
  setConnectedUi(false);
}

// ---- Send patch ----
els.patchButtons.forEach(btn => {
  btn.addEventListener("click", async () => {
    const n = parseInt(btn.dataset.patch, 10);
    if (!writeChar){
      log(t("log_not_connected"), "l-err");
      return;
    }
    try{
      const payload = buildPatchPayload(n);
      if (writeChar.properties.writeWithoutResponse){
        await writeChar.writeValueWithoutResponse(payload);
      } else {
        await writeChar.writeValue(payload);
      }
      log(t("log_tx_patch", { n, hex: fmtHex(payload) }), "l-tx");
      btn.classList.add("flash");
      setTimeout(() => btn.classList.remove("flash"), 180);
      // The patch-change command doesn't itself confirm the switch happened, and
      // requesting the read too soon can race with the device still applying it
      // (returning the previous patch's data). A short settle pause first, then an
      // accurate read of that exact patch - unlike the unreliable "which patch is
      // active" guess connectToDevice() deliberately doesn't make.
      setTimeout(() => requestPreset(n - 1), 300);
    } catch(e){
      log(t("log_send_patch_failed", { n, name: e.name, message: e.message }), "l-err");
    }
  });
});

// ---- Tuner ON/OFF ----
els.btnTunerOn.addEventListener("click", async () => {
  if (!writeChar){
    log(t("log_not_connected"), "l-err");
    return;
  }
  try{
    const payload = buildTunerStartPayload();
    if (writeChar.properties.writeWithoutResponse){
      await writeChar.writeValueWithoutResponse(payload);
    } else {
      await writeChar.writeValue(payload);
    }
    log(t("log_tx_tuner_on", { hex: fmtHex(payload) }), "l-tx");
  } catch(e){
    log(t("log_tuner_on_failed", { name: e.name, message: e.message }), "l-err");
  }
});

els.btnTunerOff.addEventListener("click", async () => {
  if (!writeChar){
    log(t("log_not_connected"), "l-err");
    return;
  }
  try{
    const payload = buildTunerStopPayload();
    if (writeChar.properties.writeWithoutResponse){
      await writeChar.writeValueWithoutResponse(payload);
    } else {
      await writeChar.writeValue(payload);
    }
    log(t("log_tx_tuner_off", { hex: fmtHex(payload) }), "l-tx");
    resetTunerDisplay();
  } catch(e){
    log(t("log_tuner_off_failed", { name: e.name, message: e.message }), "l-err");
  }
});

setConnectedUi(false);

// ---- Auto-reconnect on load ----
// Web Bluetooth can never auto-open the device picker (navigator.bluetooth.requestDevice
// always requires a fresh user gesture, by design - no way around that). But if the user
// has already granted access to a device at least once before (via Scan), Chrome remembers
// it and navigator.bluetooth.getDevices() can return it without a new prompt, letting us
// reconnect automatically. Support for getDevices() varies by browser/version.
(async () => {
  if (!navigator.bluetooth || !navigator.bluetooth.getDevices){
    log(t("log_waiting_for_scan_hint"), "l-info");
    return;
  }
  try{
    const known = await navigator.bluetooth.getDevices();
    if (known.length === 1){
      const device = known[0];
      currentDevice = device;
      els.deviceSelect.innerHTML = "";
      const opt = document.createElement("option");
      opt.value = device.id;
      opt.textContent = device.name || "(unnamed)";
      els.deviceSelect.appendChild(opt);
      els.deviceSelect.disabled = false;
      els.deviceSelect.value = device.id;
      els.btnConnect.disabled = false;
      log(t("log_remembered_device", { name: device.name || "(unnamed)" }), "l-info");
      await connectToDevice(device);
    } else if (known.length > 1){
      log(t("log_multiple_remembered", { count: known.length }), "l-info");
    } else {
      log(t("log_waiting_for_scan"), "l-info");
    }
  } catch(e){
    log(t("log_waiting_for_scan"), "l-info");
  }
})();
