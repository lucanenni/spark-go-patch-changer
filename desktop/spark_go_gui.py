import queue
import tkinter as tk
from tkinter import messagebox, ttk

import i18n
from ble_backend import BleBackend
from protocol import fmt_hex, parse_tuner_frame

DEFAULT_NAME_FILTER = "Spark"


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(i18n.t("app_title"))
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

        self.name_filter_label = ttk.Label(top, text=i18n.t("label_name_filter"))
        self.name_filter_label.pack(side="left")
        self.name_filter = tk.StringVar(value=DEFAULT_NAME_FILTER)
        ttk.Entry(top, textvariable=self.name_filter, width=18).pack(side="left", padx=5)
        self.btn_scan = ttk.Button(top, text=i18n.t("btn_scan"), command=self.scan)
        self.btn_scan.pack(side="left", padx=5)
        self.btn_connect = ttk.Button(top, text=i18n.t("btn_connect"), command=self.connect_selected)
        self.btn_connect.pack(side="left", padx=5)
        self.btn_disconnect = ttk.Button(top, text=i18n.t("btn_disconnect"), command=self.disconnect)
        self.btn_disconnect.pack(side="left", padx=5)

        self.lang_label = ttk.Label(top, text=i18n.t("label_language"))
        self.lang_label.pack(side="left", padx=(15, 0))
        self._lang_codes = [code for code, _ in i18n.LANGUAGES]
        self.lang_var = tk.StringVar(value=self._lang_display(i18n.get_language()))
        self.lang_combo = ttk.Combobox(
            top,
            textvariable=self.lang_var,
            values=[name for _, name in i18n.LANGUAGES],
            state="readonly",
            width=10,
        )
        self.lang_combo.pack(side="left", padx=5)
        self.lang_combo.bind("<<ComboboxSelected>>", self.on_language_change)

        self.tree = ttk.Treeview(self.root, columns=("name", "address", "rssi"), show="headings", height=8)
        for col, width in (("name", 220), ("address", 420), ("rssi", 80)):
            self.tree.heading(col, text=col.upper())
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(fill="x", padx=10, pady=10)

        self.patch_frame = ttk.LabelFrame(self.root, text=i18n.t("panel_send_patch"), padding=10)
        self.patch_frame.pack(fill="x", padx=10, pady=6)
        self.patch_buttons = []
        for i in range(1, 5):
            btn = ttk.Button(
                self.patch_frame,
                text=i18n.t("patch_button", n=i),
                command=lambda n=i: self.send_patch(n),
            )
            btn.pack(side="left", padx=6, pady=4, expand=True, fill="x")
            self.patch_buttons.append(btn)

        self.tuner_frame = ttk.LabelFrame(self.root, text=i18n.t("panel_tuner"), padding=10)
        self.tuner_frame.pack(fill="x", padx=10, pady=6)
        self.btn_tuner_on = ttk.Button(self.tuner_frame, text=i18n.t("btn_tuner_on"), command=self.tuner_start)
        self.btn_tuner_on.pack(side="left", padx=6, expand=True, fill="x")
        self.btn_tuner_off = ttk.Button(self.tuner_frame, text=i18n.t("btn_tuner_off"), command=self.tuner_stop)
        self.btn_tuner_off.pack(side="left", padx=6, expand=True, fill="x")

        self.tuner_display_frame = ttk.LabelFrame(self.root, text=i18n.t("panel_tuner_display"), padding=10)
        self.tuner_display_frame.pack(fill="x", padx=10, pady=6)
        tuner_row = ttk.Frame(self.tuner_display_frame)
        tuner_row.pack(fill="x")
        self.tuner_note_var = tk.StringVar(value="—")
        ttk.Label(tuner_row, textvariable=self.tuner_note_var, font=("TkDefaultFont", 28, "bold"), width=4, anchor="center").pack(side="left")
        gauge_frame = ttk.Frame(tuner_row)
        gauge_frame.pack(side="left", fill="x", expand=True, padx=(10, 0))
        self.tuner_bar_height = 16
        self.tuner_canvas_width = 400  # overwritten on first <Configure> event
        self._tuner_last_cents = None
        self.tuner_canvas = tk.Canvas(gauge_frame, height=self.tuner_bar_height + 20, bg="#1e2025", highlightthickness=0)
        self.tuner_canvas.pack(fill="x")
        self.tuner_canvas.bind("<Configure>", self._on_tuner_canvas_resize)
        self.tuner_raw_var = tk.StringVar(value=i18n.t("tuner_no_signal"))
        ttk.Label(self.tuner_display_frame, textvariable=self.tuner_raw_var).pack(anchor="w", pady=(4, 0))

        self.log_toggle_btn = ttk.Button(self.root, text=i18n.t("log_show"), command=self.toggle_log)
        self.log_toggle_btn.pack(anchor="w", padx=10, pady=(0, 4))

        self.log_frame = ttk.Frame(self.root)
        self.log_text = tk.Text(self.log_frame, height=16, wrap="word")
        self.log_text.pack(fill="both", expand=True)
        # Not packed here on purpose - the log starts hidden, see toggle_log.

        self.status_var = tk.StringVar(value=i18n.t("status_ready"))
        ttk.Label(self.root, textvariable=self.status_var, relief="sunken", anchor="w").pack(fill="x", side="bottom")

    def _lang_display(self, code: str) -> str:
        for lang_code, name in i18n.LANGUAGES:
            if lang_code == code:
                return name
        return code

    def on_language_change(self, event=None):
        index = self.lang_combo.current()
        if index < 0:
            return
        i18n.set_language(self._lang_codes[index])
        self._retranslate_ui()

    def _retranslate_ui(self):
        self.root.title(i18n.t("app_title"))
        self.name_filter_label.config(text=i18n.t("label_name_filter"))
        self.btn_scan.config(text=i18n.t("btn_scan"))
        self.btn_connect.config(text=i18n.t("btn_connect"))
        self.btn_disconnect.config(text=i18n.t("btn_disconnect"))
        self.lang_label.config(text=i18n.t("label_language"))
        self.patch_frame.config(text=i18n.t("panel_send_patch"))
        for i, btn in enumerate(self.patch_buttons, start=1):
            btn.config(text=i18n.t("patch_button", n=i))
        self.tuner_frame.config(text=i18n.t("panel_tuner"))
        self.btn_tuner_on.config(text=i18n.t("btn_tuner_on"))
        self.btn_tuner_off.config(text=i18n.t("btn_tuner_off"))
        self.tuner_display_frame.config(text=i18n.t("panel_tuner_display"))
        if self._tuner_last_cents is None:
            self.tuner_raw_var.set(i18n.t("tuner_no_signal"))
        is_shown = self.log_frame.winfo_ismapped()
        self.log_toggle_btn.config(text=i18n.t("log_hide") if is_shown else i18n.t("log_show"))

    def scan(self):
        self.backend.call(self.backend.scan(self.name_filter.get().strip()))

    def connect_selected(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning(i18n.t("app_title"), i18n.t("warn_select_device"))
            return
        values = self.tree.item(selection[0], "values")
        self.backend.call(self.backend.connect(values[1], values[0]))

    def disconnect(self):
        self.backend.call(self.backend.disconnect())
        self.reset_tuner_display()

    def send_patch(self, patch_number: int):
        future = self.backend.call(self.backend.send_patch(patch_number))

        def done_callback(f):
            try:
                f.result()
            except Exception as e:
                self.ui_queue.put((
                    "error",
                    i18n.t("error_send_patch_failed", n=patch_number, type=type(e).__name__, error=e),
                ))

        future.add_done_callback(done_callback)

    def tuner_start(self):
        future = self.backend.call(self.backend.tuner_start())

        def done_callback(f):
            try:
                f.result()
            except Exception as e:
                self.ui_queue.put((
                    "error",
                    i18n.t("error_tuner_start_failed", type=type(e).__name__, error=e),
                ))

        future.add_done_callback(done_callback)

    def tuner_stop(self):
        future = self.backend.call(self.backend.tuner_stop())

        def done_callback(f):
            try:
                f.result()
            except Exception as e:
                self.ui_queue.put((
                    "error",
                    i18n.t("error_tuner_stop_failed", type=type(e).__name__, error=e),
                ))

        future.add_done_callback(done_callback)
        self.reset_tuner_display()

    def _on_tuner_canvas_resize(self, event):
        self.tuner_canvas_width = event.width
        self._redraw_tuner_gauge()

    def _redraw_tuner_gauge(self):
        self.tuner_canvas.delete("all")
        w = self.tuner_canvas_width
        h = self.tuner_bar_height
        center = w / 2

        # Subtle "in tune" zone (+-5 cents on the provisional scale).
        zone_half = (5 / 50) * (w / 2)
        self.tuner_canvas.create_rectangle(
            center - zone_half, 0, center + zone_half, h, fill="#1f2e2b", width=0
        )
        self.tuner_canvas.create_rectangle(0, 0, w, h, outline="#34363d", width=1)

        for c in (-50, -25, 0, 25, 50):
            x = center + (c / 50) * (w / 2)
            self.tuner_canvas.create_line(x, 0, x, h, fill="#34363d")
            self.tuner_canvas.create_text(x, h + 10, text=str(c), fill="#8b909b", font=("TkDefaultFont", 8))

        self.tuner_needle = self.tuner_canvas.create_rectangle(
            center - 1.5, 0, center + 2.5, h, fill="#4fd1c5", width=0
        )
        if self._tuner_last_cents is not None:
            self._position_needle(self._tuner_last_cents)

    def _position_needle(self, cents):
        self._tuner_last_cents = cents
        clamped = max(-50.0, min(50.0, cents))
        w = self.tuner_canvas_width
        h = self.tuner_bar_height
        left_px = w / 2 + (clamped / 50.0) * (w / 2)
        self.tuner_canvas.coords(self.tuner_needle, left_px - 1.5, 0, left_px + 2.5, h)
        fill = "#6fcf7a" if abs(clamped) <= 5 else "#4fd1c5"
        self.tuner_canvas.itemconfig(self.tuner_needle, fill=fill)

    def reset_tuner_display(self):
        self.tuner_note_var.set("—")
        self.tuner_raw_var.set(i18n.t("tuner_no_signal"))
        self._tuner_last_cents = None
        center = self.tuner_canvas_width / 2
        self.tuner_canvas.coords(self.tuner_needle, center - 1.5, 0, center + 2.5, self.tuner_bar_height)
        self.tuner_canvas.itemconfig(self.tuner_needle, fill="#4fd1c5")

    def update_tuner_display(self, raw: bytes):
        parsed = parse_tuner_frame(raw)
        if not parsed:
            return  # Not a tuner data frame (e.g. an ack for some other command).
        if parsed["idle"]:
            self.reset_tuner_display()
            return
        self.tuner_note_var.set(parsed["note_name"])
        self.tuner_raw_var.set(i18n.t("tuner_raw", cents=parsed["cents"], counter=parsed["counter"]))
        self._position_needle(parsed["cents"])

    def toggle_log(self):
        if self.log_frame.winfo_ismapped():
            self.log_frame.pack_forget()
            self.log_toggle_btn.config(text=i18n.t("log_show"))
        else:
            self.log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
            self.log_toggle_btn.config(text=i18n.t("log_hide"))

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
                    self.log(i18n.t("log_error", message=data))
                elif kind == "tx":
                    self.log(i18n.t("log_tx", hex=fmt_hex(data)))
                elif kind == "rx":
                    self.log(i18n.t("log_rx", hex=fmt_hex(data)))
                    self.update_tuner_display(data)
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


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
