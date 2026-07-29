import asyncio
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox
from bleak import BleakScanner, BleakClient

# =========================
# App config
# =========================
APP_TITLE = "Spark GO GUI"
DEFAULT_NAME_FILTER = "Spark"
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


# =========================
# BLE backend
# =========================
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
        self.emit("status", "Scanning...")
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
        self.emit("status", f"Scan completed: {len(rows)} device(s)")

    async def connect(self, address: str, name: str):
        try:
            await self.disconnect(silent=True)
            self.emit("status", f"Connecting to {name}...")
            client = BleakClient(address)
            await client.connect(timeout=15.0)
            if not client.is_connected:
                raise RuntimeError("Connection failed")

            def notification_handler(sender, data: bytearray):
                self.emit("rx", bytes(data))

            await client.start_notify(NOTIFY_HANDLE, notification_handler)
            self.client = client
            self.seq = DEFAULT_SEQ
            self.emit("status", f"Connected to {name}")
        except Exception as e:
            self.emit("error", f"Connection error: {type(e).__name__}: {e}")

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
                    self.emit("status", "Disconnected")

    async def send_patch(self, patch_number: int):
        if not self.client or not self.client.is_connected:
            raise RuntimeError("Not connected")
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
        self.root.title(APP_TITLE)
        self.root.geometry("760x560")
        self.ui_queue = queue.Queue()
        self.backend = BleBackend(self.ui_queue)
        self._auto_connect_pending = True
        self._build_ui()
        self._poll_ui_queue()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(300, self.scan)

    def _build_ui(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="Name filter:").pack(side="left")
        self.name_filter = tk.StringVar(value=DEFAULT_NAME_FILTER)
        ttk.Entry(top, textvariable=self.name_filter, width=18).pack(side="left", padx=5)
        ttk.Button(top, text="Scan", command=self.scan).pack(side="left", padx=5)
        ttk.Button(top, text="Connect", command=self.connect_selected).pack(side="left", padx=5)
        ttk.Button(top, text="Disconnect", command=self.disconnect).pack(side="left", padx=5)

        self.tree = ttk.Treeview(self.root, columns=("name", "address", "rssi"), show="headings", height=8)
        for col, width in (("name", 220), ("address", 420), ("rssi", 80)):
            self.tree.heading(col, text=col.upper())
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(fill="x", padx=10, pady=10)

        patch_frame = ttk.LabelFrame(self.root, text="Send patch", padding=10)
        patch_frame.pack(fill="x", padx=10, pady=6)
        for i in range(1, 5):
            ttk.Button(
                patch_frame,
                text=f"Patch {i}",
                command=lambda n=i: self.send_patch(n),
            ).pack(side="left", padx=6, pady=4, expand=True, fill="x")

        self.log_toggle_btn = ttk.Button(self.root, text="▸ Show log", command=self.toggle_log)
        self.log_toggle_btn.pack(anchor="w", padx=10, pady=(0, 4))

        self.log_frame = ttk.Frame(self.root)
        self.log_text = tk.Text(self.log_frame, height=16, wrap="word")
        self.log_text.pack(fill="both", expand=True)
        # Not packed here on purpose - the log starts hidden, see toggle_log.

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self.root, textvariable=self.status_var, relief="sunken", anchor="w").pack(fill="x", side="bottom")

    def scan(self):
        self.backend.call(self.backend.scan(self.name_filter.get().strip()))

    def connect_selected(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning(APP_TITLE, "Select a device first.")
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
                self.ui_queue.put(("error", f"Send patch {patch_number} failed: {type(e).__name__}: {e}"))

        future.add_done_callback(done_callback)

    def toggle_log(self):
        if self.log_frame.winfo_ismapped():
            self.log_frame.pack_forget()
            self.log_toggle_btn.config(text="▸ Show log")
        else:
            self.log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
            self.log_toggle_btn.config(text="▾ Hide log")

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
                    if len(data) == 1:
                        first_item = self.tree.get_children()[0]
                        self.tree.selection_set(first_item)
                    if self._auto_connect_pending:
                        self._auto_connect_pending = False
                        if len(data) == 1:
                            self.connect_selected()
                elif kind == "status":
                    self.status_var.set(data)
                elif kind == "error":
                    self.status_var.set(data)
                    self.log(f"ERROR: {data}")
                elif kind == "tx":
                    self.log(f"TX: {fmt_hex(data)}")
                elif kind == "rx":
                    self.log(f"RX: {fmt_hex(data)}")
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
