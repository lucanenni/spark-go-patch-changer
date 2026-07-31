# Positive Grid Spark GO — BLE Protocol Notes

Reverse-engineered notes on the Bluetooth LE protocol used by the **Positive Grid Spark GO** amp, based on BLE sniffs of the official app plus cross-referencing community reverse-engineering of the related Spark 40. This document covers **patch/preset switching**, the **tuner** (on/off plus the real-time note+cents data frames), and **individual effect (stompbox) toggling** — including reading a saved preset's pedal chain back from the device, finding out which patch is actually active, and tracking live (not just saved) effect state via the device's own real-time confirmations. It also covers **Guitar Volume** control and **tap tempo**, both confirmed on real hardware despite starting as speculative ports from a Spark 40/LIVE community project (see their own section for why "Music Volume" isn't part of this protocol at all). A **multi-file client layout** and **live-state tracking during patch changes** are still being reintroduced on other feature branches; see the project's branch list rather than expecting those here yet.

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

## Individual effect (stompbox) toggling

An early hypothesis for this was reverse-engineered from a BLE capture whose device addresses were all anonymized (`00:00:00:00:00:00`), which turned out to mix **two different BLE devices** — a later capture with real MAC addresses showed the handles it used (`0x006D`/`0x004F`/`0x006F`/`0x0052`, characteristics `FFC9`/`FFCA`/`362F71A0-6C96-11E3-981F-0800200C9A66`) belong to a **different peripheral** (MAC `E4:DE:10:0D:69:0C`, likely a Spark Control footswitch), **not the Spark GO** (which nRF Connect confirms only exposes `ffc0`/`ffc1`/`ffc2`). Replaying that protocol never worked, for the obvious reason. **Don't repeat that mistake** — always confirm which MAC address a capture's traffic actually belongs to before trusting it.

The real encoding, on the Spark GO's actual `ffc0`/`ffc1`/`ffc2` characteristics, is understood and confirmed against real hardware, thanks to two community projects that reverse-engineered the same protocol family for the **Spark 40**: [paulhamsh/Spark](https://github.com/paulhamsh/Spark) (`SparkClass/SparkClass.py` and `SparkReaderClass.py`) and [richtamblyn/PGSparkLite](https://github.com/richtamblyn/PGSparkLite) (which vendors and builds on paulhamsh's code, and additionally ships a catalog of internal pedal names in `config/effects/*/*.json`). The Spark GO shares this exact message format.

`CMD 0x01, SUB_CMD 0x15`. The `[payload...]` bytes (see the envelope section above) are built like this, then packed 8-bit→7-bit as described below:

```
[len(name)] [len(name)+0xA0] [name bytes, ASCII] [0xC3 if ON else 0xC2] [0x00]
```

- `name` is not the display name shown in the app — it's an **internal codename**, often the pedal's original real-world name before Positive Grid's marketing/legal renaming. Confirmed examples (internal codename → what the app actually displays): `KlonCentaurSilver` → "Clone Drive", `ChorusAnalog` → "Digital Chorus", `Booster` → "Booster" (this one happens to match). See "Reading the current preset" below for how to get the real codename instead of guessing it from the display text — guessing by removing spaces from the display name (or reordering words) does **not** reliably work.
- The on/off byte is `0xC3` for On, `0xC2` for Off.

**8-bit → 7-bit packing** (SysEx-style, so every on-wire byte stays under `0x80`): split the raw bytes above into groups of up to 7. For each group, emit one "bit8" byte whose bit `i` records whether raw byte `i` of the group had its top bit set, followed by the group's bytes each masked with `0x7F`. (Reverse to decode: `original[i] = data7[i] | (0x80 if bit8 has bit i set else 0)`.)

**Checksum**: the `CHECKSUM` byte in the envelope (inner offset 3) is the **XOR of every byte in the 7-bit-packed payload** — confirmed by independently re-deriving it for real captures of two different pedal names (`KlonCentaurSilver` and `ChorusAnalog`, both On and Off) with an exact match every time. Note `LL` (the header length byte) is the total message length **including the 16-byte header itself**, same rule as everywhere else — e.g. `0x2F` (16+31) for a Drive-length pedal name, `0x2A` (16+26) for a shorter one.

