"""Spark GO BLE wire protocol: GATT handles and message building.

See PROTOCOL.md for the full reverse-engineered protocol reference.
"""

import struct

NOTIFY_HANDLE = 0x0007
WRITE_HANDLE = 0x000A

PRESET_HEADER = bytes.fromhex("01 FE 00 00 53 FE 1A 00 00 00 00 00 00 00 00 00")
TUNER_HEADER = bytes.fromhex("01 FE 00 00 53 FE 19 00 00 00 00 00 00 00 00 00")
DEFAULT_SEQ = 0x20

SLOT_LABELS = ["Gate", "Comp/Wah", "Drive", "Amp", "MOD/EQ", "Delay", "Reverb"]

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
# From PROTOCOL.md's tuner calibration notes: "0 cents" consistently sits at ~8064
# regardless of note (matches the idle frame's default), and +-50 cents roughly spans
# +-345 counter units. Both numbers are provisional, not a confirmed scale.
TUNER_CENTER = 8064
TUNER_HALF_RANGE = 345  # counter units corresponding to ~50 cents


def fmt_hex(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def build_patch_payload(patch_number: int, seq: int) -> bytes:
    if patch_number not in (1, 2, 3, 4):
        raise ValueError("patch_number must be 1..4")
    patch_id = patch_number - 1
    inner = bytes([0xF0, 0x01, seq & 0xFF, patch_id, 0x01, 0x38, 0x00, 0x00, patch_id, 0xF7])
    return PRESET_HEADER + inner


def build_tuner_start_payload(seq: int) -> bytes:
    inner = bytes([0xF0, 0x01, seq & 0xFF, 0x42, 0x01, 0x65, 0x01, 0x43, 0xF7])
    return TUNER_HEADER + inner


def build_tuner_stop_payload(seq: int) -> bytes:
    inner = bytes([0xF0, 0x01, seq & 0xFF, 0x43, 0x01, 0x65, 0x01, 0x42, 0xF7])
    return TUNER_HEADER + inner


def _build_header(inner_len: int) -> bytes:
    total_len = 16 + inner_len
    return bytes([0x01, 0xFE, 0x00, 0x00, 0x53, 0xFE, total_len & 0xFF]) + bytes(9)


# ---- Effect toggle / preset read (see PROTOCOL.md "Individual effect toggling" and
# "Reading the current preset") ----
#
# Every command/response inner payload beyond F0 01 SEQ CHECKSUM CMD SUB_CMD is packed
# 8-bit -> 7-bit, SysEx-style: split into groups of up to 7 bytes, each group prefixed
# with a "bit8" byte recording which of the 7 bytes had their top bit set (so every
# byte on the wire stays under 0x80). CHECKSUM is the XOR of every byte in that packed
# payload - confirmed against real hardware for multiple pedal names, both On and Off.


def pack_7bit(data8: bytes) -> bytes:
    out = bytearray()
    for start in range(0, len(data8), 7):
        group = data8[start:start + 7]
        bit8 = 0
        packed = bytearray()
        for idx, b in enumerate(group):
            if b & 0x80:
                bit8 |= (1 << idx)
            packed.append(b & 0x7F)
        out.append(bit8)
        out.extend(packed)
    return bytes(out)


def unpack_7bit(data7: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(data7):
        bit8 = data7[i]
        group = data7[i + 1:i + 8]
        i += 1 + len(group)
        for idx, b in enumerate(group):
            if bit8 & (1 << idx):
                b |= 0x80
            out.append(b)
    return bytes(out)


def xor_all(data: bytes) -> int:
    x = 0
    for b in data:
        x ^= b
    return x


def build_effect_toggle_payload(internal_name: str, on: bool, seq: int) -> bytes:
    """Toggle the pedal identified by its internal codename (NOT the display name
    shown in the app - see PROTOCOL.md). Use parse_preset_data's result to find the
    real current name/state for a slot instead of guessing.
    """
    name_bytes = internal_name.encode("ascii")
    data8 = bytes([len(name_bytes), len(name_bytes) + 0xA0]) + name_bytes
    data8 += bytes([0xC3 if on else 0xC2, 0x00])
    data7 = pack_7bit(data8)
    checksum = xor_all(data7)
    inner = bytes([0xF0, 0x01, seq & 0xFF, checksum, 0x01, 0x15]) + data7 + b"\xF7"
    return _build_header(len(inner)) + inner


def build_preset_request_payload(preset_num: int, seq: int) -> bytes:
    """Ask the device to send back the full pedal chain of saved patch preset_num
    (0-based, same numbering as build_patch_payload's patch_id). The response is a
    multi-chunk CMD 0x03/SUB_CMD 0x01 message - reassembled by the BLE backend.
    """
    inner = bytes([0xF0, 0x01, seq & 0xFF, 0x00, 0x02, 0x01, 0x00, 0x00, preset_num & 0xFF])
    inner += bytes(32)  # padding, purpose unconfirmed - round-trips fine as all-zero
    inner += bytes([0x00, 0x00, 0xF7])
    return _build_header(len(inner)) + inner


def build_state_request_payload(seq: int) -> bytes:
    """Ask the device which patch is actually active right now (CMD 0x02/SUB_CMD
    0x10) - unlike build_preset_request_payload, which reads a specific saved slot
    by number and has no way to confirm that's the one really loaded. The response
    is a single short CMD 0x03/SUB_CMD 0x10 message, not multi-chunk.
    """
    inner = bytes([0xF0, 0x01, seq & 0xFF, 0x00, 0x02, 0x10]) + bytes(37) + b"\xF7"
    return _build_header(len(inner)) + inner


def _read_string(data: bytes, pos: int):
    a_byte = data[pos]
    pos += 1
    if a_byte == 0xD9:  # str8: one length byte follows
        str_len = data[pos]
        pos += 1
    elif a_byte == 0xDA:  # str16: two big-endian length bytes follow
        str_len = (data[pos] << 8) | data[pos + 1]
        pos += 2
    elif a_byte == 0xDB:  # str32: four big-endian length bytes follow
        (str_len,) = struct.unpack(">I", data[pos:pos + 4])
        pos += 4
    elif 0xA0 <= a_byte <= 0xBF:  # fixstr: length encoded in the byte itself
        str_len = a_byte - 0xA0
    else:
        # Legacy fallback for the effect-toggle confirmation's wire shape (see
        # parse_effect_state_notification), which prepends a raw length byte before
        # the fixstr-style second byte - not a real preset-read string encoding.
        str_len = data[pos] - 0xA0
        pos += 1
    s = data[pos:pos + str_len].decode("ascii", errors="replace")
    return s, pos + str_len


def _read_float(data: bytes, pos: int):
    pos += 1  # skip the 0xCA prefix byte
    (val,) = struct.unpack(">f", data[pos:pos + 4])
    return val, pos + 4


def _build_float(value: float) -> bytes:
    return b"\xCA" + struct.pack(">f", value)


def parse_preset_data(data: bytes) -> dict:
    """Parse a reassembled preset-read response (see PROTOCOL.md "Reading the current
    preset") into {preset_num, uuid, name, version, description, icon, bpm, pedals:[...]}.
    Each pedal is {name (internal codename), on (bool), params: [{id, value}, ...]}.
    """
    pos = 1  # skip one unknown leading byte
    preset_num = data[pos]
    pos += 1
    uuid, pos = _read_string(data, pos)
    name, pos = _read_string(data, pos)
    version, pos = _read_string(data, pos)
    description, pos = _read_string(data, pos)
    icon, pos = _read_string(data, pos)
    bpm, pos = _read_float(data, pos)
    num_pedals = data[pos] - 0x90
    pos += 1
    pedals = []
    for _ in range(num_pedals):
        pedal_name, pos = _read_string(data, pos)
        on = data[pos] == 0xC3
        pos += 1
        num_params = data[pos] - 0x90
        pos += 1
        params = []
        for _ in range(num_params):
            param_id = data[pos]
            pos += 2  # skip param_id and the fixed 0x91 spec byte
            val, pos = _read_float(data, pos)
            params.append({"id": param_id, "value": val})
        pedals.append({"name": pedal_name, "on": on, "params": params})
    return {
        "preset_num": preset_num,
        "uuid": uuid,
        "name": name,
        "version": version,
        "description": description,
        "icon": icon,
        "bpm": bpm,
        "pedals": pedals,
    }


def parse_effect_state_notification(data: bytes) -> dict:
    """Parse a CMD 0x03/SUB_CMD 0x15 notification: the device's own real-time
    confirmation of an effect's new on/off state, sent unsolicited right after we
    (or the official app, or a footswitch) change it. Distinct from - and more
    reliable than - re-reading a saved preset, which reflects what's stored for that
    patch slot, not the live/current state (toggling doesn't rewrite the saved
    preset). {name: internal codename, on: bool}.
    """
    name, pos = _read_string(data, 0)
    return {"name": name, "on": data[pos] == 0xC3}


def parse_active_patch_notification(data: bytes) -> int:
    """Parse a CMD 0x03/SUB_CMD 0x10 notification (response to
    build_state_request_payload): which patch is truly active on the device right
    now, 0-based. data[0] is an unknown/reserved byte."""
    return data[1]


# ---- Guitar volume and tap tempo ----
#
# Both reverse-engineered from paulhamsh/SparkIO6 (a newer, more complete community
# firmware than the paulhamsh/Spark and richtamblyn/PGSparkLite repos everything else
# in this file is based on - its own comments explicitly cover "40 / GO / MINI") and
# CONFIRMED on real Spark GO hardware. The source project's "MIXER" enum also
# documents a channel 5 ("MUSIC"), but the Spark GO's physical Music Volume buttons
# turned out to be plain Bluetooth AVRCP volume commands sent to the paired phone/
# audio source - nothing to do with this GATT protocol at all - so there's no reason
# to believe channel 5 controls anything meaningful here, and it's not exposed by
# either reference client. See PROTOCOL.md's "Mixer" section for the full story.

MIXER_CHANNEL_GUITAR = 0  # "IN1" in the source comments - CONFIRMED


def build_mixer_payload(channel: int, value: float, seq: int) -> bytes:
    """Set a mixer channel's volume (CMD 0x01/SUB_CMD 0x33). `value` is 0.0-1.0,
    matching every other float parameter in this protocol. CONFIRMED on real Spark GO
    hardware for MIXER_CHANNEL_GUITAR - see PROTOCOL.md's "Mixer" section. No
    confirmation/ack for this command has been observed in the source project, so
    clients apply it optimistically rather than waiting for one.
    """
    data8 = bytes([channel & 0xFF]) + _build_float(value)
    data7 = pack_7bit(data8)
    checksum = xor_all(data7)
    inner = bytes([0xF0, 0x01, seq & 0xFF, checksum, 0x01, 0x33]) + data7 + b"\xF7"
    return _build_header(len(inner)) + inner


def parse_mixer_notification(data: bytes) -> dict:
    """Parse an unsolicited CMD 0x01 or 0x03/SUB_CMD 0x33 message reporting a mixer
    channel's current value - same shape as build_mixer_payload's own request, since
    the source project's parser doesn't distinguish a separate response shape for
    this command (unlike patch change or effect toggle)."""
    channel = data[0]
    value, _ = _read_float(data, 1)
    return {"channel": channel, "value": value}


def build_mixer_request_payload(channel: int, seq: int) -> bytes:
    """Ask the device for a mixer channel's current value (CMD 0x02/SUB_CMD 0x33) -
    the source project documents this pairing as Spark LIVE-specific (the classic
    40/GO/MINI section has no read/request command for the mixer at all). CONFIRMED
    NOT TO WORK on real Spark GO hardware: sends fine (TX logged) but never gets any
    response back, for the Guitar channel either. Currently unused - kept only in
    case a future BLE sniff of the official app finds the real request shape. See
    PROTOCOL.md's "Mixer" section.
    """
    data8 = bytes([channel & 0xFF])
    data7 = pack_7bit(data8)
    checksum = xor_all(data7)
    inner = bytes([0xF0, 0x01, seq & 0xFF, checksum, 0x02, 0x33]) + data7 + b"\xF7"
    return _build_header(len(inner)) + inner


def parse_mixer_value_response(data: bytes) -> float:
    """Parse a CMD 0x03/SUB_CMD 0x33 response to build_mixer_request_payload: just a
    float, no channel byte - unlike parse_mixer_notification's shape, the caller has
    to already know which channel it asked about (see BleBackend's in-flight queue).
    """
    value, _ = _read_float(data, 0)
    return value


def build_tap_tempo_payload(bpm: float, seq: int) -> bytes:
    """Send a computed tap-tempo BPM to sync tempo-based effects (CMD 0x01/SUB_CMD
    0x62). CONFIRMED on real Spark GO hardware, despite the source project itself
    flagging this sub-command with a "is this right??" comment and no code in that
    project actually calling it. `bpm` is a plain beats-per-minute float; the
    trailing `0x3F 0x3F` is a fixed/reserved suffix copied verbatim from the source,
    purpose still unknown but works as-is.
    """
    data8 = _build_float(bpm) + bytes([0x3F, 0x3F])
    data7 = pack_7bit(data8)
    checksum = xor_all(data7)
    inner = bytes([0xF0, 0x01, seq & 0xFF, checksum, 0x01, 0x62]) + data7 + b"\xF7"
    return _build_header(len(inner)) + inner


def parse_tuner_frame(data: bytes):
    """Parse a tuner notification frame (CMD 0x03/SUB_CMD 0x64). Returns None if this
    isn't a tuner data frame (e.g. it's an ack for some other command), otherwise a
    dict with the (rough, uncalibrated) fields - see PROTOCOL.md for the byte layout.
    """
    if len(data) != 14 or data[0] != 0xF0 or data[1] != 0x01:
        return None
    if data[4] != 0x03 or data[5] != 0x64:
        return None
    note = data[7]
    hi = data[9] & 0x7F
    lo = data[10] & 0x7F
    idle = data[6] == 0x0E and hi == 0x3F and data[10] == 0 and data[11] == 0 and data[12] == 0
    counter = (hi << 7) | lo
    cents = ((counter - TUNER_CENTER) / TUNER_HALF_RANGE) * 50
    return {
        "idle": idle,
        "note": note,
        "note_name": NOTE_NAMES[note] if 0 <= note < len(NOTE_NAMES) else "?",
        "counter": counter,
        "cents": cents,
    }
