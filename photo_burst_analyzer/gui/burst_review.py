"""Stage 1: Burst Review

One burst at a time. Auto-selects the best photo (highest composite score).
User confirms with Space, swaps by clicking, or keeps multiple with Ctrl+click.
Side-by-side comparison available via Compare button or 'C' key.
"""

import os
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageOps, ImageTk


# ── Helpers ──────────────────────────────────────────────────────────────────

def _bar_color(pct: float) -> str:
    """Green / yellow / red based on percentage 0-100."""
    if pct >= 65:
        return "#3cb371"
    if pct >= 35:
        return "#e8a020"
    return "#cc3333"


def _normalize_burst_scores(burst: dict) -> list[float]:
    """Return composites normalised to 0-100 relative to the best in this burst."""
    comps = burst.get("composites") or []
    valid = [c for c in comps if c is not None]
    if not valid:
        return [50.0] * len(comps)
    best = max(valid)
    if best == 0:
        return [50.0] * len(comps)
    return [min(100.0, (c / best) * 100.0) if c is not None else 0.0 for c in comps]


def _load_thumb(path: str, size: int) -> ImageTk.PhotoImage:
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)
    im = im.convert("RGB")
    im.thumbnail((size, size), Image.Resampling.LANCZOS)
    return ImageTk.PhotoImage(im)


# ── Quality bar canvas widget ────────────────────────────────────────────────

def _draw_bars(canvas: tk.Canvas, metrics: list[tuple[str, float | None]], bar_w=90, bar_h=8):
    """Draw labelled quality bars onto a canvas. metrics = [(label, value_0_100), ...]"""
    canvas.delete("all")
    x0 = 4   # left inset so text/bars aren't clipped at the canvas edge
    y = 4    # top inset
    for label, val in metrics:
        pct = val if val is not None else 0.0
        color = _bar_color(pct)
        canvas.create_text(x0, y, anchor="nw", text=label, font=("Arial", 7), fill="#555")
        y += 11
        canvas.create_rectangle(x0, y, x0 + bar_w, y + bar_h, fill="#ddd", outline="")
        canvas.create_rectangle(x0, y, x0 + int(bar_w * pct / 100.0), y + bar_h, fill=color, outline="")
        canvas.create_text(x0 + bar_w + 4, y, anchor="nw", text=f"{pct:.0f}", font=("Arial", 7), fill="#333")
        y += bar_h + 6


# ── Comparison window ─────────────────────────────────────────────────────────

