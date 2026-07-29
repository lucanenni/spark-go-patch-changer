"use strict";

// Minimal key-based i18n: language auto-detected from the browser, English fallback.
const translations = {
  en: {
    app_title: "Spark GO GUI",
    subtitle: "BLE control panel — Web Bluetooth",
    panel_connection: "BLE connection",
    panel_send_patch: "Send patch",
    label_language: "Language",
    label_name_filter: "Name filter",
    btn_scan: "Scan",
    btn_connect: "Connect",
    btn_disconnect: "Disconnect",
    option_no_device: "— no device selected —",
    log_title: "Log",
    status_ready: "Ready",
    status_not_supported: "Not supported",
    status_selecting_device: "Selecting device...",
    status_error: "Error",
    status_connecting: "Connecting to {name}...",
    status_connected: "Connected",
    status_disconnected: "Disconnected",
    log_web_bluetooth_unavailable: "Web Bluetooth is not available in this browser (use Chrome/Edge on desktop or Android, over HTTPS).",
    log_opening_picker: "Opening Bluetooth device picker...",
    log_selected: "Selected: {name} [{id}]",
    log_selection_cancelled: "Selection cancelled.",
    log_device_selection_error: "Device selection error: {name}: {message}",
    log_connecting: "Connecting to {name}...",
    log_connected: "Connected to {name}",
    log_connection_error: "Connection error: {name}: {message}",
    log_not_connected: "Not connected.",
    log_tx_patch: "TX (patch {n}): {hex}",
    log_rx: "RX: {hex}",
    log_send_patch_failed: "Send patch {n} failed: {name}: {message}",
    log_disconnected: "Disconnected.",
    log_remembered_device: "Remembered device found: {name} — auto-connecting...",
    log_multiple_remembered: "{count} remembered devices found — pick one manually via Scan.",
    log_waiting_for_scan: "Waiting for scan.",
    log_waiting_for_scan_hint: "Waiting for scan. (Auto-reconnect needs a browser that supports navigator.bluetooth.getDevices — use the Scan button.)",
  },
  it: {
    app_title: "Spark GO GUI",
    subtitle: "Pannello di controllo BLE — Web Bluetooth",
    panel_connection: "Connessione BLE",
    panel_send_patch: "Invia patch",
    label_language: "Lingua",
    label_name_filter: "Filtro nome",
    btn_scan: "Scansiona",
    btn_connect: "Connetti",
    btn_disconnect: "Disconnetti",
    option_no_device: "— nessun dispositivo selezionato —",
    log_title: "Log",
    status_ready: "Pronto",
    status_not_supported: "Non supportato",
    status_selecting_device: "Selezione dispositivo...",
    status_error: "Errore",
    status_connecting: "Connessione a {name}...",
    status_connected: "Connesso",
    status_disconnected: "Disconnesso",
    log_web_bluetooth_unavailable: "Web Bluetooth non è disponibile in questo browser (usa Chrome/Edge su desktop o Android, via HTTPS).",
    log_opening_picker: "Apertura selezione dispositivo Bluetooth...",
    log_selected: "Selezionato: {name} [{id}]",
    log_selection_cancelled: "Selezione annullata.",
    log_device_selection_error: "Errore selezione dispositivo: {name}: {message}",
    log_connecting: "Connessione a {name}...",
    log_connected: "Connesso a {name}",
    log_connection_error: "Errore di connessione: {name}: {message}",
    log_not_connected: "Non connesso.",
    log_tx_patch: "TX (patch {n}): {hex}",
    log_rx: "RX: {hex}",
    log_send_patch_failed: "Invio patch {n} fallito: {name}: {message}",
    log_disconnected: "Disconnesso.",
    log_remembered_device: "Dispositivo noto trovato: {name} — connessione automatica...",
    log_multiple_remembered: "{count} dispositivi noti trovati — selezionane uno manualmente con Scansiona.",
    log_waiting_for_scan: "In attesa di scansione.",
    log_waiting_for_scan_hint: "In attesa di scansione. (La riconnessione automatica richiede un browser che supporti navigator.bluetooth.getDevices — usa il pulsante Scansiona.)",
  },
};

function detectLang() {
  const nav = (navigator.language || navigator.userLanguage || "en").toLowerCase();
  return nav.startsWith("it") ? "it" : "en";
}

let LANG = detectLang();

function setLanguage(lang) {
  if (translations[lang]) {
    LANG = lang;
    applyStaticTranslations();
  }
}

function t(key, params) {
  let str = (translations[LANG] && translations[LANG][key]) || translations.en[key] || key;
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      str = str.replace(new RegExp(`\\{${k}\\}`, "g"), v);
    }
  }
  return str;
}

// Elements whose content is driven by app state (e.g. #statusText) are excluded here -
// the app re-renders them itself via refreshDynamicText() on language change.
function applyStaticTranslations() {
  document.documentElement.lang = LANG;
  document.title = t("app_title");
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-value]").forEach((el) => {
    el.value = t(el.dataset.i18nValue);
  });
  document.querySelectorAll("[data-i18n-label]").forEach((el) => {
    el.setAttribute("data-label", t(el.dataset.i18nLabel));
  });
  if (typeof refreshDynamicText === "function") refreshDynamicText();
}
