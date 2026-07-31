"""Minimal i18n helper: key-based translations with English fallback.

Language is auto-detected from the OS locale; override with the SPARK_GO_LANG
env var (e.g. `SPARK_GO_LANG=it`) for testing or explicit user choice.
"""

import locale
import os

_TRANSLATIONS = {
    "en": {
        "app_title": "Spark GO GUI",
        "label_language": "Language:",
        "label_name_filter": "Name filter:",
        "btn_scan": "Scan",
        "btn_connect": "Connect",
        "btn_disconnect": "Disconnect",
        "panel_send_patch": "Send patch",
        "patch_button": "Patch {n}",
        "panel_tuner": "Tuner",
        "btn_tuner_on": "Tuner ON",
        "btn_tuner_off": "Tuner OFF",
        "panel_tuner_display": "Tuner display (raw, uncalibrated)",
        "tuner_no_signal": "no signal",
        "tuner_raw": "~{cents:+.0f} cents (raw {counter}, provisional scale)",
        "panel_mixer": "Guitar volume",
        "panel_tap_tempo": "Tap tempo",
        "btn_tap": "TAP",
        "tap_tempo_none": "tap to set tempo",
        "tap_tempo_waiting": "tap again...",
        "tap_tempo_bpm": "{bpm:.1f} BPM",
        "patch_bpm_unknown": "Patch tempo: —",
        "patch_bpm_label": "Patch tempo: {bpm:.0f} BPM",
        "panel_chain": "Pedal chain",
        "chain_none": "Not read yet.",
        "chain_preset_label": "{name}  (patch {n}, {bpm:.0f} BPM)",
        "chain_unnamed": "(unnamed)",
        "chain_header_slot": "Slot",
        "chain_header_pedal": "Pedal (internal name)",
        "chain_header_state": "State",
        "chain_header_params": "Parameters",
        "chain_on": "ON",
        "chain_off": "OFF",
        "chain_toggle": "Toggle",
        "log_show": "▸ Show log",
        "log_hide": "▾ Hide log",
        "log_clear": "Clear",
        "log_export": "Export...",
        "log_export_failed": "Export failed: {err}",
        "status_ready": "Ready",
        "status_scanning": "Scanning...",
        "status_scan_completed": "Scan completed: {count} device(s)",
        "status_connecting": "Connecting to {name}...",
        "status_connected": "Connected to {name}",
        "status_disconnected": "Disconnected",
        "warn_select_device": "Select a device first.",
        "error_connection_failed": "Connection failed",
        "error_connection": "Connection error: {type}: {error}",
        "error_not_connected": "Not connected",
        "error_send_patch_failed": "Send patch {n} failed: {type}: {error}",
        "error_tuner_start_failed": "Tuner ON failed: {type}: {error}",
        "error_tuner_stop_failed": "Tuner OFF failed: {type}: {error}",
        "error_active_patch_query": "Active patch query failed: {type}: {error}",
        "error_preset_parse": "Preset parse failed: {type}: {error}",
        "error_request_preset_failed": "Read preset {n} failed: {type}: {error}",
        "error_patch_name_failed": "Read patch {n} name failed: {type}: {error}",
        "error_toggle_effect_failed": "Toggle {name} failed: {type}: {error}",
        "error_mixer_failed": "Set volume failed: {type}: {error}",
        "error_tap_tempo_failed": "Tap tempo failed: {type}: {error}",
        "log_error": "ERROR: {message}",
        "log_tx": "TX: {hex}",
        "log_rx": "RX: {hex}",
    },
    "it": {
        "app_title": "Spark GO GUI",
        "label_language": "Lingua:",
        "label_name_filter": "Filtro nome:",
        "btn_scan": "Scansiona",
        "btn_connect": "Connetti",
        "btn_disconnect": "Disconnetti",
        "panel_send_patch": "Invia patch",
        "patch_button": "Patch {n}",
        "panel_tuner": "Accordatore",
        "btn_tuner_on": "Accordatore ON",
        "btn_tuner_off": "Accordatore OFF",
        "panel_tuner_display": "Display accordatore (grezzo, non calibrato)",
        "tuner_no_signal": "nessun segnale",
        "tuner_raw": "~{cents:+.0f} cent (grezzo {counter}, scala provvisoria)",
        "panel_mixer": "Volume chitarra",
        "panel_tap_tempo": "Tap tempo",
        "btn_tap": "TAP",
        "tap_tempo_none": "tocca per impostare il tempo",
        "tap_tempo_waiting": "tocca di nuovo...",
        "tap_tempo_bpm": "{bpm:.1f} BPM",
        "patch_bpm_unknown": "Tempo patch: —",
        "patch_bpm_label": "Tempo patch: {bpm:.0f} BPM",
        "panel_chain": "Catena effetti",
        "chain_none": "Non ancora letta.",
        "chain_preset_label": "{name}  (patch {n}, {bpm:.0f} BPM)",
        "chain_unnamed": "(senza nome)",
        "chain_header_slot": "Slot",
        "chain_header_pedal": "Pedale (nome interno)",
        "chain_header_state": "Stato",
        "chain_header_params": "Parametri",
        "chain_on": "ON",
        "chain_off": "OFF",
        "chain_toggle": "Toggle",
        "log_show": "▸ Mostra log",
        "log_hide": "▾ Nascondi log",
        "log_clear": "Pulisci",
        "log_export": "Esporta...",
        "log_export_failed": "Esportazione fallita: {err}",
        "status_ready": "Pronto",
        "status_scanning": "Scansione in corso...",
        "status_scan_completed": "Scansione completata: {count} dispositivo/i",
        "status_connecting": "Connessione a {name}...",
        "status_connected": "Connesso a {name}",
        "status_disconnected": "Disconnesso",
        "warn_select_device": "Seleziona prima un dispositivo.",
        "error_connection_failed": "Connessione fallita",
        "error_connection": "Errore di connessione: {type}: {error}",
        "error_not_connected": "Non connesso",
        "error_send_patch_failed": "Invio patch {n} fallito: {type}: {error}",
        "error_tuner_start_failed": "Accensione accordatore fallita: {type}: {error}",
        "error_tuner_stop_failed": "Spegnimento accordatore fallito: {type}: {error}",
        "error_active_patch_query": "Richiesta patch attiva fallita: {type}: {error}",
        "error_preset_parse": "Analisi preset fallita: {type}: {error}",
        "error_request_preset_failed": "Lettura preset {n} fallita: {type}: {error}",
        "error_patch_name_failed": "Lettura nome patch {n} fallita: {type}: {error}",
        "error_toggle_effect_failed": "Toggle {name} fallito: {type}: {error}",
        "error_mixer_failed": "Impostazione volume fallita: {type}: {error}",
        "error_tap_tempo_failed": "Tap tempo fallito: {type}: {error}",
        "log_error": "ERRORE: {message}",
        "log_tx": "TX: {hex}",
        "log_rx": "RX: {hex}",
    },
}


def _detect_language() -> str:
    env_lang = os.environ.get("SPARK_GO_LANG")
    if env_lang:
        return env_lang.split("_")[0].lower()
    try:
        lang = locale.getlocale()[0] or locale.getdefaultlocale()[0]
    except (ValueError, TypeError):
        lang = None
    if lang:
        return lang.split("_")[0].lower()
    return "en"


LANGUAGES = [("en", "English"), ("it", "Italiano")]

_LANG = _detect_language()
if _LANG not in _TRANSLATIONS:
    _LANG = "en"


def get_language() -> str:
    return _LANG


def set_language(lang: str) -> None:
    global _LANG
    if lang in _TRANSLATIONS:
        _LANG = lang


def t(key: str, **kwargs) -> str:
    text = _TRANSLATIONS.get(_LANG, {}).get(key) or _TRANSLATIONS["en"].get(key, key)
    return text.format(**kwargs) if kwargs else text