Putting it together, `build_effect_toggle_payload(internal_name, on, seq)`:
```
inner = F0 01 SEQ CHECKSUM 01 15 [7bit-packed payload] F7
```
where `CHECKSUM` is computed from the packed payload as above. Verified end-to-end on real hardware turning Digital Chorus (`ChorusAnalog`) on and off using a freshly-read internal name.

**Failure modes observed, now fully explained**:
- **Wrong `seq`** (too low relative to what the device has already accepted, since it appears to track this persistently across BLE reconnects) → normal-looking ack, no real effect. Simple fix: keep `seq` monotonically increasing, don't restart it low.
- **Right structure, but the named pedal isn't the one currently loaded in that slot** (e.g. replaying a captured `ChorusAnalog` command while `Booster` is loaded in Drive) → normal-looking ack, no real effect. The device validated and accepted the message, it just doesn't apply to the pedal that's actually there.
- **Unrecognized name, or wrong `CHECKSUM` for the payload's actual content** → **no response at all**, not even an ack. The device appears to reject the message outright before it would otherwise ack it.
- **Right pedal, right direction, but it's already in that state** (e.g. sending "Off" to a pedal that's already off) → looks identical to a real failure from the outside (nothing changes) but isn't one. Check the real current state first — via "Real-time effect-state confirmation" below (from the last time it changed) or a footswitch/app observation, **not** via "Reading the current preset", which reflects saved data, not live state (see the correction under that heading).

### Real-time effect-state confirmation

Toggle commands (`CMD 0x01/SUB_CMD 0x15`) get a richer confirmation than a generic ack: `CMD 0x03/SUB_CMD 0x15`, carrying the **same shape as the request's payload** (prefixed pedal name + on/off byte, 7-bit packed, own `CHECKSUM`) — i.e. the device echoes back exactly which pedal is now in exactly which state. This is the reliable way to know a toggle actually landed, confirmed on real hardware: sent a toggle for `ChorusAnalog` → On, got `CMD 0x03/SUB_CMD 0x15` back with `ChorusAnalog` + `0xC3`, and the amp's live audio changed to match.

**However, this isn't the only ack observed.** On the ESP32-S3 bridge (NimBLE-Arduino, not the desktop/web clients' `bleak`/Web Bluetooth), effect toggles consistently got the **generic `CMD 0x04/SUB_CMD 0x15` ack (no payload) instead** — the richer confirmation above was never observed there at all, mirroring the same generic-ack-instead-of-rich-confirmation behavior already documented for patch changes. Whether this is BLE-stack-dependent (MTU/timing differences between `bleak` and NimBLE) or just inconsistent on the amp's side isn't confirmed — but any client relying on this confirmation to know a toggle landed needs to handle both shapes, the same way patch-change handling already does (fall back to what was just requested when the generic ack arrives instead).

Parsing: same string reader used for preset data (`_read_string`/`readString`), then one byte (`0xC3`/`0xC2`) for on/off. No multi-chunk handling needed, it's always a single short message.

**This supersedes re-reading the preset after a toggle**. Both reference clients apply this confirmation directly to the relevant chain-panel row instead of re-requesting the saved patch.

### Which patch is active

There is no way to infer which of the 4 saved patches is currently loaded just from connecting — `CMD 0x02, SUB_CMD 0x01` (reading a preset, below) always requires you to already specify a patch number. `CMD 0x02, SUB_CMD 0x10` solves this: a fixed-shape request (`00 00` + 37×`00` padding) that gets back a short `CMD 0x03/SUB_CMD 0x10` response, single message, not multi-chunk: `[1 byte unknown][1 byte: active patch number, 0-based]`. Confirmed on real hardware — correctly reported `0` (patch 1) after switching to it. Both reference clients send this right after connecting (after a short settle pause) and, on the response, follow up with an ordinary preset-read for that exact patch number — rather than trusting a guessed/default patch number.

### Reading the current preset (chain state)

