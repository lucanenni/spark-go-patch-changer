import asyncio
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox
from bleak import BleakScanner, BleakClient

# =========================
# App config and i18n
# =========================
APP_TITLE = "Spark GO patch changer"
DEFAULT_NAME_FILTER = "Spark"
NOTIFY_HANDLE = 0x0007
WRITE_HANDLE = 0x000A
PRESET_HEADER = bytes.fromhex("01 FE 00 00 53 FE 1A 00 00 00 00 00 00 00 00 00")

EN_STRINGS = {
    "app_title": "Spark GO patch changer",
    "name_filter": "Name filter:",
    "scan": "Scan",
    "connect": "Connect",
    "disconnect": "Disconnect",
    "disconnected": "Disconnected",
    "scan_in_progress": "BLE scan in progress...",
    "scan_done": "Scan completed: {count} device(s)",
    "connecting": "Connecting to {name}...",
    "connected": "Connected to {name} | notify=0x{notify:04X} | write=0x{write:04X}",
    "connection_failed": "Connection failed",
    "status_ready": "Ready",
    "status_connected": "Connected",
    "status_disconnected": "Disconnected",
    "status_error": "Error",
    "select_device": "Select a device first.",
    "patches": "Send patch",
    "patch": "Patch {n}",
    "log": "Log",
    "error_connect": "Connection error: {err}",
    "error_send_patch": "Send patch {n} failed: {err}",
    "not_connected": "Not connected",
    "tx": "TX",
    "rx": "RX",
    "unnamed": "(unnamed)",
}

STRINGS = EN_STRINGS


def tr(key, **kwargs):
    return STRINGS[key].format(**kwargs)


