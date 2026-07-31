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
  `js/app.js`. Hosted, no install needed, at
  **[the live control panel](https://lucanenni.github.io/spark-go-utils/)**
  (latest release; needs a Web Bluetooth browser, e.g. Chrome/Edge).
- [`ESP32-S3-ChocolatePlus-bridge/`](ESP32-S3-ChocolatePlus-bridge/) — ESP32-S3 dongle
  firmware bridging an MVave Chocolate Plus MIDI pedal (USB-MIDI) to the Spark GO
  (BLE): patch switching, individual effect toggling, tuner display, Guitar
  Volume, and tap tempo. Flash it from a browser, no software install, at
  **[the web flash tool](https://lucanenni.github.io/spark-go-utils/flash/)**
  (latest release; Chrome/Edge/Opera on a computer only - uses Web Serial).

The desktop and web clients auto-detect the system/browser language
(English/Italian for now) for all user-visible text; see `i18n.py` / `js/i18n.js`
to add more languages. The ESP32 firmware doesn't have localization (fixed
English strings on its small screen).
