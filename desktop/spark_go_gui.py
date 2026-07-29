import queue
import tkinter as tk
from tkinter import messagebox, ttk

import i18n
from ble_backend import BleBackend
from protocol import fmt_hex

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
