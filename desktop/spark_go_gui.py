import queue
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import i18n
from ble_backend import BleBackend
from protocol import MIXER_CHANNEL_GUITAR, SLOT_LABELS, fmt_hex, parse_tuner_frame

DEFAULT_NAME_FILTER = "Spark"
TAP_TEMPO_RESET_GAP = 2.0  # seconds - a tap after this long starts a fresh sequence
TAP_TEMPO_MAX_SAMPLES = 4
TAP_TEMPO_MIN_BPM = 30.0
TAP_TEMPO_MAX_BPM = 300.0


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(i18n.t("app_title"))
        # No fixed .geometry() here on purpose - let Tk size the window to fit its
        # actual content (driven by the left column's natural height). A hardcoded
        # size can end up shorter than the content once panels are added, pushing the
        # status bar out of view until the window is enlarged by hand.
        self.root.minsize(900, 600)
        self.ui_queue = queue.Queue()
        self.backend = BleBackend(self.ui_queue)
        self._auto_connect_pending = True
        self.last_preset = None
        self._tap_times = []
        self._build_ui()
        self._poll_ui_queue()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(300, self.scan)

    def _build_ui(self):
        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)

        right = ttk.Frame(body, width=380, padding=(0, 10, 10, 10))
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        top = ttk.Frame(left, padding=10)
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

        self.tree = ttk.Treeview(left, columns=("name", "address", "rssi"), show="headings", height=8)
        for col, width in (("name", 220), ("address", 420), ("rssi", 80)):
            self.tree.heading(col, text=col.upper())
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(fill="x", padx=10, pady=10)

        self.patch_frame = ttk.LabelFrame(left, text=i18n.t("panel_send_patch"), padding=10)
        self.patch_frame.pack(fill="x", padx=10, pady=6)
        self.patch_buttons = []
        self.patch_name_vars = []
        for i in range(1, 5):
            cell = ttk.Frame(self.patch_frame)
            cell.pack(side="left", padx=6, pady=4, expand=True, fill="x")
            btn = ttk.Button(
                cell,
                text=i18n.t("patch_button", n=i),
                command=lambda n=i: self.send_patch(n),
            )
            btn.pack(fill="x")
            name_var = tk.StringVar(value="—")
            ttk.Label(cell, textvariable=name_var, foreground="#8b909b", font=("TkDefaultFont", 8), anchor="center").pack(fill="x")
            self.patch_buttons.append(btn)
            self.patch_name_vars.append(name_var)

        self.tuner_frame = ttk.LabelFrame(left, text=i18n.t("panel_tuner"), padding=10)
        self.tuner_frame.pack(fill="x", padx=10, pady=6)
        self.btn_tuner_on = ttk.Button(self.tuner_frame, text=i18n.t("btn_tuner_on"), command=self.tuner_start)
        self.btn_tuner_on.pack(side="left", padx=6, expand=True, fill="x")
        self.btn_tuner_off = ttk.Button(self.tuner_frame, text=i18n.t("btn_tuner_off"), command=self.tuner_stop)
        self.btn_tuner_off.pack(side="left", padx=6, expand=True, fill="x")

        # Guitar volume - CONFIRMED working on real hardware (see PROTOCOL.md). Music
        # Volume was removed: its physical buttons turned out to be standard AVRCP
        # volume commands sent to the Bluetooth audio source (the phone), not
        # anything going through the Spark GO's own control protocol at all.
        self.mixer_frame = ttk.LabelFrame(left, text=i18n.t("panel_mixer"), padding=10)
        self.mixer_frame.pack(fill="x", padx=10, pady=6)

        guitar_row = ttk.Frame(self.mixer_frame)
        guitar_row.pack(fill="x")
        self.guitar_vol_var = tk.DoubleVar(value=0.5)
        guitar_scale = ttk.Scale(
            guitar_row, from_=0.0, to=1.0, orient="horizontal", variable=self.guitar_vol_var,
            command=lambda v: self.guitar_vol_pct.set(f"{float(v) * 100:.0f}%"),
        )
        guitar_scale.pack(side="left", fill="x", expand=True, padx=(0, 8))
        guitar_scale.bind("<Button-1>", self._on_mixer_scale_click)
        guitar_scale.bind(
            "<ButtonRelease-1>", lambda e: self.set_mixer_volume(MIXER_CHANNEL_GUITAR, self.guitar_vol_var.get())
        )
        self.guitar_vol_pct = tk.StringVar(value="50%")
        ttk.Label(guitar_row, textvariable=self.guitar_vol_pct, width=5).pack(side="left")

        self.tap_tempo_frame = ttk.LabelFrame(left, text=i18n.t("panel_tap_tempo"), padding=10)
        self.tap_tempo_frame.pack(fill="x", padx=10, pady=6)
        tap_row = ttk.Frame(self.tap_tempo_frame)
        tap_row.pack(fill="x")
        self.btn_tap_tempo = ttk.Button(tap_row, text=i18n.t("btn_tap"), command=self.tap_tempo)
        self.btn_tap_tempo.pack(side="left", padx=(0, 10))
        self.tap_tempo_var = tk.StringVar(value=i18n.t("tap_tempo_none"))
        ttk.Label(tap_row, textvariable=self.tap_tempo_var).pack(side="left")
        self.patch_bpm_var = tk.StringVar(value=i18n.t("patch_bpm_unknown"))
        ttk.Label(
            self.tap_tempo_frame, textvariable=self.patch_bpm_var, foreground="#8b909b", font=("TkDefaultFont", 8)
        ).pack(anchor="w", pady=(6, 0))

        self.tuner_display_frame = ttk.LabelFrame(left, text=i18n.t("panel_tuner_display"), padding=10)
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

        # Right column: pedal chain on top, status bar below it, log (toggle-collapsible) last.
        self.chain_frame = ttk.LabelFrame(right, text=i18n.t("panel_chain"), padding=10)
        self.chain_frame.pack(fill="x", pady=(0, 6))
        self.chain_preset_var = tk.StringVar(value=i18n.t("chain_none"))
        ttk.Label(self.chain_frame, textvariable=self.chain_preset_var, font=("TkDefaultFont", 10, "bold")).grid(
            row=0, column=0, columnspan=5, sticky="w", pady=(0, 6)
        )
        self.chain_headers = []
        for col, key in enumerate(("chain_header_slot", "chain_header_pedal", "chain_header_state", "", "chain_header_params")):
            label = ttk.Label(self.chain_frame, text=i18n.t(key) if key else "", foreground="#8b909b")
            label.grid(row=1, column=col, sticky="w", padx=(0, 10))
            self.chain_headers.append((label, key))
        self.chain_rows = []
        for i, slot_label in enumerate(SLOT_LABELS):
            r = i + 2
            ttk.Label(self.chain_frame, text=slot_label).grid(row=r, column=0, sticky="w", padx=(0, 10), pady=2)
            name_var = tk.StringVar(value="—")
            ttk.Label(self.chain_frame, textvariable=name_var).grid(row=r, column=1, sticky="w", padx=(0, 10))
            state_var = tk.StringVar(value="—")
            state_label = tk.Label(self.chain_frame, textvariable=state_var, width=4)
            state_label.grid(row=r, column=2, sticky="w", padx=(0, 10))
            toggle_btn = ttk.Button(
                self.chain_frame, text=i18n.t("chain_toggle"), state="disabled",
                command=lambda idx=i: self.toggle_chain_slot(idx),
            )
            toggle_btn.grid(row=r, column=3, sticky="w", padx=(0, 10))
            params_var = tk.StringVar(value="")
            ttk.Label(self.chain_frame, textvariable=params_var, foreground="#8b909b").grid(row=r, column=4, sticky="w")
            self.chain_rows.append({
                "name_var": name_var, "state_var": state_var, "state_label": state_label,
                "toggle_btn": toggle_btn, "params_var": params_var, "pedal": None,
            })

        self.status_var = tk.StringVar(value=i18n.t("status_ready"))
        self.status_label = ttk.Label(right, textvariable=self.status_var, relief="sunken", anchor="w")
        self.status_label.pack(fill="x", pady=(0, 6))

        log_header = ttk.Frame(right)
        log_header.pack(fill="x", pady=(0, 4))
        self.log_toggle_btn = ttk.Button(log_header, text=i18n.t("log_show"), command=self.toggle_log)
        self.log_toggle_btn.pack(side="left")
        self.btn_log_export = ttk.Button(log_header, text=i18n.t("log_export"), command=self.export_log)
        self.btn_log_export.pack(side="right")
        self.btn_log_clear = ttk.Button(log_header, text=i18n.t("log_clear"), command=self.clear_log)
        self.btn_log_clear.pack(side="right", padx=(0, 6))

        self.log_frame = ttk.Frame(right)
        log_scroll = ttk.Scrollbar(self.log_frame, orient="vertical")
        self.log_text = tk.Text(self.log_frame, wrap="word", yscrollcommand=log_scroll.set)
        log_scroll.config(command=self.log_text.yview)
        log_scroll.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)
        # Not packed here on purpose - the log starts hidden, see toggle_log.

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
        self.mixer_frame.config(text=i18n.t("panel_mixer"))
        self.tap_tempo_frame.config(text=i18n.t("panel_tap_tempo"))
        self.btn_tap_tempo.config(text=i18n.t("btn_tap"))
        if not self._tap_times:
            self.tap_tempo_var.set(i18n.t("tap_tempo_none"))
        if self.last_preset is None:
            self.patch_bpm_var.set(i18n.t("patch_bpm_unknown"))
        else:
            self.patch_bpm_var.set(i18n.t("patch_bpm_label", bpm=self.last_preset["bpm"]))
        self.chain_frame.config(text=i18n.t("panel_chain"))
        for label, key in self.chain_headers:
            if key:
                label.config(text=i18n.t(key))
        for row in self.chain_rows:
            row["toggle_btn"].config(text=i18n.t("chain_toggle"))
            if row["pedal"] is None:
                row["state_var"].set("—")
            else:
                row["state_var"].set(i18n.t("chain_on") if row["pedal"]["on"] else i18n.t("chain_off"))
        if self.last_preset is None:
            self.chain_preset_var.set(i18n.t("chain_none"))
        else:
            self._render_chain_preset_label()
        self.tuner_display_frame.config(text=i18n.t("panel_tuner_display"))
        if self._tuner_last_cents is None:
            self.tuner_raw_var.set(i18n.t("tuner_no_signal"))
        is_shown = self.log_frame.winfo_ismapped()
        self.log_toggle_btn.config(text=i18n.t("log_hide") if is_shown else i18n.t("log_show"))
        self.btn_log_export.config(text=i18n.t("log_export"))
        self.btn_log_clear.config(text=i18n.t("log_clear"))

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
        self.reset_chain_display()
        self.reset_mixer_display()
        self.reset_patch_names()

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

    def set_mixer_volume(self, channel: int, value: float):
        future = self.backend.call(self.backend.set_mixer_volume(channel, value))

        def done_callback(f):
            try:
                f.result()
            except Exception as e:
                self.ui_queue.put((
                    "error",
                    i18n.t("error_mixer_failed", type=type(e).__name__, error=e),
                ))

        future.add_done_callback(done_callback)

    def apply_mixer_value(self, channel: int, value: float):
        if channel == MIXER_CHANNEL_GUITAR:
            self.guitar_vol_var.set(value)
            self.guitar_vol_pct.set(f"{value * 100:.0f}%")

    def reset_mixer_display(self):
        self.guitar_vol_var.set(0.5)
        self.guitar_vol_pct.set("50%")
        self._tap_times = []
        self.tap_tempo_var.set(i18n.t("tap_tempo_none"))

    def _on_mixer_scale_click(self, event):
        """ttk.Scale on macOS jumps straight to 0 or the maximum when you click the
        trough (not the thumb itself) instead of moving proportionally to the click -
        a known Tk/Aqua quirk. Compute the intended value ourselves and set it, but
        only for trough clicks; a click on the thumb itself is left alone so normal
        dragging still works."""
        scale = event.widget
        if "trough" not in scale.identify(event.x, event.y):
            return None
        width = scale.winfo_width()
        frac = min(max(event.x / width, 0.0), 1.0) if width else 0.0
        # ttk.Scale's `command` callback is invoked by the widget's own click/drag
        # handling, not by a variable trace - setting the variable directly (to
        # override the buggy native jump-to-extreme) doesn't fire it, so the percent
        # label needs updating here too.
        self.guitar_vol_var.set(frac)
        self.guitar_vol_pct.set(f"{frac * 100:.0f}%")
        return "break"

    def tap_tempo(self):
        now = time.monotonic()
        if self._tap_times and now - self._tap_times[-1] > TAP_TEMPO_RESET_GAP:
            self._tap_times = []
        self._tap_times.append(now)
        self._tap_times = self._tap_times[-TAP_TEMPO_MAX_SAMPLES:]
        if len(self._tap_times) < 2:
            self.tap_tempo_var.set(i18n.t("tap_tempo_waiting"))
            return
        intervals = [t2 - t1 for t1, t2 in zip(self._tap_times, self._tap_times[1:])]
        avg_interval = sum(intervals) / len(intervals)
        bpm = max(TAP_TEMPO_MIN_BPM, min(TAP_TEMPO_MAX_BPM, 60.0 / avg_interval))
        self.tap_tempo_var.set(i18n.t("tap_tempo_bpm", bpm=bpm))

        future = self.backend.call(self.backend.send_tap_tempo(bpm))

        def done_callback(f):
            try:
                f.result()
            except Exception as e:
                self.ui_queue.put((
                    "error",
                    i18n.t("error_tap_tempo_failed", type=type(e).__name__, error=e),
                ))

        future.add_done_callback(done_callback)

    def toggle_chain_slot(self, slot_index: int):
        row = self.chain_rows[slot_index]
        pedal = row["pedal"]
        if not pedal:
            return
        new_on = not pedal["on"]
        future = self.backend.call(self.backend.toggle_effect(pedal["name"], new_on))

        def done_callback(f):
            try:
                f.result()
            except Exception as e:
                self.ui_queue.put((
                    "error",
                    i18n.t("error_toggle_effect_failed", name=pedal["name"], type=type(e).__name__, error=e),
                ))
            else:
                # Apply optimistically as soon as the write succeeds, rather than
                # waiting solely on the device's real-time confirmation
                # (CMD 0x03/SUB_CMD 0x15) - if that notification is slow, dropped, or
                # never applied, pedal["on"] would otherwise stay stale and every
                # subsequent click would keep recomputing the same (wrong) direction.
                # apply_effect_state still runs if/when the live confirmation arrives,
                # correcting this if the command didn't actually take effect.
                self.ui_queue.put(("effect_state", {"name": pedal["name"], "on": new_on}))

        future.add_done_callback(done_callback)

    def apply_patch_name(self, n: int, name: str):
        if 0 <= n < len(self.patch_name_vars):
            self.patch_name_vars[n].set(name or i18n.t("chain_unnamed"))

    def reset_patch_names(self):
        for var in self.patch_name_vars:
            var.set("—")

    def _render_chain_preset_label(self):
        preset = self.last_preset
        self.chain_preset_var.set(i18n.t(
            "chain_preset_label",
            name=preset["name"] or i18n.t("chain_unnamed"),
            n=preset["preset_num"] + 1,
            bpm=preset["bpm"],
        ))

    def update_chain_display(self, preset: dict):
        self.last_preset = preset
        self._render_chain_preset_label()
        self.patch_bpm_var.set(i18n.t("patch_bpm_label", bpm=preset["bpm"]))
        for row, pedal in zip(self.chain_rows, preset["pedals"]):
            row["pedal"] = pedal
            row["name_var"].set(pedal["name"])
            row["state_var"].set(i18n.t("chain_on") if pedal["on"] else i18n.t("chain_off"))
            row["state_label"].config(fg="#2e7d32" if pedal["on"] else "#8b909b")
            row["toggle_btn"].config(state="normal")
            row["params_var"].set(" ".join(f"P{p['id']}={p['value']:.2f}" for p in pedal["params"]))

    def apply_effect_state(self, name: str, on: bool):
        """Update whichever row currently shows this internal pedal name, from the
        device's own real-time confirmation - see parse_effect_state_notification."""
        for row in self.chain_rows:
            if row["pedal"] and row["pedal"]["name"] == name:
                row["pedal"]["on"] = on
                row["state_var"].set(i18n.t("chain_on") if on else i18n.t("chain_off"))
                row["state_label"].config(fg="#2e7d32" if on else "#8b909b")

    def reset_chain_display(self):
        self.last_preset = None
        self.chain_preset_var.set(i18n.t("chain_none"))
        self.patch_bpm_var.set(i18n.t("patch_bpm_unknown"))
        for row in self.chain_rows:
            row["pedal"] = None
            row["name_var"].set("—")
            row["state_var"].set("—")
            row["state_label"].config(fg="#8b909b")
            row["toggle_btn"].config(state="disabled")
            row["params_var"].set("")

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
            self.log_frame.pack(fill="both", expand=True)
            self.log_toggle_btn.config(text=i18n.t("log_hide"))

    def log(self, text: str):
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")

    def clear_log(self):
        self.log_text.delete("1.0", "end")

    def export_log(self):
        path = filedialog.asksaveasfilename(
            title=i18n.t("log_export"),
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile="spark_go_log.txt",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.log_text.get("1.0", "end"))
        except OSError as e:
            messagebox.showerror(i18n.t("app_title"), i18n.t("log_export_failed", err=str(e)))

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
                elif kind == "preset":
                    self.update_chain_display(data)
                elif kind == "effect_state":
                    self.apply_effect_state(data["name"], data["on"])
                elif kind == "patch_name":
                    self.apply_patch_name(data["n"], data["name"])
                elif kind == "mixer":
                    self.apply_mixer_value(data["channel"], data["value"])
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
