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
  patchButtons: Array.from(document.querySelectorAll(".fsw")),
};

let currentDevice = null;
let gattServer = null;
let writeChar = null;
let notifyChar = null;

function log(text, cls){
  const line = document.createElement("div");
  if (cls) line.className = cls;
  line.textContent = text;
  els.log.appendChild(line);
  els.log.scrollTop = els.log.scrollHeight;
}

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

    await notifyChar.startNotifications();
    notifyChar.addEventListener("characteristicvaluechanged", (ev) => {
      const raw = new Uint8Array(ev.target.value.buffer);
      log(t("log_rx", { hex: fmtHex(raw) }), "l-rx");
    });

    log(t("log_connected", { name: device.name }), "l-info");
    setStatus("status_connected", null, "on");
    setConnectedUi(true);
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
    } catch(e){
      log(t("log_send_patch_failed", { n, name: e.name, message: e.message }), "l-err");
    }
  });
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
