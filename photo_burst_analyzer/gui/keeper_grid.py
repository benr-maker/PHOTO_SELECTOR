"""Stage 3: Keeper Grid

Scrollable grid of kept photos.
- Click to toggle deselect (stragglers)
- Drag to reorder
- Export selected to folder
"""

import logging
import os
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageOps, ImageTk

logger = logging.getLogger("pba.keeper_grid")


class KeeperGridFrame(tk.Frame):
    """Stage 3 – final curation grid.

    on_export_done: optional callable notified after a successful save.
    """

    COLS = 6

    def __init__(self, parent, kept_paths: set, all_bursts: list,
                 on_export_done=None, settings: dict = None):
        super().__init__(parent)
        self._settings = settings or {}
        self._thumb_size = self._settings.get("thumb_size", 160)
        self._on_export_done = on_export_done

        # Build ordered list from burst order (preserves sequence)
        self._photos = self._ordered(kept_paths, all_bursts)
        self._selected = set(self._photos)   # all kept by default
        self._tkimgs = {}
        self._card_widgets = {}

        # Drag state — all fields initialised here so no AttributeError is
        # possible even if motion/release events arrive before ButtonPress.
        self._drag_src: int | None = None
        self._drag_moved: bool = False
        self._drag_indicator = None  # reserved for a future drag-ghost widget

        self._build()
        self._render()

    # ── Layout ───────────────────────────────────────────────────────────────

    def _build(self):
        # Top bar
        top = tk.Frame(self, bg="#2c2c2c")
        top.pack(fill="x")
        tk.Label(top, text="Final Selection", bg="#2c2c2c", fg="white",
                 font=("Arial", 13, "bold")).pack(side="left", padx=12, pady=6)
        self._count_lbl = tk.Label(top, text="", bg="#2c2c2c", fg="#aaa", font=("Arial", 10))
        self._count_lbl.pack(side="left", padx=8)

        # Thumb size slider
        tk.Label(top, text="Size:", bg="#2c2c2c", fg="#ccc", font=("Arial", 9)).pack(side="right", padx=(0, 4))
        self._size_var = tk.IntVar(value=self._thumb_size)
        sld = ttk.Scale(top, from_=80, to=300, orient="horizontal", length=120,
                        variable=self._size_var)
        sld.pack(side="right", padx=(0, 12), pady=6)
        sld.bind("<ButtonRelease-1>", self._on_resize)

        # Scrollable canvas
        outer = tk.Frame(self)
        outer.pack(fill="both", expand=True)
        vscroll = ttk.Scrollbar(outer, orient="vertical")
        vscroll.pack(side="right", fill="y")
        self._canvas = tk.Canvas(outer, yscrollcommand=vscroll.set, bg="#111")
        self._canvas.pack(fill="both", expand=True)
        vscroll.config(command=self._canvas.yview)

        self._grid_frame = tk.Frame(self._canvas, bg="#111")
        self._canvas_window = self._canvas.create_window((0, 0), window=self._grid_frame, anchor="nw")
        self._grid_frame.bind("<Configure>", lambda e: self._canvas.configure(
            scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>", lambda e: self._canvas.itemconfig(
            self._canvas_window, width=e.width))

        # Mouse wheel scroll
        self._canvas.bind("<MouseWheel>", lambda e: self._canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        # Use tk.Label for the green primary button so text renders immediately
        # on macOS (tk.Button with custom bg/fg is invisible until clicked there).
        bot = tk.Frame(self, pady=8)
        bot.pack(fill="x", padx=8)
        export_lbl = tk.Label(bot, text="Export Selected", bg="#3cb371", fg="white",
                              font=("Arial", 11, "bold"), padx=14, pady=6, cursor="hand2")
        export_lbl.pack(side="left", padx=6)
        export_lbl.bind("<Button-1>", lambda e: self._export())
        tk.Button(bot, text="Select All", command=self._select_all).pack(side="left", padx=4)
        tk.Button(bot, text="Deselect All", command=self._deselect_all).pack(side="left", padx=4)
        self._sel_lbl = tk.Label(bot, text="", font=("Arial", 9), fg="#555")
        self._sel_lbl.pack(side="right", padx=8)

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _render(self):
        for w in self._grid_frame.winfo_children():
            w.destroy()
        self._card_widgets.clear()
        self._tkimgs.clear()

        ts = self._thumb_size
        for idx, path in enumerate(self._photos):
            row, col = divmod(idx, self.COLS)
            card = self._make_card(idx, path, ts)
            card.grid(row=row, column=col, padx=6, pady=6, sticky="n")
            self._card_widgets[path] = card

        self._update_counts()

    def _make_card(self, idx: int, path: str, ts: int) -> tk.Frame:
        is_sel = path in self._selected
        border_color = "#00e676" if is_sel else "#333"
        border_w = 3 if is_sel else 1

        card = tk.Frame(self._grid_frame, bg="#1a1a1a",
                        highlightbackground=border_color,
                        highlightcolor=border_color,
                        highlightthickness=border_w,
                        cursor="hand2")

        try:
            im = Image.open(path)
            im = ImageOps.exif_transpose(im)
            im = im.convert("RGB")
            im.thumbnail((ts, ts), Image.Resampling.LANCZOS)
            tkimg = ImageTk.PhotoImage(im)
        except Exception:
            tkimg = None
        self._tkimgs[path] = tkimg

        img_lbl = tk.Label(card, image=tkimg, bg="#1a1a1a")
        img_lbl.image = tkimg
        img_lbl.pack()

        fname = os.path.basename(path)
        if len(fname) > 20:
            fname = fname[:17] + "…"
        tk.Label(card, text=fname, font=("Arial", 7), fg="#888", bg="#1a1a1a").pack()

        # Click = toggle selection
        def on_click(ev, _path=path, _card=card):
            self._toggle(_path, _card)

        for w in (card, img_lbl):
            w.bind("<Button-1>", on_click)

        # Drag to reorder
        card.bind("<ButtonPress-1>", lambda e, i=idx: self._drag_start(e, i))
        card.bind("<B1-Motion>", self._drag_motion)
        card.bind("<ButtonRelease-1>", lambda e, i=idx: self._drag_end(e, i))
        img_lbl.bind("<ButtonPress-1>", lambda e, i=idx: self._drag_start(e, i))
        img_lbl.bind("<B1-Motion>", self._drag_motion)
        img_lbl.bind("<ButtonRelease-1>", lambda e, i=idx: self._drag_end(e, i))

        return card

    # ── Selection ─────────────────────────────────────────────────────────────

    def _toggle(self, path: str, card: tk.Frame):
        if path in self._selected:
            self._selected.discard(path)
            card.config(highlightbackground="#333", highlightcolor="#333", highlightthickness=1)
        else:
            self._selected.add(path)
            card.config(highlightbackground="#00e676", highlightcolor="#00e676", highlightthickness=3)
        self._update_counts()

    def _select_all(self):
        self._selected = set(self._photos)
        self._refresh_borders()

    def _deselect_all(self):
        self._selected.clear()
        self._refresh_borders()

    def _refresh_borders(self):
        for path, card in self._card_widgets.items():
            is_sel = path in self._selected
            card.config(
                highlightbackground="#00e676" if is_sel else "#333",
                highlightcolor="#00e676" if is_sel else "#333",
                highlightthickness=3 if is_sel else 1,
            )
        self._update_counts()

    def _update_counts(self):
        n_total = len(self._photos)
        n_sel = len(self._selected)
        self._count_lbl.config(text=f"{n_total} photos")
        self._sel_lbl.config(text=f"{n_sel} selected for export")

    # ── Drag to reorder ───────────────────────────────────────────────────────

    def _drag_start(self, event, idx: int):
        self._drag_src = idx
        self._drag_moved = False

    def _drag_motion(self, event):
        if self._drag_src is None:
            return
        self._drag_moved = True
        # Highlight potential drop target
        x_root, y_root = event.widget.winfo_rootx() + event.x, event.widget.winfo_rooty() + event.y
        target = self._target_idx_from_pos(x_root, y_root)
        self._highlight_drop_target(target)

    def _drag_end(self, event, idx: int):
        if self._drag_src is None:
            return
        try:
            if not self._drag_moved:
                # Was a short click, not a drag — delegate to toggle.
                path = self._photos[idx] if idx < len(self._photos) else None
                if path and path in self._card_widgets:
                    self._toggle(path, self._card_widgets[path])
                return

            x_root = event.widget.winfo_rootx() + event.x
            y_root = event.widget.winfo_rooty() + event.y
            target = self._target_idx_from_pos(x_root, y_root)

            if target is not None and target != self._drag_src:
                item = self._photos.pop(self._drag_src)
                self._photos.insert(target, item)
                self._render()
        except Exception:
            logger.exception("drag_end failed")
        finally:
            # Always reset drag state, even on exception, so subsequent
            # mouse events don't find a stale drag in progress.
            self._drag_src = None
            self._drag_moved = False
            self._clear_drop_highlight()

    def _target_idx_from_pos(self, x_root: int, y_root: int):
        """Find grid index under screen position."""
        for path, card in self._card_widgets.items():
            cx, cy = card.winfo_rootx(), card.winfo_rooty()
            cw, ch = card.winfo_width(), card.winfo_height()
            if cx <= x_root <= cx + cw and cy <= y_root <= cy + ch:
                try:
                    return self._photos.index(path)
                except ValueError:
                    pass
        return None

    def _highlight_drop_target(self, idx):
        self._clear_drop_highlight()
        if idx is not None and idx < len(self._photos):
            card = self._card_widgets.get(self._photos[idx])
            if card:
                card.config(highlightbackground="#ff9900", highlightcolor="#ff9900", highlightthickness=3)

    def _clear_drop_highlight(self):
        for path, card in self._card_widgets.items():
            is_sel = path in self._selected
            card.config(
                highlightbackground="#00e676" if is_sel else "#333",
                highlightcolor="#00e676" if is_sel else "#333",
                highlightthickness=3 if is_sel else 1,
            )

    # ── Export ────────────────────────────────────────────────────────────────

    def _export(self):
        if not self._selected:
            messagebox.showwarning("Nothing selected", "Select at least one photo to export.")
            return
        dest = filedialog.askdirectory(title="Select destination folder")
        if not dest:
            return
        saved, failed = 0, 0
        for path in self._selected:
            try:
                shutil.copy2(path, os.path.join(dest, os.path.basename(path)))
                saved += 1
            except Exception:
                failed += 1
        msg = f"Exported {saved} photos to:\n{dest}"
        if failed:
            msg += f"\n({failed} failed — check permissions)"
        messagebox.showinfo("Export complete", msg)
        if self._on_export_done:
            self._on_export_done(saved, dest)
        # Remove exported photos from the grid
        self._photos = [p for p in self._photos if p not in self._selected]
        self._selected.clear()
        self._render()

    # ── Resize ────────────────────────────────────────────────────────────────

    def _on_resize(self, event=None):
        self._thumb_size = int(self._size_var.get())
        self._render()

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _ordered(kept: set, bursts: list) -> list:
        """Return kept paths in burst order (preserves original sequence)."""
        ordered = []
        seen = set()
        for b in bursts:
            for path in b.get("burst", []):
                if path in kept and path not in seen:
                    ordered.append(path)
                    seen.add(path)
        # Any paths not found in bursts (shouldn't happen, but defensive)
        for p in kept:
            if p not in seen:
                ordered.append(p)
        return ordered
