"""Spark GO BLE wire protocol: GATT handles and message building.

See PROTOCOL.md for the full reverse-engineered protocol reference.
"""

NOTIFY_HANDLE = 0x0007
WRITE_HANDLE = 0x000A

PRESET_HEADER = bytes.fromhex("01 FE 00 00 53 FE 1A 00 00 00 00 00 00 00 00 00")
DEFAULT_SEQ = 0x20


def fmt_hex(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def build_patch_payload(patch_number: int, seq: int) -> bytes:
    if patch_number not in (1, 2, 3, 4):
        raise ValueError("patch_number must be 1..4")
    patch_id = patch_number - 1
    inner = bytes([0xF0, 0x01, seq & 0xFF, patch_id, 0x01, 0x38, 0x00, 0x00, patch_id, 0xF7])
    return PRESET_HEADER + inner
