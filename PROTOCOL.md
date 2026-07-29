# Positive Grid Spark GO — BLE Protocol Notes

Reverse-engineered notes on the Bluetooth LE protocol used by the **Positive Grid Spark GO** amp, based on BLE sniffs of the official app. This document currently covers what's needed for **patch/preset switching** — the first, minimal slice of the protocol. Other confirmed capabilities (tuner, effect toggling, reading a preset's pedal chain, live-state tracking) are being reintroduced incrementally on feature branches; see the project's branch list rather than expecting them here yet.

> Everything here comes from passive BLE captures and black-box testing against a real device. There is no official protocol documentation — treat all of this as best-effort reverse engineering, not a spec.

## GATT profile

| Role | UUID |
|---|---|
| Service | `0000ffc0-0000-1000-8000-00805f9b34fb` |
| Write characteristic | `0000ffc1-0000-1000-8000-00805f9b34fb` (write / write-without-response / read) |
| Notify characteristic | `0000ffc2-0000-1000-8000-00805f9b34fb` (notify / read) |

Commands are sent as a **Write Command** (no response) to the write characteristic. Notifications (confirmations, acks) arrive on the notify characteristic.

## Common message envelope

Every outgoing command shares the same 16-byte header:

```
01 FE 00 00 53 FE LL 00 00 00 00 00 00 00 00 00
```

- `01 FE 00 00 53 FE` — fixed magic/preamble.
- `LL` — the **total message length including the 16-byte header itself**, i.e. `LL = 16 + len(inner)`. For patch change, `LL = 0x1A` (16 + 10).
- Remaining bytes — always zero in every capture so far.

The header is followed by an inner payload that starts with `F0 01` and ends with `F7` (SysEx-style framing):

```
[16-byte header][F0 01 ... F7]
```

## Preset / patch change

Inner payload (10 bytes):

```
F0 01 SEQ PID 01 38 00 00 PID F7
```

- `SEQ` — a rolling sequence byte, incremented on every command sent (starts arbitrarily, e.g. `0x20`, wraps at `0xFF`). Must be a single counter shared across every command sent in the session.
- `PID` — patch index, zero-based: `0x00`–`0x03` for patches 1–4.

Full command example (patch 1, header length `0x1A`):

```
01 FE 00 00 53 FE 1A 00 00 00 00 00 00 00 00 00 F0 01 20 00 01 38 00 00 00 F7
```

Confirmed working for all 4 patch slots.

**Confirmation received**: the device replies with a short message, `CMD 0x03/SUB_CMD 0x38` (not a generic ack), of the shape `F0 01 SEQ 00 03 38 00 00 [PID] F7`, confirming the patch actually switched to. The command doesn't itself guarantee the switch has *finished* applying though — reading anything about the new patch immediately can race with this; a short settle pause (the reference client uses ~0.3s) avoids acting on stale state.

## Reference implementation

- `desktop/spark_go_gui.py` — minimal desktop app (Tkinter + `bleak`). Scan, connect/disconnect, and patch switching only, with just enough logging (raw TX/RX, collapsed by default) to follow what's happening. Auto-scans on startup and auto-connects if exactly one device is found.
- `web/index.html` — minimal single-file browser app (Web Bluetooth), same scope as the desktop app, no external dependencies.
