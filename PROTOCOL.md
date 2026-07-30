# Positive Grid Spark GO — BLE Protocol Notes

Reverse-engineered notes on the Bluetooth LE protocol used by the **Positive Grid Spark GO** amp, based on BLE sniffs of the official app. This document currently covers **patch/preset switching** and the **tuner** (on/off plus the real-time note+cents data frames). Other confirmed capabilities (effect toggling, reading a preset's pedal chain, live-state tracking) are being reintroduced incrementally on feature branches; see the project's branch list rather than expecting them here yet.

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

## Tuner ON / OFF

Uses a shorter header (length byte `0x19` instead of `0x1A`):

```
01 FE 00 00 53 FE 19 00 00 00 00 00 00 00 00 00
```

Inner payload (9 bytes), same envelope shape as everywhere else — `CMD 0x01`, `SUB_CMD 0x65`, then a 2-byte payload `[0x01, marker]` whose XOR gives `CHECKSUM`:

```
F0 01 SEQ CHECKSUM 01 65 01 MARKER F7
```

| Action | MARKER | CHECKSUM (`0x01 ^ MARKER`) |
|---|---|---|
| Tuner **ON** | `0x43` | `0x42` |
| Tuner **OFF** | `0x42` | `0x43` |

`SEQ` is the **same shared, continuously-incrementing counter** used by patch change — not an independent counter per command type. **Bug found and fixed**: an early version of both reference clients sent tuner ON/OFF with the literal `SEQ` bytes from the original BLE capture (`0x13`/`0x14`), completely independent of the patch command's own counter. This broke patch switching afterwards — the device appears to track one persistent sequence counter across every command regardless of type, and jumping between two independent counters put it out of sync in a way the firmware silently rejected. Fix: advance one shared counter by 1 on every command sent, tuner included.

Full commands (with an example `SEQ` of `0x20`):

```
Tuner ON:  01 FE 00 00 53 FE 19 00 00 00 00 00 00 00 00 00 F0 01 20 42 01 65 01 43 F7
Tuner OFF: 01 FE 00 00 53 FE 19 00 00 00 00 00 00 00 00 00 F0 01 21 43 01 65 01 42 F7
```

Both confirmed working on real hardware, including switching patches again afterwards.

## Tuner data frames

While the tuner is ON, the device streams notification frames (`CMD 0x03`/`SUB_CMD 0x64`) on the notify characteristic. Two frame shapes have been observed, both 14 bytes:

**Idle / no signal**:

```
F0 01 CTR 7F 03 64 0E 04 4A 3F 00 00 00 F7
```

**Active detection**, e.g.:

```
F0 01 CTR 77 03 64 1A 04 4A 3D 26 38 00 F7
```

Byte-by-byte (0-indexed from `F0`):

| Offset | Field | Notes |
|---|---|---|
| 0–1 | `F0 01` | Fixed frame start |
| 2 | Rolling counter | Increments per notification, ~6 bits wide, unrelated to musical content |
| 3 | Unknown / noisy | Changes rapidly during detection; possibly signal amplitude |
| 4–5 | `03 64` | Fixed — this is what identifies the frame as tuner data (`CMD`/`SUB_CMD`) |
| 6 | Unknown | Cycles through 8 fixed values (`(n << 3) \| 0x02`) — looks like an internal DSP frame index |
| 7 | **Detected note class** | Standard MIDI pitch class, `0`=C … `11`=B. Confirmed against a full 6-string sweep |
| 8 | `4A` | Fixed constant in every frame |
| 9–10 | **Fine pitch counter** | `(byte9 << 7) \| byte10` — a ~14-bit counter that climbs with pitch and resets at each semitone boundary in lockstep with byte 7 |
| 11 | Unknown / noisy | Fluctuates quickly, not monotonic |
| 12 | Status/confidence flag? | Only 4 distinct values seen (`0x00, 0x20, 0x40, 0x60`) |
| 13 | `F7` | Fixed frame end |

**Idle detection**: in every idle frame seen so far, byte 6 is `0x0E` and bytes 9–12 sit exactly at `0x3F 0x00 0x00 0x00`. Clients treat a frame matching that exact pattern as "no signal" rather than a real (if oddly centered) reading.

### Calibration (provisional)

The 0-cents center consistently sits at **counter ≈ 8064** (matching the idle frame's own default value, `0x3F` combined) regardless of note — likely a fixed firmware reference, not computed per-note. The counts-per-cent scale is **not solidly pinned down**: estimates from live sweeps ranged from ~1 to ~6.6 units/cent. Both reference clients use a provisional working scale: **center = 8064, ±50 cents ≈ ±345 counter units**, derived from the widest single-string sweep captured so far. Treat the on-screen cents value as a rough indicator, not a calibrated measurement — refining it needs a longer, externally-verified reference test (e.g. holding a single string at a known pitch against a calibrated tuner).

## Reference implementation

- **Desktop** (Tkinter + `bleak`), split by concern:
  - `desktop/protocol.py` — GATT handles, message envelope, `build_patch_payload`, `build_tuner_start_payload`/`build_tuner_stop_payload`, `parse_tuner_frame`, `fmt_hex`. No UI or I/O code.
  - `desktop/ble_backend.py` — `BleBackend`: async BLE I/O on a background event-loop thread, reports back via a queue. No `tkinter` imports (see HANDOFF.md for why that boundary matters).
  - `desktop/i18n.py` — key-based translations (`en`/`it`), OS-locale auto-detection, `SPARK_GO_LANG` env override.
  - `desktop/spark_go_gui.py` — the Tkinter `App` and entry point; imports the three modules above. Patch switching, tuner ON/OFF, and a live note+cents gauge (Canvas-based needle bar) fed by the tuner data frames.
  - Scan, connect/disconnect, patch switching, and the tuner, with just enough logging (raw TX/RX, collapsed by default) to follow what's happening. Auto-scans on startup and auto-connects if exactly one device is found.
- **Web** (Web Bluetooth), same scope as the desktop app, no external dependencies (no CDN, no build step):
  - `web/index.html` — markup only, `data-i18n*` attributes mark translatable text.
  - `web/css/style.css` — all styling, including the tuner gauge.
  - `web/js/protocol.js` — GATT UUIDs, `buildPatchPayload`, `buildTunerStartPayload`/`buildTunerStopPayload`, `parseTunerFrame`, `fmtHex`.
  - `web/js/i18n.js` — key-based translations (`en`/`it`), `navigator.language` auto-detection, `t()` + `applyStaticTranslations()`.
  - `web/js/app.js` — UI wiring and BLE glue, including the tuner gauge; loaded last, after `i18n.js` and `protocol.js`.
