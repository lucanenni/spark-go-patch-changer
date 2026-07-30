# spark-go-utils

Reverse engineering of the Positive Grid Spark GO BLE protocol, plus small clients
that talk to it directly.

See [PROTOCOL.md](PROTOCOL.md) for the protocol reference.

## Reference implementations

- `desktop/` — minimal desktop app (Tkinter + `bleak`). Scan, connect, patch
  switching, and a tuner (ON/OFF plus a live note+cents gauge), split into
  `spark_go_gui.py` (UI), `ble_backend.py` (BLE I/O), `protocol.py` (wire format),
  and `i18n.py` (translations, English/Italian).
- `web/` — minimal browser app (Web Bluetooth), same scope, no external dependencies,
  split into `index.html`, `css/style.css`, and `js/protocol.js` / `js/i18n.js` /
  `js/app.js`.
- [`ESP32-S3-ChocolatePlus-bridge/`](ESP32-S3-ChocolatePlus-bridge/) — ESP32-S3 dongle
  firmware bridging an MVave Chocolate Plus MIDI pedal (USB-MIDI) to the Spark GO
  (BLE): patch switching, effect toggling, and tuner display.

Both clients auto-detect the system/browser language (English/Italian for now) for
all user-visible text; see `i18n.py` / `js/i18n.js` to add more languages.

This is intentionally a small starting point. Other capabilities (individual effect
toggling, reading a preset's full pedal chain, live-state tracking) are being
reintroduced incrementally on feature branches - see the repository's branches rather
than expecting them on `main` yet.