# =========================
# Protocol helpers
# =========================
def fmt_hex(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def build_patch_payload(patch_number: int, seq: int) -> bytes:
    if patch_number not in (1, 2, 3, 4):
        raise ValueError("patch_number must be 1..4")
    patch_id = patch_number - 1
    inner = bytes([0xF0, 0x01, seq & 0xFF, patch_id, 0x01, 0x38, 0x00, 0x00, patch_id, 0xF7])
    return PRESET_HEADER + inner


# =========================
# BLE backend
# =========================
class BleBackend:
    def __init__(self, ui_queue: queue.Queue):
        self.ui_queue = ui_queue
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.client = None
        self.seq = 0x20
        self.thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def call(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def emit(self, kind, data):
        self.ui_queue.put((kind, data))

    async def scan(self, name_filter: str):
        self.emit("status", tr("scan_in_progress"))
        devices = await BleakScanner.discover(timeout=5.0, return_adv=True)
        rows = []
        for _, item in devices.items():
            device, adv = item
            name = device.name or adv.local_name or tr("unnamed")
            if name_filter and name_filter.lower() not in name.lower():
                continue
            rows.append((name, device.address, adv.rssi if adv.rssi is not None else ""))
        rows.sort(key=lambda x: (x[0].lower(), x[1]))
        self.emit("devices", rows)
        self.emit("status", tr("scan_done", count=len(rows)))

    async def connect(self, address: str, name: str):
        try:
            await self.disconnect(silent=True)
            self.emit("status", tr("connecting", name=name))
            client = BleakClient(address)
            await client.connect(timeout=15.0)
            if not client.is_connected:
                raise RuntimeError(tr("connection_failed"))

            def notification_handler(sender, data: bytearray):
                self.emit("rx", {"sender": sender, "raw": bytes(data)})

            await client.start_notify(NOTIFY_HANDLE, notification_handler)
            self.client = client
            self.emit("connection", tr("connected", name=name, notify=NOTIFY_HANDLE, write=WRITE_HANDLE))
            self.emit("status", tr("status_connected"))
        except Exception as e:
            self.emit("error", tr("error_connect", err=f"{type(e).__name__}: {e}"))
            self.emit("status", tr("status_error"))

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
                self.emit("connection", tr("disconnected"))
                if not silent:
                    self.emit("status", tr("status_disconnected"))

    async def send_patch(self, patch_number: int):
        if not self.client or not self.client.is_connected:
            raise RuntimeError(tr("not_connected"))
        payload = build_patch_payload(patch_number, self.seq)
        self.seq = (self.seq + 1) & 0xFF
        await self.client.write_gatt_char(WRITE_HANDLE, payload, response=False)
        self.emit("tx", payload)


# =========================
# GUI frontend
# =========================
class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(tr("app_title"))
        self.root.geometry("980x720")
        self.ui_queue = queue.Queue()
        self.backend = BleBackend(self.ui_queue)
        self._build_ui()
        self._poll_ui_queue()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text=tr("name_filter")).pack(side="left")
        self.name_filter = tk.StringVar(value=DEFAULT_NAME_FILTER)
        ttk.Entry(top, textvariable=self.name_filter, width=18).pack(side="left", padx=5)
        ttk.Button(top, text=tr("scan"), command=self.scan).pack(side="left", padx=5)
        ttk.Button(top, text=tr("connect"), command=self.connect_selected).pack(side="left", padx=5)
        ttk.Button(top, text=tr("disconnect"), command=self.disconnect).pack(side="left", padx=5)

        self.connection_var = tk.StringVar(value=tr("disconnected"))
        ttk.Label(self.root, textvariable=self.connection_var, padding=(10, 0)).pack(anchor="w")

        self.tree = ttk.Treeview(self.root, columns=("name", "address", "rssi"), show="headings", height=10)
        for col, width in (("name", 220), ("address", 520), ("rssi", 80)):
            self.tree.heading(col, text=col.upper())
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(fill="x", padx=10, pady=10)

        patch_frame = ttk.LabelFrame(self.root, text=tr("patches"), padding=10)
        patch_frame.pack(fill="x", padx=10, pady=6)
        for i in range(1, 5):
            ttk.Button(
                patch_frame,
                text=tr("patch", n=i),
                command=lambda n=i: self.send_patch(n),
            ).pack(side="left", padx=6, pady=4, expand=True, fill="x")

        ttk.Label(self.root, text=tr("log")).pack(anchor="w", padx=10)
        self.log_text = tk.Text(self.root, height=20, wrap="word")
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.status_var = tk.StringVar(value=tr("status_ready"))
        ttk.Label(self.root, textvariable=self.status_var, relief="sunken", anchor="w").pack(fill="x", side="bottom")

    def scan(self):
        self.backend.call(self.backend.scan(self.name_filter.get().strip()))

    def connect_selected(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning(tr("app_title"), tr("select_device"))
            return
        values = self.tree.item(selection[0], "values")
        self.backend.call(self.backend.connect(values[1], values[0]))

    def disconnect(self):
        self.backend.call(self.backend.disconnect())

    def send_patch(self, patch_number: int):
        future = self.backend.call(self.backend.send_patch(patch_number))

        def done_callback(f):
            try:
                f.result()
            except Exception as e:
                self.ui_queue.put(("error", tr("error_send_patch", n=patch_number, err=f"{type(e).__name__}: {e}")))

        future.add_done_callback(done_callback)

    def log(self, text: str):
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")

    def _poll_ui_queue(self):
        try:
            while True:
                kind, data = self.ui_queue.get_nowait()
                if kind == "devices":
                    for item in self.tree.get_children():
                        self.tree.delete(item)
                    for row in data:
                        self.tree.insert("", "end", values=row)
                elif kind == "connection":
                    self.connection_var.set(data)
                elif kind == "status":
                    self.status_var.set(data)
                elif kind == "error":
                    self.status_var.set(tr("status_error"))
                    self.log(data)
                elif kind == "tx":
                    self.log(f"{tr('tx')}: {fmt_hex(data)}")
                elif kind == "rx":
                    self.log(f"{tr('rx')} [{data['sender']}]: {fmt_hex(data['raw'])}")
        except queue.Empty:
            pass
        self.root.after(100, self._poll_ui_queue)

    def on_close(self):
        try:
            future = self.backend.call(self.backend.disconnect(silent=True))
            future.result(timeout=3)
        except Exception:
            pass
        self.root.destroy()


# =========================
# Entry point
# =========================
if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()