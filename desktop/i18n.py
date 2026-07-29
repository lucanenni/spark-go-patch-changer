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
        "log_show": "▸ Show log",
        "log_hide": "▾ Hide log",
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
        "log_show": "▸ Mostra log",
        "log_hide": "▾ Nascondi log",
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