`CMD 0x02, SUB_CMD 0x01` requests a specific saved patch by number (0-based, matching the patch-change command's `PID`). Payload: `00 00 [preset_num] [32×00 padding] 00 00` (the padding's exact purpose isn't confirmed, but it round-trips fine as all-zero).

The device replies with a **multi-chunk** response, `CMD 0x03, SUB_CMD 0x01`, spread across many BLE notifications (confirmed: 15 chunks / ~566 raw bytes for one preset). To reassemble:
1. Concatenate all raw notification bytes in arrival order (GATT notifications don't align to message boundaries — a single `F0 01 ... F7` chunk can and does span several separate notifications).
2. Split the concatenated stream on `F7` bytes into individual chunks, each shaped like any other message: `F0 01 SEQ CHECKSUM CMD SUB_CMD [7bit-packed data] F7`.
3. Unpack each chunk's data from 7-bit back to 8-bit (same algorithm as the toggle command, in reverse).
4. Since `CMD 0x03 / SUB_CMD 0x01` is a multi-chunk message, each unpacked chunk's data starts with `[num_chunks] [this_chunk_index] [chunk_len]` (3 bytes) followed by that chunk's slice of the real payload. Concatenate the real payload slices (i.e. everything after those first 3 bytes) across all chunks in order. A request's own `SEQ` must be tracked and matched against each incoming chunk's `SEQ` — an in-flight reassembly should discard chunks belonging to a stale/superseded request instead of corrupting the current one.

The reassembled payload is a preset, parsed sequentially as:
```
[1 byte, unknown]  [1 byte: preset number]
[string: UUID]  [string: Name]  [string: Version]  [string: Description]  [string: Icon]
[float: BPM]
[1 byte: 0x90 + 7]   -- always 7 pedal slots
7 × {
  [string: pedal internal name]
  [1 byte: 0xC3 On / 0xC2 Off]
  [1 byte: 0x90 + N]   -- N parameters follow
  N × { [1 byte: param id] [1 byte: 0x91, unknown/fixed] [float: value, 0.0-1.0] }
}
```
String encoding (`read_string`): if the first byte is `0xD9`, the next byte is a raw length; if the first byte is `≥0xA0`, the length is `byte - 0xA0`; otherwise read one more byte and the length is `that byte - 0xA0`. Floats are `0xCA` + 4 bytes, big-endian IEEE 754.

**The 7 pedal slots are in a fixed order**, confirmed from a real decoded preset: **Gate, Comp/Wah, Drive, Amp, MOD/EQ, Delay, Reverb** — note the **Amp model itself is slot index 3**, sitting between Drive and MOD/EQ, and follows the exact same internal-name/on-off/parameters shape as the stompboxes. Example real values from that preset: `bias.noisegate`(Off), `Compressor`(On), `Booster`(On), `Twin`(On, the amp model), `ChorusAnalog`(Off), `DelayRe201`(On), `bias.reverb`(On).

This means a client can build a **correct, general-purpose toggle for whatever's actually in a slot**: read the current preset, pick out the pedal name + current on/off for the target slot index, then build the toggle command from that real name in the direction opposite its current state — no captured reference payload needed for that specific pedal.

**Important correction, found via real-hardware testing**: this read reflects the patch's **saved/flash-stored** configuration, not the device's **live** current state. Toggling an effect changes what's actually playing but does **not** rewrite the saved patch — re-reading the same preset number afterward returns the exact same (pre-toggle) bytes. Confirmed directly: toggled `ChorusAnalog` on (audible on the amp, and confirmed via the real-time confirmation above), then re-read that same preset — it still reported Off, byte-for-byte identical to the pre-toggle read. **Never re-read the preset to "confirm" a toggle** — that would silently overwrite a correct live update with the stale saved value moments later. Loading a patch (`CMD 0x01/SUB_CMD 0x38`) *does* reset live state to match the saved data (that's what "loading" a patch means), so reading right after a patch change is accurate — it's specifically post-toggle reads of the same patch that are misleading. Use "Real-time effect-state confirmation" above to track live changes instead.

### Open questions

- Confirm the `[32×00 padding]` in the preset-request payload is really inert filler and not encoding something (only tested with all-zero padding so far).
- Work out `CMD 0x01 / SUB_CMD 0x06` (`change_effect`, i.e. swapping which pedal model occupies a slot) and `SUB_CMD 0x04` (`change_effect_parameter`, adjusting a knob) — same underlying encoding, per `SparkClass.py`, just not yet built or tested for the Spark GO.
- Confirm whether `CMD 0x02/SUB_CMD 0x10`'s companion `01 00`-marked preset request (per `SparkCommsClass.py` in `richtamblyn/PGSparkLite`) ever actually differs from an ordinary `SUB_CMD 0x01` request for the same number — on real hardware it returned the identical saved-slot data, so both reference clients skip sending it and just combine the `SUB_CMD 0x10` answer with an ordinary `SUB_CMD 0x01` request instead.
- Identify what the second device seen in an early, unrelated capture (`E4:DE:10:0D:69:0C`, characteristics `FFC9`/`FFCA`) actually is (a Spark Control footswitch is the leading guess) — not the Spark GO, not blocking anything here.

## Mixer (Guitar volume)

Reverse-engineered from [paulhamsh/SparkIO6](https://github.com/paulhamsh/SparkIO6), a newer and more complete community firmware project than `paulhamsh/Spark`/`richtamblyn/PGSparkLite` (everything above this section is based on those two) — its own comments explicitly cover "40 / GO / MINI" and one even lists `"Spark GO Audio"` as a possible BLE advertised name.

`SparkIO.ino`'s message parser (used for both directions, since that project bridges between a real app and a real amp) documents:

```
CMD 0x01, SUB_CMD 0x33 ("MIXER change channel")
Payload: [channel: byte] [value: float]

Channels: 0 = IN1, 1 = IN2 1/4", 2 = IN2 XLR, 3 = IN3, 4 = IN4, 5 = MUSIC, 9 = MASTER
```

`value` is `0.0`–`1.0`, matching every other float in this protocol (pedal parameters, BPM). The payload uses the exact same envelope, 8-bit→7-bit packing, and XOR checksum as everything above — `build_mixer_payload`/`buildMixerPayload` reuse the same helpers as the effect-toggle command.

**Channel `0` (Guitar Volume) — CONFIRMED on real Spark GO hardware**: sending `build_mixer_payload(0, value, seq)` changes only the guitar input's volume, exactly matching what the physical rotary encoder controls, with no audible effect on the Bluetooth/music channel. Turning that physical encoder also makes the amp broadcast an unsolicited notification with the new value (`CMD 0x01` or `CMD 0x03`/`SUB_CMD 0x33`, 6-byte `[channel][float]` payload — same shape as the outgoing command, confirmed with real hardware) — both reference clients listen for this passively and update the slider live when it happens, though there's still no way to query the value proactively (see "Reading the current value on connect" below).

**Channel `5` ("MUSIC") — not used, and not expected to do anything meaningful here.** The Spark GO's official spec sheet lists a "Music Volume" control (a pair of physical up/down buttons) right next to Guitar Volume under "TOP PANEL CONTROLS", which originally suggested it might be this same channel. **Confirmed otherwise by testing on real hardware**: pressing those physical buttons changes the volume on the *phone* (the Bluetooth audio source), not anything on the amp — they're standard **AVRCP volume commands sent to the connected Bluetooth audio device**, a completely different mechanism from the Spark GO's own `ffc0`/`ffc1`/`ffc2` control service this whole document is about. There is no confirmed way to control an on-amp "music" mixer channel via this protocol, and no reason left to believe channel `5` does anything on the Spark GO specifically (it may be meaningful on the Spark LIVE, which has an actual hardware mixer with real IN1-4/MUSIC/MASTER channels). Neither reference client exposes a Music Volume control any more.

### Reading the current value on connect (confirmed not to work)

The source project's Spark LIVE section documents a separate pair, `CMD 0x02/SUB_CMD 0x33` request (`[channel: byte]` payload) → `CMD 0x03/SUB_CMD 0x33` response (**just a bare float, 5 bytes unpacked, no channel byte** — the caller has to already know which channel it asked about). This is commented as LIVE-specific, with nothing equivalent documented for the classic 40/GO/MINI firmware. Both reference clients tried it anyway on connect, right after the active-patch query, on the strength of the *set* command already working on GO despite similar doubts.

**Tested on real hardware and confirmed not to work**: the request goes out fine (visible as TX in the log) but the Spark GO never sends any response back, for the Guitar channel either. This is now disabled (commented out) in both reference clients rather than deleted, in case a future BLE sniff of the official Positive Grid app reveals the real request shape - `build_mixer_request_payload`/`parse_mixer_value_response` (`buildMixerRequestPayload`/`parseMixerValueResponse` in JS) are still defined and functional, just unused. The Guitar Volume slider instead starts at a neutral 50% on connect and only reflects the real value once the user moves it themselves, or once the amp broadcasts a live update from someone turning the physical encoder (see above) - there is currently no known way to learn the starting value without one of those two things happening first.

## Tap tempo

Also from `paulhamsh/SparkIO6`, `MessageOut::send_tap_tempo(float val)`:

```
CMD 0x01, SUB_CMD 0x62
Payload: [value: float, BPM] [0x3F] [0x3F]
```

**CONFIRMED on real Spark GO hardware** — despite the doubts below, sending `build_tap_tempo_payload(bpm, seq)` with a locally-computed BPM (averaged from tap intervals, see the reference clients) works and syncs tempo-based effects on the device. The trailing `0x3F 0x3F` is copied verbatim from the source; its purpose is still unknown (possibly padding/reserved, matching how other commands in this protocol have unexplained fixed trailing bytes), but sending it as-is works. Same envelope/packing/checksum as everything else — `build_tap_tempo_payload`/`buildTapTempoPayload` reuse the standard helpers.

**Why this one looked shakier than the mixer command before testing** (kept for the record, since the reasoning was wrong in a useful way — a `// is this right??` comment from the original author turned out not to mean the command was wrong, just that *that author* hadn't verified it):
- The source itself flags the outgoing sub-command with a `// is this right??` comment.
- The incoming/response side is `CMD 0x03/SUB_CMD 0x63` (`0x63`, not `0x62`) — every other paired command in the entire source project uses the **same** `SUB_CMD` for both the `CMD 0x01` request and the `CMD 0x03` response (patch change: `0x38`/`0x38`; effect toggle: `0x15`/`0x15`; preset read: `0x01`/`0x01`). Still unexplained, but evidently doesn't stop the *outgoing* `0x0162` command from working.
- No code anywhere in `paulhamsh/SparkIO6` or `paulhamsh/SparkBox` (which exposes `send_tap_tempo` as a public API) actually calls it — it was defined but, as far as this research found, never exercised against a real amp by its own authors before this project tried it.

Reference clients here compute the BPM locally from tap intervals (last up to 4 taps, averaged, reset if a tap arrives more than 2 seconds after the previous one) and send the result on every tap — there's no protocol-level "start/stop tapping" concept, just a plain BPM value sent each time.

## Reference implementation

- **Desktop** (Tkinter + `bleak`), split by concern:
  - `desktop/protocol.py` — GATT handles, message envelope, `build_patch_payload`, `build_tuner_start_payload`/`build_tuner_stop_payload`, `parse_tuner_frame`, `fmt_hex`, plus the effect-toggling/chain-reading pieces: `pack_7bit`/`unpack_7bit`, `xor_all`, `build_effect_toggle_payload`, `build_preset_request_payload`, `build_state_request_payload`, `parse_preset_data`, `parse_effect_state_notification`, `parse_active_patch_notification`, `SLOT_LABELS`, and `build_mixer_payload`/`parse_mixer_notification`/`build_tap_tempo_payload` (Guitar Volume and tap tempo, both confirmed on real hardware - see their own sections above). `build_mixer_request_payload`/`parse_mixer_value_response` are also defined but currently unused (confirmed not to work - see "Reading the current value on connect"). No UI or I/O code.
  - `desktop/ble_backend.py` — `BleBackend`: async BLE I/O on a background event-loop thread, reports back via a queue. Reassembles multi-chunk notifications (`_handle_notification_bytes`/`_process_chunk`) and dispatches `preset`/`effect_state`/`patch_name`/`mixer` events alongside the existing `tx`/`rx`/`status`/`error`. On connect (after a settle pause): queries which patch is active and reads its full chain (`_request_active_patch_and_wait`/`_read_preset_and_wait`), then sequentially reads the other 3 patches just for their names (`read_all_patch_names`, emitting `patch_name` for all 4 - shown under the patch buttons). Preset reads are always sequential, awaited one at a time via an internal completion event - the multi-chunk reassembly state only tracks a single in-flight request, so a second one before the first finishes would silently lose whichever response arrives second. After a manual patch change, re-reads that exact patch's chain the same way. The connect-time Guitar-volume read attempt is commented out (see PROTOCOL.md's mixer section). No `tkinter` imports (see HANDOFF.md for why that boundary matters).
  - `desktop/i18n.py` — key-based translations (`en`/`it`), OS-locale auto-detection, `SPARK_GO_LANG` env override.
  - `desktop/spark_go_gui.py` — the Tkinter `App` and entry point; imports the three modules above. Two-column layout: connection/patches/tuner/guitar-volume/tap-tempo on the left, pedal chain + status bar + collapsible log (with Export/Clear) on the right. Patch switching (each of the 4 patch buttons shows that patch's name underneath, populated from the connect-time scan above), tuner ON/OFF with a live note+cents gauge (Canvas-based needle bar), a pedal-chain panel (all 7 slots: name, live on/off, parameters, per-slot Toggle button) backed by the chain-reading/toggle protocol above — live state tracked via the real-time confirmation notification (and applied optimistically as soon as a toggle/mixer command is sent, since that confirmation isn't guaranteed to arrive) rather than by re-reading the preset — plus a Guitar Volume slider (`_on_mixer_scale_click` works around a `ttk.Scale`/macOS quirk where clicking the trough jumps straight to 0 or the max instead of moving proportionally to the click), a Tap Tempo button, and the active patch's tempo shown next to it (`patch_bpm_label`, from the same preset data already parsed for the chain panel).
  - Scan, connect/disconnect, patch switching, the tuner, the pedal chain, and Guitar Volume/tap-tempo, with just enough logging (raw TX/RX, collapsed by default) to follow what's happening. Auto-scans on startup and auto-connects if exactly one device is found.
- **Web** (Web Bluetooth), same scope as the desktop app, no external dependencies (no CDN, no build step):
  - `web/index.html` — markup only, `data-i18n*` attributes mark translatable text; includes a `.fsw-name` label under each of the 4 patch buttons, the pedal-chain panel markup (`#chainPresetLabel`, `#chainRows`, rows built dynamically in JS), a Guitar Volume slider, and a Tap Tempo button with the active patch's tempo shown next to it (`#patchBpmNote`).
  - `web/css/style.css` — all styling, including the tuner gauge, the patch-name labels (`.fsw-cell`/`.fsw-name`), the chain panel (`.chain-preset`, `.chain-header-row`/`.chain-row`, `.chain-state`, `.chain-params`), the Guitar Volume slider (`.mixer-row`), and small notes (`.panel-note`).
  - `web/js/protocol.js` — GATT UUIDs, `buildPatchPayload`, `buildTunerStartPayload`/`buildTunerStopPayload`, `parseTunerFrame`, `fmtHex`, plus `pack7bit`/`unpack7bit`, `xorAll`, `buildEffectTogglePayload`, `buildPresetRequestPayload`, `buildStateRequestPayload`, `parsePresetData`, `parseEffectStateNotification`, `parseActivePatchNotification`, `SLOT_LABELS`, and `buildMixerPayload`/`parseMixerNotification`/`buildTapTempoPayload`. `buildMixerRequestPayload`/`parseMixerValueResponse` are also defined but currently unused (see PROTOCOL.md's mixer section).
  - `web/js/i18n.js` — key-based translations (`en`/`it`), `navigator.language` auto-detection, `t()` + `applyStaticTranslations()`.
  - `web/js/app.js` — UI wiring and BLE glue, including the tuner gauge and the pedal-chain panel; reassembles multi-chunk notifications (`handleNotificationBytes`/`processChunk`), functionally at parity with the desktop app: active-patch detection on connect followed by a sequential, awaited (`readPresetAndWait`/`requestActivePatchAndWait`) scan of all 4 patches for their names (`readAllPatchNames`, shown under the patch buttons) - one at a time, since `presetAccum`/`presetSeqInFlight` only track a single in-flight preset read - plus an accurate chain re-read after every manual patch change, and live state applied optimistically on send and corrected by the real-time confirmation notification if it disagrees. Also the same Guitar Volume/tap-tempo controls as the desktop client (the connect-time Guitar-volume read attempt is commented out too), and log Export/Clear buttons. Loaded last, after `i18n.js` and `protocol.js`.
- **ESP32-S3 firmware** (`ESP32-S3-ChocolatePlus-bridge/`, PlatformIO/Arduino, NimBLE + Adafruit TinyUSB), a USB-MIDI-to-BLE bridge rather than a standalone client: plugs into an MVave Chocolate Plus's USB HOST port and translates the pedal's Program Change/Control Change messages into patch switches, effect toggles, tuner start/stop, Guitar Volume, and tap tempo against the Spark GO, with a small on-device status/tuner display. No i18n (fixed English strings). See its own README for the MIDI mapping and hardware notes.
