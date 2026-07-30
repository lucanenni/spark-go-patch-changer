"""Spark GO BLE wire protocol: GATT handles and message building.

See PROTOCOL.md for the full reverse-engineered protocol reference.
"""

NOTIFY_HANDLE = 0x0007
WRITE_HANDLE = 0x000A

PRESET_HEADER = bytes.fromhex("01 FE 00 00 53 FE 1A 00 00 00 00 00 00 00 00 00")
TUNER_HEADER = bytes.fromhex("01 FE 00 00 53 FE 19 00 00 00 00 00 00 00 00 00")
DEFAULT_SEQ = 0x20

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
