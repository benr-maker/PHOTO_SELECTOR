"""Settings modal dialog."""

import tkinter as tk
from tkinter import ttk

DEFAULT_SETTINGS = {
    "burst_threshold": 1.0,
    "sharpness_weight": 50,
    "exposure_weight": 30,
    "use_face_detection": True,
    "top_tile_pct": 20,        # stored as integer 1-50
    "thumb_size": 160,
    "max_workers": 0,          # 0 = auto
}


class SettingsDialog(tk.Toplevel):
    """Modal settings dialog. Call .result after closing to get updated settings dict."""

    def __init__(self, parent, current: dict):
        super().__init__(parent)
        self.title("Settings")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result = None

        s = dict(DEFAULT_SETTINGS)
        s.update(current)
        self._build(s)

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.wait_window(self)

    # ── Build UI ────────────────────────────────────────────────────────────

    def _build(self, s):
        pad = {"padx": 12, "pady": 6}
        frame = tk.Frame(self, padx=16, pady=12)
        frame.pack(fill="both", expand=True)

        row = 0

        # Section: Burst detection
        self._section(frame, "Burst Detection", row); row += 1
        self._burst_var = tk.DoubleVar(value=s["burst_threshold"])
        self._slider_row(frame, row, "Burst time threshold (s):", self._burst_var, 0.2, 5.0, 0.1)
        row += 1

        # Section: Scoring weights
        self._section(frame, "Scoring Weights", row); row += 1

        self._sharp_var = tk.IntVar(value=s["sharpness_weight"])
        self._slider_row(frame, row, "Sharpness weight:", self._sharp_var, 0, 100, 1)
        row += 1

        self._expo_var = tk.IntVar(value=s["exposure_weight"])
        self._slider_row(frame, row, "Exposure weight:", self._expo_var, 0, 100, 1)
        row += 1

        # Section: Sharpness method
        self._section(frame, "Sharpness Method", row); row += 1

        self._face_var = tk.BooleanVar(value=s["use_face_detection"])
        tk.Checkbutton(frame, text="Face detection (falls back to tile-based if no face found)",
                       variable=self._face_var).grid(row=row, column=0, columnspan=3, sticky="w", **pad)
        row += 1

        self._tile_var = tk.IntVar(value=s["top_tile_pct"])
        self._slider_row(frame, row, "Top tile % for tile-based scoring:", self._tile_var, 5, 50, 1)
        row += 1

        # Section: Display
        self._section(frame, "Display", row); row += 1

        self._thumb_var = tk.IntVar(value=s["thumb_size"])
        self._slider_row(frame, row, "Default thumbnail size (px):", self._thumb_var, 80, 300, 10)
        row += 1

        # Section: Performance
        self._section(frame, "Performance", row); row += 1

        self._workers_var = tk.IntVar(value=s["max_workers"])
        self._slider_row(frame, row, "Worker threads (0 = auto):", self._workers_var, 0, 32, 1)
        row += 1

        # Buttons
        btn_frame = tk.Frame(frame)
        btn_frame.grid(row=row, column=0, columnspan=3, pady=(12, 0))
        tk.Button(btn_frame, text="Apply", width=10, command=self._apply).pack(side="left", padx=6)
        tk.Button(btn_frame, text="Cancel", width=10, command=self._cancel).pack(side="left", padx=6)
        tk.Button(btn_frame, text="Defaults", width=10, command=lambda: self._reset(frame)).pack(side="left", padx=6)

    def _section(self, parent, text, row):
        tk.Label(parent, text=text, font=("Arial", 10, "bold"), fg="#444").grid(
            row=row, column=0, columnspan=3, sticky="w", padx=12, pady=(10, 2))

    def _slider_row(self, parent, row, label, var, from_, to, resolution):
        tk.Label(parent, text=label, width=36, anchor="w").grid(row=row, column=0, padx=12, pady=4, sticky="w")
        s = ttk.Scale(parent, from_=from_, to=to, orient="horizontal", length=180,
                      variable=var, command=lambda v, _v=var: _v.set(round(float(v), 2)))
        s.grid(row=row, column=1, padx=6)
        lbl = tk.Label(parent, textvariable=var, width=5, anchor="w")
        lbl.grid(row=row, column=2, padx=4)

    # ── Actions ─────────────────────────────────────────────────────────────

    def _apply(self):
        self.result = {
            "burst_threshold": round(self._burst_var.get(), 2),
            "sharpness_weight": int(self._sharp_var.get()),
            "exposure_weight": int(self._expo_var.get()),
            "use_face_detection": bool(self._face_var.get()),
            "top_tile_pct": int(self._tile_var.get()),
            "thumb_size": int(self._thumb_var.get()),
            "max_workers": int(self._workers_var.get()),
        }
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()

    def _reset(self, frame):
        for child in frame.winfo_children():
            child.destroy()
        self._build(dict(DEFAULT_SETTINGS))


def open_settings(parent, current: dict) -> dict:
    """Open settings dialog and return updated settings (or original if cancelled)."""
    dlg = SettingsDialog(parent, current)
    return dlg.result if dlg.result is not None else current
