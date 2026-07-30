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
    build_patch_payload,
    build_tuner_start_payload,
    build_tuner_stop_payload,
)


class BleBackend:
    def __init__(self, ui_queue: queue.Queue):
        self.ui_queue = ui_queue
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.client = None
        self.seq = DEFAULT_SEQ
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
        try:
            await self.disconnect(silent=True)
            self.emit("status", i18n.t("status_connecting", name=name))
            client = BleakClient(address)
            await client.connect(timeout=15.0)
            if not client.is_connected:
                raise RuntimeError(i18n.t("error_connection_failed"))

            def notification_handler(sender, data: bytearray):
                self.emit("rx", bytes(data))

            await client.start_notify(NOTIFY_HANDLE, notification_handler)
            self.client = client
            self.seq = DEFAULT_SEQ
            self.emit("status", i18n.t("status_connected", name=name))
        except Exception as e:
            self.emit("error", i18n.t("error_connection", type=type(e).__name__, error=e))

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
