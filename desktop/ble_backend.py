"""Async BLE I/O, decoupled from the Tkinter UI.

Runs its own event loop on a background thread and reports everything back
to the caller via a queue (`kind`, `data`) tuples - never touches `tkinter`
directly. See HANDOFF.md for why that separation matters.
"""

import asyncio
import queue
import threading

from bleak import BleakClient, BleakScanner

import i18n
from protocol import (
    DEFAULT_SEQ,
    NOTIFY_HANDLE,
    WRITE_HANDLE,
    build_effect_toggle_payload,
    build_mixer_payload,
    build_mixer_request_payload,
    build_patch_payload,
    build_preset_request_payload,
    build_state_request_payload,
    build_tap_tempo_payload,
    build_tuner_start_payload,
    build_tuner_stop_payload,
    parse_active_patch_notification,
    parse_effect_state_notification,
    parse_mixer_notification,
    parse_mixer_value_response,
    parse_preset_data,
    unpack_7bit,
)


class BleBackend:
    def __init__(self, ui_queue: queue.Queue):
        self.ui_queue = ui_queue
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.client = None
        self.seq = DEFAULT_SEQ
        self._rx_stream = bytearray()
        self._preset_accum = bytearray()
        self._preset_seq_in_flight = None
        self._preset_purpose = "chain"
        self._preset_done_event = None
        self._active_patch_done_event = None
        self._active_patch_result = None
        self._mixer_channels_pending = []
        self.thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def call(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def emit(self, kind, data):
        self.ui_queue.put((kind, data))

    async def scan(self, name_filter: str):
        self.emit("status", i18n.t("status_scanning"))
        devices = await BleakScanner.discover(timeout=5.0, return_adv=True)
        rows = []
        for _, item in devices.items():
            device, adv = item
            name = device.name or adv.local_name or "(unnamed)"
            if name_filter and name_filter.lower() not in name.lower():
                continue
            rows.append((name, device.address, adv.rssi if adv.rssi is not None else ""))
        rows.sort(key=lambda x: (x[0].lower(), x[1]))
        self.emit("devices", rows)
        self.emit("status", i18n.t("status_scan_completed", count=len(rows)))

    async def connect(self, address: str, name: str):
        connected_ok = False
        try:
            await self.disconnect(silent=True)
            self.emit("status", i18n.t("status_connecting", name=name))
            client = BleakClient(address)
            await client.connect(timeout=15.0)
            if not client.is_connected:
                raise RuntimeError(i18n.t("error_connection_failed"))

            def notification_handler(sender, data: bytearray):
                raw = bytes(data)
                self.emit("rx", raw)
                self._handle_notification_bytes(raw)

            self._rx_stream = bytearray()
            self._preset_accum = bytearray()
            self._preset_seq_in_flight = None
            self._preset_done_event = None
            self._active_patch_done_event = None
            self._active_patch_result = None
            self._mixer_channels_pending = []
            await client.start_notify(NOTIFY_HANDLE, notification_handler)
            self.client = client
            self.seq = DEFAULT_SEQ
            self.emit("status", i18n.t("status_connected", name=name))
            connected_ok = True
        except Exception as e:
            self.emit("error", i18n.t("error_connection", type=type(e).__name__, error=e))

        if connected_ok:
            # Find out which patch is really active (CMD 0x02/SUB_CMD 0x10) instead of
            # guessing/defaulting, then read its full chain. A short pause first lets
            # the BLE notification subscription fully settle; failure here must not be
            # reported as a connection error - we ARE connected either way.
            await asyncio.sleep(0.3)
            active_num = None
            try:
                active_num = await self._request_active_patch_and_wait()
            except Exception as e:
                self.emit("error", i18n.t("error_active_patch_query", type=type(e).__name__, error=e))

            if active_num is not None:
                try:
                    await self._read_preset_and_wait(active_num, "chain")
                except Exception as e:
                    self.emit("error", i18n.t("error_request_preset_failed", n=active_num, type=type(e).__name__, error=e))

            # Read the other 3 patches too - just for their names (shown under the
            # patch buttons), not the full chain. One at a time: the multi-chunk
            # reassembly state (_preset_accum/_preset_seq_in_flight) only tracks a
            # single in-flight preset read, so a second request before the first
            # finishes would silently lose whichever one's response arrives second.
            await self.read_all_patch_names(skip=active_num)

            # Reading the current Guitar volume on connect (CMD 0x02/SUB_CMD 0x33) is
            # disabled for now - confirmed on real hardware to never get a response
            # (TX-only, no RX ever, for both mixer channels). Left here commented out
            # rather than deleted in case a future sniff of the official app finds the
            # real request shape; request_mixer_value/parse_mixer_value_response are
            # still defined and ready to use. The Guitar slider instead picks up the
            # live value passively, the moment the physical rotary encoder is turned
            # (the amp does broadcast that unsolicited - see PROTOCOL.md).
            # for channel in (MIXER_CHANNEL_GUITAR,):
            #     try:
            #         await self.request_mixer_value(channel)
            #     except Exception:
            #         pass

    def _handle_notification_bytes(self, raw: bytes):
        """BLE notifications don't align to message boundaries - a single logical
        F0 01 ... F7 chunk can span several separate notification packets, so bytes
        are accumulated across calls and split on F7 here."""
        self._rx_stream += raw
        while True:
            idx = self._rx_stream.find(b"\xF7")
            if idx == -1:
                break
            chunk = bytes(self._rx_stream[:idx + 1])
            del self._rx_stream[:idx + 1]
            self._process_chunk(chunk)

    def _process_chunk(self, chunk: bytes):
        start = chunk.find(b"\xF0\x01")
        if start == -1 or len(chunk) - start < 7:
            return
        chunk = chunk[start:]
        seq, cmd, sub_cmd = chunk[2], chunk[4], chunk[5]
        try:
            data8 = unpack_7bit(chunk[6:-1])
        except Exception:
            return
        # CMD 0x03 (and, per the source library this was ported from, also 0x01) with
        # SUB_CMD 0x01 is a multi-chunk preset dump: data8[0]=num_chunks, data8[1]=this
        # chunk's index, data8[2]=chunk_len, data8[3:]=this chunk's slice of the payload.
        if cmd in (0x01, 0x03) and sub_cmd == 0x01 and len(data8) >= 3:
            if seq != self._preset_seq_in_flight:
                # Belongs to a request we're no longer waiting on (a stale/aborted
                # read, or one superseded by a newer one) - accumulating it anyway
                # would corrupt the current reassembly with a foreign response.
                return
            num_chunks, this_chunk = data8[0], data8[1]
            self._preset_accum += data8[3:]
            if this_chunk >= num_chunks - 1:
                accum, self._preset_accum = bytes(self._preset_accum), bytearray()
                self._preset_seq_in_flight = None
                purpose = self._preset_purpose
                try:
                    parsed = parse_preset_data(accum)
                    # Every successful read updates that patch's name label,
                    # regardless of why it was requested; only a "chain" read (the
                    # active patch, or after a manual patch change) also repopulates
                    # the full pedal-chain panel.
                    self.emit("patch_name", {"n": parsed["preset_num"], "name": parsed["name"]})
                    if purpose == "chain":
                        self.emit("preset", parsed)
                except Exception as e:
                    self.emit("error", i18n.t("error_preset_parse", type=type(e).__name__, error=e))
                finally:
                    if self._preset_done_event is not None:
                        self._preset_done_event.set()
        # CMD 0x03/SUB_CMD 0x15 (single message, not multi-chunk) is the device
        # confirming an effect's new live on/off state - see parse_effect_state_notification.
        elif cmd == 0x03 and sub_cmd == 0x15 and len(data8) >= 2:
            try:
                self.emit("effect_state", parse_effect_state_notification(data8))
            except Exception:
                pass
        elif cmd == 0x03 and sub_cmd == 0x10 and len(data8) >= 2:
            try:
                self._active_patch_result = parse_active_patch_notification(data8)
            except Exception:
                self._active_patch_result = None
            if self._active_patch_done_event is not None:
                self._active_patch_done_event.set()
        # CMD 0x03/SUB_CMD 0x33 with just a bare float (5 bytes: 0xCA + 4) would be a
        # response to request_mixer_value's CMD 0x02/SUB_CMD 0x33 - confirmed on real
        # hardware that the Spark GO never actually sends this (see
        # build_mixer_request_payload, currently unused). Kept here in case that
        # changes; no channel byte in the response, so match it against whichever
        # channel we asked about first (FIFO, same assumption as a single BLE link
        # delivering notifications in the order requests were sent).
        elif cmd == 0x03 and sub_cmd == 0x33 and len(data8) == 5 and self._mixer_channels_pending:
            channel = self._mixer_channels_pending.pop(0)
            try:
                self.emit("mixer", {"channel": channel, "value": parse_mixer_value_response(data8)})
            except Exception:
                pass
        # CMD 0x01 or 0x03/SUB_CMD 0x33 with channel+value (6 bytes) is the confirmed
        # mixer-change shape (see protocol.py's build_mixer_payload and PROTOCOL.md) -
        # either our own optimistic echo or the amp reporting a physical
        # button/encoder change unsolicited.
        elif cmd in (0x01, 0x03) and sub_cmd == 0x33 and len(data8) == 6:
            try:
                self.emit("mixer", parse_mixer_notification(data8))
            except Exception:
                pass

    async def disconnect(self, silent=False):
        if self.client:
            try:
                try:
                    await self.client.stop_notify(NOTIFY_HANDLE)
                except Exception:
                    pass
                await self.client.disconnect()
            finally:
                self.client = None
                if not silent:
                    self.emit("status", i18n.t("status_disconnected"))

    async def send_patch(self, patch_number: int):
        if not self.client or not self.client.is_connected:
            raise RuntimeError(i18n.t("error_not_connected"))
        payload = build_patch_payload(patch_number, self.seq)
        self.seq = (self.seq + 1) & 0xFF
        await self.client.write_gatt_char(WRITE_HANDLE, payload, response=False)
        self.emit("tx", payload)
        # The patch-change command doesn't itself confirm the switch happened, and
        # requesting the read too soon can race with the device still applying it
        # (returning the previous patch's data). A short settle pause first, then an
        # accurate read of that exact patch - unlike the unreliable "which patch is
        # active" guess connect() deliberately doesn't make.
        await asyncio.sleep(0.3)
        await self._read_preset_and_wait(patch_number - 1, "chain")

    async def request_preset(self, preset_num: int, purpose: str = "chain"):
        if not self.client or not self.client.is_connected:
            raise RuntimeError(i18n.t("error_not_connected"))
        payload = build_preset_request_payload(preset_num, self.seq)
        self._preset_seq_in_flight = self.seq
        self._preset_accum = bytearray()
        self._preset_purpose = purpose
        self.seq = (self.seq + 1) & 0xFF
        await self.client.write_gatt_char(WRITE_HANDLE, payload, response=False)
        self.emit("tx", payload)

    async def _read_preset_and_wait(self, preset_num: int, purpose: str, timeout: float = 2.0):
        """Like request_preset, but waits (with a timeout) for that exact read to
        finish before returning - used wherever more than one preset might otherwise
        be requested back to back, since only one can be reassembled at a time."""
        self._preset_done_event = asyncio.Event()
        await self.request_preset(preset_num, purpose)
        try:
            await asyncio.wait_for(self._preset_done_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
        self._preset_done_event = None

    async def read_all_patch_names(self, skip: int = None):
        """Read all 4 saved patches just to grab their names (see _process_chunk's
        "patch_name" emit) for display under the patch buttons. `skip` is the active
        patch's number, already read in full via _read_preset_and_wait(..., "chain")
        - no need to read it again."""
        for preset_num in range(4):
            if preset_num == skip:
                continue
            try:
                await self._read_preset_and_wait(preset_num, "name")
            except Exception as e:
                self.emit("error", i18n.t("error_patch_name_failed", n=preset_num + 1, type=type(e).__name__, error=e))

    async def request_active_patch(self):
        if not self.client or not self.client.is_connected:
            raise RuntimeError(i18n.t("error_not_connected"))
        payload = build_state_request_payload(self.seq)
        self.seq = (self.seq + 1) & 0xFF
        await self.client.write_gatt_char(WRITE_HANDLE, payload, response=False)
        self.emit("tx", payload)

    async def _request_active_patch_and_wait(self, timeout: float = 2.0):
        self._active_patch_done_event = asyncio.Event()
        self._active_patch_result = None
        await self.request_active_patch()
        try:
            await asyncio.wait_for(self._active_patch_done_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
        result = self._active_patch_result
        self._active_patch_done_event = None
        return result

    async def toggle_effect(self, internal_name: str, on: bool):
        if not self.client or not self.client.is_connected:
            raise RuntimeError(i18n.t("error_not_connected"))
        payload = build_effect_toggle_payload(internal_name, on, self.seq)
        self.seq = (self.seq + 1) & 0xFF
        await self.client.write_gatt_char(WRITE_HANDLE, payload, response=False)
        self.emit("tx", payload)
        # No need to re-read the preset afterward: the device sends its own real-time
        # confirmation (CMD 0x03/SUB_CMD 0x15) of the new live state, handled in
        # _process_chunk/parse_effect_state_notification. Re-reading the saved preset
        # instead would be actively wrong here - toggling doesn't rewrite what's
        # stored for the patch, so that read would just show the pre-toggle value.

    async def tuner_start(self):
        if not self.client or not self.client.is_connected:
            raise RuntimeError(i18n.t("error_not_connected"))
        payload = build_tuner_start_payload(self.seq)
        self.seq = (self.seq + 1) & 0xFF
        await self.client.write_gatt_char(WRITE_HANDLE, payload, response=False)
        self.emit("tx", payload)

    async def tuner_stop(self):
        if not self.client or not self.client.is_connected:
            raise RuntimeError(i18n.t("error_not_connected"))
        payload = build_tuner_stop_payload(self.seq)
        self.seq = (self.seq + 1) & 0xFF
        await self.client.write_gatt_char(WRITE_HANDLE, payload, response=False)
        self.emit("tx", payload)

    async def set_mixer_volume(self, channel: int, value: float):
        if not self.client or not self.client.is_connected:
            raise RuntimeError(i18n.t("error_not_connected"))
        payload = build_mixer_payload(channel, value, self.seq)
        self.seq = (self.seq + 1) & 0xFF
        await self.client.write_gatt_char(WRITE_HANDLE, payload, response=False)
        self.emit("tx", payload)

    async def request_mixer_value(self, channel: int):
        if not self.client or not self.client.is_connected:
            raise RuntimeError(i18n.t("error_not_connected"))
        payload = build_mixer_request_payload(channel, self.seq)
        self._mixer_channels_pending.append(channel)
        self.seq = (self.seq + 1) & 0xFF
        await self.client.write_gatt_char(WRITE_HANDLE, payload, response=False)
        self.emit("tx", payload)

    async def send_tap_tempo(self, bpm: float):
        if not self.client or not self.client.is_connected:
            raise RuntimeError(i18n.t("error_not_connected"))
        payload = build_tap_tempo_payload(bpm, self.seq)
        self.seq = (self.seq + 1) & 0xFF
        await self.client.write_gatt_char(WRITE_HANDLE, payload, response=False)
        self.emit("tx", payload)