class ComparisonWindow(tk.Toplevel):
    """Scrollable comparison of all burst photos with multi-select and quality bars.

    Click any photo to toggle it selected (green border).  Close via the Done
    button, Escape, or the window's own X — all three apply the current selection.
    Photos resize automatically when the window is dragged larger/smaller.
    """

    # Pixels reserved for toolbar + bars + filename + select indicator + padding
    _CHROME_HEIGHT = 224

    def __init__(self, parent, photos: list[dict],
                 initially_selected: set = None, on_picks=None):
        """
        photos:             list of {path, blur, exposure, composite, has_face, norm_score}
        initially_selected: set of paths pre-checked when the window opens
        on_picks:           callable(set[path]) called with all selected paths on close
        """
        super().__init__(parent)
        self.title("Compare Photos")
        self._on_picks = on_picks
        self._rot_enabled = tk.BooleanVar(value=False)
        self._photos = photos
        self._selected: set = set(initially_selected or [])
        self._tkimgs = []
        self._canvases = []
        self._col_frames: dict = {}   # path -> col_frame, for border updates
        self._resize_job = None

        n = len(photos)
        init_w = min(1400, max(800, n * 300))
        self.geometry(f"{init_w}x720")
        self.resizable(True, True)

        self._build()
        # All dismiss paths apply the selection
        self.protocol("WM_DELETE_WINDOW", self._confirm)
        self.bind("<Escape>", lambda e: self._confirm())
        self.bind("<Configure>", self._on_window_resize)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        toolbar = tk.Frame(self, pady=4, bg="#222")
        toolbar.pack(fill="x", padx=8)

        tk.Checkbutton(toolbar, text="Rule of Thirds", variable=self._rot_enabled,
                       bg="#222", fg="#eee", selectcolor="#444",
                       command=self._redraw).pack(side="left", padx=6)

        self._sel_count_lbl = tk.Label(toolbar, text="", bg="#222", fg="#aaa",
                                       font=("Arial", 9))
        self._sel_count_lbl.pack(side="left", padx=16)

        # Done button — applies selection and closes
        done_lbl = tk.Label(toolbar, text="Done", bg="#3cb371", fg="white",
                            font=("Arial", 10, "bold"), padx=12, pady=4, cursor="hand2")
        done_lbl.pack(side="right", padx=8)
        done_lbl.bind("<Button-1>", lambda e: self._confirm())

        # Scrollable photo row
        outer = tk.Frame(self, bg="#1a1a1a")
        outer.pack(fill="both", expand=True)

        hscroll = ttk.Scrollbar(outer, orient="horizontal")
        hscroll.pack(side="bottom", fill="x")

        self._scroll_canvas = tk.Canvas(outer, xscrollcommand=hscroll.set, bg="#1a1a1a",
                                        highlightthickness=0)
        self._scroll_canvas.pack(fill="both", expand=True)
        hscroll.config(command=self._scroll_canvas.xview)

        self._photo_frame = tk.Frame(self._scroll_canvas, bg="#1a1a1a")
        self._frame_id = self._scroll_canvas.create_window(
            (0, 0), window=self._photo_frame, anchor="nw")

        self._photo_frame.bind("<Configure>", lambda e: self._scroll_canvas.configure(
            scrollregion=self._scroll_canvas.bbox("all")))
        self._scroll_canvas.bind(
            "<MouseWheel>",
            lambda e: self._scroll_canvas.xview_scroll(-1 * (e.delta // 120), "units"))

        self._redraw()

    # ── Resize ────────────────────────────────────────────────────────────────

    def _on_window_resize(self, event):
        if event.widget is not self:
            return
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(120, self._redraw)

    def _photo_size(self) -> tuple[int, int]:
        win_h = self.winfo_height()
        target_h = max(200, win_h - self._CHROME_HEIGHT)
        target_w = int(target_h * 4 / 3)
        return target_w, target_h

    # ── Render ────────────────────────────────────────────────────────────────

    def _redraw(self):
        self._resize_job = None
        for w in self._photo_frame.winfo_children():
            w.destroy()
        self._tkimgs.clear()
        self._canvases.clear()
        self._col_frames.clear()

        target_w, target_h = self._photo_size()

        for col, p in enumerate(self._photos):
            path = p["path"]
            is_sel = path in self._selected
            border = "#00e676" if is_sel else "#444"

            col_frame = tk.Frame(self._photo_frame, bg="#222",
                                 highlightbackground=border, highlightcolor=border,
                                 highlightthickness=3)
            col_frame.grid(row=0, column=col, padx=6, pady=6, sticky="n")
            self._col_frames[path] = col_frame

            # Image canvas — click anywhere on it to toggle selection
            c = tk.Canvas(col_frame, width=target_w, height=target_h, bg="black",
                          cursor="hand2", highlightthickness=0)
            c.pack()
            self._canvases.append(c)
            c.bind("<Button-1>", lambda e, _p=path: self._toggle(_p))

            try:
                im = Image.open(path)
                im = ImageOps.exif_transpose(im)
                im = im.convert("RGB")
                im.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)
                tkimg = ImageTk.PhotoImage(im)
                self._tkimgs.append(tkimg)
                iw, ih = im.size
                ox = (target_w - iw) // 2
                oy = (target_h - ih) // 2
                c.create_image(ox, oy, anchor="nw", image=tkimg)
                if self._rot_enabled.get():
                    self._draw_rot(c, ox, oy, iw, ih)
            except Exception:
                self._tkimgs.append(None)
                c.create_text(target_w // 2, target_h // 2, text="Error", fill="red")

            # Quality bars
            bar_canvas = tk.Canvas(col_frame, width=target_w, height=84, bg="white",
                                   highlightthickness=0)
            bar_canvas.pack(fill="x")
            norm = p.get("norm_score", 50.0)
            blur_norm = min(100.0, (p.get("blur", 0) ** 0.5) * 3.16)
            exp = p.get("exposure", 50.0) or 50.0
            _draw_bars(bar_canvas, [("Sharp", blur_norm), ("Exposure", exp), ("Overall", norm)])

            # Filename + face tag
            fname = os.path.basename(path)
            face_tag = " [face]" if p.get("has_face") else ""
            tk.Label(col_frame, text=fname + face_tag, font=("Arial", 8), fg="#ccc",
                     bg="#222", wraplength=target_w).pack()

            # Selected indicator label (toggles on click)
            ind = tk.Label(col_frame,
                           text="✓ Selected" if is_sel else "  Click to select  ",
                           bg="#3cb371" if is_sel else "#444",
                           fg="white", font=("Arial", 9, "bold"),
                           padx=8, pady=3, cursor="hand2")
            ind.pack(pady=(2, 6))
            ind.bind("<Button-1>", lambda e, _p=path: self._toggle(_p))

        self._update_count_label()

    # ── Selection ─────────────────────────────────────────────────────────────

    def _toggle(self, path: str):
        if path in self._selected:
            self._selected.discard(path)
        else:
            self._selected.add(path)
        self._update_card(path)
        self._update_count_label()

    def _update_card(self, path: str):
        """Refresh border and indicator label for one card without full redraw."""
        col_frame = self._col_frames.get(path)
        if col_frame is None:
            return
        is_sel = path in self._selected
        border = "#00e676" if is_sel else "#444"
        col_frame.config(highlightbackground=border, highlightcolor=border)
        # The indicator label is the last child of col_frame
        children = col_frame.winfo_children()
        if children:
            ind = children[-1]
            ind.config(text="✓ Selected" if is_sel else "  Click to select  ",
                       bg="#3cb371" if is_sel else "#444")

    def _update_count_label(self):
        n = len(self._selected)
        self._sel_count_lbl.config(
            text=f"{n} photo{'s' if n != 1 else ''} selected" if n else "Click photos to select")

    # ── Confirm / close ───────────────────────────────────────────────────────

    def _confirm(self):
        """Apply current selection and close — called by Done, Escape, and window X."""
        if self._on_picks:
            self._on_picks(set(self._selected))
        self.destroy()

    # ── Rule of thirds ────────────────────────────────────────────────────────

    def _draw_rot(self, canvas: tk.Canvas, ox, oy, w, h):
        opts = {"fill": "#ffffff", "dash": (4, 4)}
        for frac in (1/3, 2/3):
            x = ox + int(w * frac)
            canvas.create_line(x, oy, x, oy + h, **opts)
            y = oy + int(h * frac)
            canvas.create_line(ox, y, ox + w, y, **opts)


# ── Main burst review frame ───────────────────────────────────────────────────

class BurstReviewFrame(tk.Frame):
    """Stage 1: review one burst at a time.

    Callbacks:
      on_stage_complete(kept_paths: set)  – all bursts reviewed
    """

    THUMB_SIZE = 180

    def __init__(self, parent, bursts: list, on_stage_complete, settings: dict):
        super().__init__(parent)
        self._bursts = bursts
        self._on_complete = on_stage_complete
        self._settings = settings
        self._thumb_size = settings.get("thumb_size", self.THUMB_SIZE)

        # Per-burst selection: list of sets (one per burst)
        self._selections: list[set] = []
        for b in bursts:
            best = b.get("best_idx", 0)
            paths = b.get("burst", [])
            self._selections.append({paths[best]} if paths else set())

        self._current = 0        # current burst index
        self._norm_scores = []   # pre-computed per-burst normalised scores
        for b in bursts:
            self._norm_scores.append(_normalize_burst_scores(b))

        self._tkimgs = []        # keep refs alive
        self._card_frames = []   # per-photo container frames

        self._build_chrome()
        self._show_burst(0)

        # Keyboard bindings on the parent window
        self._root = self.winfo_toplevel()
        self._root.bind("<space>", self._on_space)
        self._root.bind("<Return>", self._on_space)
        self._root.bind("<Left>", lambda e: self._shift_pick(-1))
        self._root.bind("<Right>", lambda e: self._shift_pick(1))
        self._root.bind("c", lambda e: self._open_comparison())
        self._root.bind("C", lambda e: self._open_comparison())
        self._root.bind("a", lambda e: self._select_all())
        self._root.bind("A", lambda e: self._select_all())
        self._root.bind("s", lambda e: self._skip())
        self._root.bind("S", lambda e: self._skip())

    def _build_chrome(self):
        # ── Header bar ──────────────────────────────────────────────────────
        self._header = tk.Frame(self, bg="#2c2c2c")
        self._header.pack(fill="x")

        self._title_lbl = tk.Label(self._header, text="", bg="#2c2c2c", fg="white",
                                   font=("Arial", 13, "bold"))
        self._title_lbl.pack(side="left", padx=12, pady=6)

        self._count_lbl = tk.Label(self._header, text="", bg="#2c2c2c", fg="#aaa",
                                   font=("Arial", 10))
        self._count_lbl.pack(side="left", padx=8)

        self._progress = ttk.Progressbar(self._header, orient="horizontal", length=200,
                                         mode="determinate")
        self._progress.pack(side="right", padx=12, pady=8)

        # ── Filmstrip area (scrollable horizontal) ───────────────────────────
        strip_outer = tk.Frame(self)
        strip_outer.pack(fill="both", expand=True, padx=8, pady=(8, 0))

        self._hscroll = ttk.Scrollbar(strip_outer, orient="horizontal")
        self._hscroll.pack(side="bottom", fill="x")

        self._canvas = tk.Canvas(strip_outer, yscrollcommand=None,
                                 xscrollcommand=self._hscroll.set, bg="#1a1a1a", height=320)
        self._canvas.pack(fill="both", expand=True)
        self._hscroll.config(command=self._canvas.xview)

        self._strip = tk.Frame(self._canvas, bg="#1a1a1a")
        self._strip_window = self._canvas.create_window((0, 0), window=self._strip, anchor="nw")
        self._strip.bind("<Configure>", lambda e: self._canvas.configure(
            scrollregion=self._canvas.bbox("all")))

        # ── Status line ───────────────────────────────────────────────────────
        self._status_lbl = tk.Label(self, text="", font=("Arial", 9), fg="#555")
        self._status_lbl.pack(pady=(4, 0))

        # ── Action buttons ────────────────────────────────────────────────────
        btn_bar = tk.Frame(self, pady=6)
        btn_bar.pack()

        # Use tk.Label (not tk.Button) for the green primary action so the text
        # renders immediately on macOS. tk.Button with a custom bg/fg uses native
        # macOS rendering where white text on a gray surface is invisible until clicked.
        self._accept_btn = tk.Label(
            btn_bar, text="Accept Best  [Space]", bg="#3cb371", fg="white",
            font=("Arial", 11, "bold"), padx=12, pady=6, cursor="hand2")
        self._accept_btn.pack(side="left", padx=8)
        self._accept_btn.bind("<Button-1>", lambda e: self._accept())

        tk.Button(btn_bar, text="Compare  [C]", width=14, command=self._open_comparison).pack(side="left", padx=4)
        tk.Button(btn_bar, text="Keep All  [A]", width=12, command=self._select_all).pack(side="left", padx=4)
        tk.Button(btn_bar, text="Skip  [S]", width=10, command=self._skip).pack(side="left", padx=4)

        # ── Tip ───────────────────────────────────────────────────────────────
        tk.Label(self, text="Click a photo to swap pick  ·  Ctrl+click to keep multiple",
                 font=("Arial", 8), fg="#888").pack(pady=(0, 4))

    # ── Burst rendering ───────────────────────────────────────────────────────

    def _show_burst(self, idx: int):
        if idx < 0 or idx >= len(self._bursts):
            return
        self._current = idx
        burst = self._bursts[idx]
        paths = burst.get("burst", [])
        norm = self._norm_scores[idx]
        selected = self._selections[idx]

        # Update header
        total = len(self._bursts)
        self._title_lbl.config(text=f"Burst {idx + 1} / {total}")
        self._count_lbl.config(text=f"{len(paths)} photos")
        self._progress["maximum"] = total
        self._progress["value"] = idx

        # Clear strip
        for w in self._strip.winfo_children():
            w.destroy()
        self._tkimgs.clear()
        self._card_frames.clear()

        blur_list = burst.get("blur_scores") or [None] * len(paths)
        exp_list = burst.get("exposures") or [None] * len(paths)

        for i, path in enumerate(paths[:32]):
            card = self._make_card(i, path, norm[i] if i < len(norm) else 0.0,
                                   blur_list[i], exp_list[i], selected, burst)
            card.grid(row=0, column=i, padx=6, pady=8)
            self._card_frames.append(card)

        # Reset filmstrip scroll to the left for each new burst
        self._canvas.xview_moveto(0)
        self._update_status()

    def _make_card(self, i: int, path: str, norm_score: float,
                   blur, exposure, selected: set, burst: dict) -> tk.Frame:
        is_sel = path in selected
        border_color = "#00e676" if is_sel else "#444"
        border_w = 4 if is_sel else 1

        card = tk.Frame(self._strip, bg="#1a1a1a",
                        highlightbackground=border_color,
                        highlightcolor=border_color,
                        highlightthickness=border_w)

        # Thumbnail
        try:
            tkimg = _load_thumb(path, self._thumb_size)
        except Exception:
            tkimg = None
        self._tkimgs.append(tkimg)

        img_lbl = tk.Label(card, image=tkimg, bg="#1a1a1a", cursor="hand2")
        img_lbl.image = tkimg
        img_lbl.pack()

        # Quality bars
        bar_canvas = tk.Canvas(card, width=100, height=84, bg="#1a1a1a", highlightthickness=0)
        bar_canvas.pack(pady=(2, 0))
        blur_norm = min(100.0, ((blur or 0) ** 0.5) * 3.16)
        exp_val = exposure or 0.0
        _draw_bars(bar_canvas, [
            ("Sharp", blur_norm),
            ("Expo", exp_val),
            ("Score", norm_score),
        ], bar_w=80)

        # Filename (truncated)
        fname = os.path.basename(path)
        if len(fname) > 18:
            fname = fname[:15] + "…"
        tk.Label(card, text=fname, font=("Arial", 7), fg="#aaa", bg="#1a1a1a").pack()

        # Bind clicks
        def on_click(ev, _path=path, _card=card):
            ctrl = (ev.state & 0x4) != 0
            self._toggle_selection(_path, _card, ctrl)

        for w in (card, img_lbl, bar_canvas):
            w.bind("<Button-1>", on_click)

        return card

    # ── Selection management ──────────────────────────────────────────────────

    def _toggle_selection(self, path: str, card: tk.Frame, multi: bool):
        sel = self._selections[self._current]
        burst = self._bursts[self._current]
        paths = burst.get("burst", [])

        if multi:
            # Ctrl+click: toggle without clearing others
            if path in sel:
                if len(sel) > 1:   # must keep at least one selected
                    sel.discard(path)
            else:
                sel.add(path)
        else:
            # Normal click: swap to this photo only
            sel.clear()
            sel.add(path)

        self._refresh_borders()
        self._update_status()

    def _refresh_borders(self):
        sel = self._selections[self._current]
        burst = self._bursts[self._current]
        paths = burst.get("burst", [])
        for i, card in enumerate(self._card_frames):
            if i >= len(paths):
                break
            is_sel = paths[i] in sel
            color = "#00e676" if is_sel else "#444"
            width = 4 if is_sel else 1
            card.config(highlightbackground=color, highlightcolor=color, highlightthickness=width)

    def _shift_pick(self, delta: int):
        """Move the single selection left/right using arrow keys."""
        sel = self._selections[self._current]
        paths = self._bursts[self._current].get("burst", [])
        if not paths:
            return
        # Find current pick index (first selected)
        try:
            current_idx = next(i for i, p in enumerate(paths) if p in sel)
        except StopIteration:
            current_idx = 0
        new_idx = max(0, min(len(paths) - 1, current_idx + delta))
        sel.clear()
        sel.add(paths[new_idx])
        self._refresh_borders()
        self._update_status()

    def _select_all(self):
        sel = self._selections[self._current]
        paths = self._bursts[self._current].get("burst", [])
        sel.update(paths)
        self._refresh_borders()
        self._update_status()

    def _update_status(self):
        sel = self._selections[self._current]
        burst = self._bursts[self._current]
        paths = burst.get("burst", [])
        n_kept = len(sel)
        n_total = len(paths)
        msg = f"Keeping {n_kept} of {n_total} photos in this burst"
        if n_kept > 1:
            msg += "  (Ctrl+click to deselect extras)"
        self._status_lbl.config(text=msg)

    # ── Navigation ────────────────────────────────────────────────────────────

    def _on_space(self, event=None):
        self._accept()

    def _accept(self):
        self._advance()

    def _skip(self):
        """Skip burst: keep nothing (defer to Stage 3 if needed, effectively drop burst)."""
        self._selections[self._current].clear()
        self._advance()

    def _advance(self):
        next_idx = self._current + 1
        if next_idx >= len(self._bursts):
            self._finish()
        else:
            self._show_burst(next_idx)

    def cleanup(self):
        """Remove root-window key bindings installed by this frame.

        Called by the parent App before _clear_content() destroys the frame,
        so bindings don't linger and fire against a dead frame.
        """
        self._unbind_keys()

    def _unbind_keys(self):
        try:
            for key in ("<space>", "<Return>", "<Left>", "<Right>",
                        "c", "C", "a", "A", "s", "S"):
                self._root.unbind(key)
        except Exception:
            pass

    def _finish(self):
        self._unbind_keys()
        kept = set()
        for sel in self._selections:
            kept.update(sel)
        self._on_complete(kept)

    # ── Comparison ────────────────────────────────────────────────────────────

    def _open_comparison(self):
        burst = self._bursts[self._current]
        paths = burst.get("burst", [])
        sel = self._selections[self._current]
        norm = self._norm_scores[self._current]
        blur_list = burst.get("blur_scores") or [None] * len(paths)
        exp_list = burst.get("exposures") or [None] * len(paths)
        face_list = burst.get("has_faces") or [False] * len(paths)

        # Show all burst photos in burst order; selected photos appear first.
        show_paths = [p for p in paths if p in sel] + [p for p in paths if p not in sel]

        photos = []
        for p in show_paths:
            i = paths.index(p) if p in paths else 0
            photos.append({
                "path": p,
                "blur": blur_list[i] if i < len(blur_list) else None,
                "exposure": exp_list[i] if i < len(exp_list) else None,
                "norm_score": norm[i] if i < len(norm) else 50.0,
                "has_face": face_list[i] if i < len(face_list) else False,
            })

        def on_picks(chosen: set):
            if chosen:
                self._selections[self._current] = chosen
                self._refresh_borders()
                self._update_status()

        ComparisonWindow(self._root, photos,
                         initially_selected=set(sel),
                         on_picks=on_picks)
