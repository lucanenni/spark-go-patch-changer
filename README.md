# spark-go-utils

Reverse engineering of the Positive Grid Spark GO BLE protocol, plus small clients
that talk to it directly.

See [PROTOCOL.md](PROTOCOL.md) for the protocol reference.

## Reference implementations

- `desktop/spark_go_gui.py` — minimal desktop app (Tkinter + `bleak`). Scan, connect,
  and patch switching.
- `web/index.html` — minimal single-file browser app (Web Bluetooth), same scope, no
  external dependencies.

This is intentionally a small starting point. Other capabilities (tuner, individual
effect toggling, reading a preset's full pedal chain, live-state tracking) are being
reintroduced incrementally on feature branches - see the repository's branches rather
than expecting them on `main` yet.
