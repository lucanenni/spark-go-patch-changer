"use strict";

// Minimal key-based i18n: language auto-detected from the browser, English fallback.
const translations = {
  en: {
    app_title: "Spark GO GUI",
    subtitle: "BLE control panel — Web Bluetooth",
    panel_connection: "BLE connection",
    panel_send_patch: "Send patch",
    panel_tuner: "Tuner",
    panel_tuner_display: "Tuner display (raw, uncalibrated)",
    btn_tuner_on: "Tuner ON",
    btn_tuner_off: "Tuner OFF",
    tuner_no_signal: "no signal",
    tuner_raw: "~{sign}{cents} cents (raw {counter}, provisional scale)",
    log_tx_tuner_on: "TX (tuner ON): {hex}",
    log_tx_tuner_off: "TX (tuner OFF): {hex}",
    log_tuner_on_failed: "Tuner ON failed: {name}: {message}",
    log_tuner_off_failed: "Tuner OFF failed: {name}: {message}",
    panel_mixer: "Guitar volume",
    panel_tap_tempo: "Tap tempo",
    btn_tap: "TAP",
    tap_tempo_none: "tap to set tempo",
    tap_tempo_waiting: "tap again...",
    tap_tempo_bpm: "{bpm} BPM",
    patch_bpm_unknown: "Patch tempo: —",
    patch_bpm_label: "Patch tempo: {bpm} BPM",
    log_tx_mixer: "TX (mixer channel {channel}): {hex}",
    log_mixer_failed: "Set volume failed: {name}: {message}",
    log_tx_tap_tempo: "TX (tap tempo {bpm} BPM): {hex}",
    log_tap_tempo_failed: "Tap tempo failed: {name}: {message}",
    panel_chain: "Pedal chain",
    chain_none: "Not read yet.",
    chain_preset_label: "{name}  (patch {n}, {bpm} BPM)",
    chain_unnamed: "(unnamed)",
    chain_header_slot: "Slot",
    chain_header_pedal: "Pedal (internal name)",
    chain_header_state: "State",
    chain_header_params: "Parameters",
    chain_on: "ON",
    chain_off: "OFF",
    chain_toggle: "Toggle",
    log_tx_request_preset: "TX (read preset {n}): {hex}",
    log_request_preset_failed: "Read preset {n} failed: {name}: {message}",
    log_tx_active_patch: "TX (which patch is active): {hex}",
    log_active_patch_failed: "Active patch query failed: {name}: {message}",
    log_tx_mixer_request: "TX (read mixer channel {channel}): {hex}",
    log_mixer_request_failed: "Mixer value query failed: {name}: {message}",
    log_tx_toggle: "TX (toggle {name}): {hex}",
    log_toggle_failed: "Toggle {name} failed: {err}: {message}",
    log_preset_parse_failed: "Preset parse failed: {message}",
    label_language: "Language",
    label_name_filter: "Name filter",
    btn_scan: "Scan",
    btn_connect: "Connect",
    btn_disconnect: "Disconnect",
    option_no_device: "— no device selected —",
    log_title: "Log",
    log_export: "Export",
    log_clear: "Clear",
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
    panel_tuner: "Accordatore",
    panel_tuner_display: "Display accordatore (grezzo, non calibrato)",
    btn_tuner_on: "Accordatore ON",
    btn_tuner_off: "Accordatore OFF",
    tuner_no_signal: "nessun segnale",
    tuner_raw: "~{sign}{cents} cent (grezzo {counter}, scala provvisoria)",
    log_tx_tuner_on: "TX (accordatore ON): {hex}",
    log_tx_tuner_off: "TX (accordatore OFF): {hex}",
    log_tuner_on_failed: "Accensione accordatore fallita: {name}: {message}",
    log_tuner_off_failed: "Spegnimento accordatore fallito: {name}: {message}",
    panel_mixer: "Volume chitarra",
    panel_tap_tempo: "Tap tempo",
    btn_tap: "TAP",
    tap_tempo_none: "tocca per impostare il tempo",
    tap_tempo_waiting: "tocca di nuovo...",
    tap_tempo_bpm: "{bpm} BPM",
    patch_bpm_unknown: "Tempo patch: —",
    patch_bpm_label: "Tempo patch: {bpm} BPM",
    log_tx_mixer: "TX (canale mixer {channel}): {hex}",
    log_mixer_failed: "Impostazione volume fallita: {name}: {message}",
    log_tx_tap_tempo: "TX (tap tempo {bpm} BPM): {hex}",
    log_tap_tempo_failed: "Tap tempo fallito: {name}: {message}",
    panel_chain: "Catena effetti",
    chain_none: "Non ancora letta.",
    chain_preset_label: "{name}  (patch {n}, {bpm} BPM)",
    chain_unnamed: "(senza nome)",
    chain_header_slot: "Slot",
    chain_header_pedal: "Pedale (nome interno)",
    chain_header_state: "Stato",
    chain_header_params: "Parametri",
    chain_on: "ON",
    chain_off: "OFF",
    chain_toggle: "Toggle",
    log_tx_request_preset: "TX (lettura preset {n}): {hex}",
    log_request_preset_failed: "Lettura preset {n} fallita: {name}: {message}",
    log_tx_active_patch: "TX (richiesta patch attiva): {hex}",
    log_active_patch_failed: "Richiesta patch attiva fallita: {name}: {message}",
    log_tx_mixer_request: "TX (lettura canale mixer {channel}): {hex}",
    log_mixer_request_failed: "Richiesta valore mixer fallita: {name}: {message}",
    log_tx_toggle: "TX (toggle {name}): {hex}",
    log_toggle_failed: "Toggle {name} fallito: {err}: {message}",
    log_preset_parse_failed: "Analisi preset fallita: {message}",
    label_language: "Lingua",
    label_name_filter: "Filtro nome",
    btn_scan: "Scansiona",
    btn_connect: "Connetti",
    btn_disconnect: "Disconnetti",
    option_no_device: "— nessun dispositivo selezionato —",
    log_title: "Log",
    log_export: "Esporta",
    log_clear: "Pulisci",
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
