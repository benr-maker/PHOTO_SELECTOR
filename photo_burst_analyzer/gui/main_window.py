"""Photo Burst Analyzer – main application window.

Three-stage triage workflow:
  Stage 1 (Burst Review)  – one burst at a time, spacebar to accept
  Stage 3 (Keeper Grid)   – drag/click final curation, then export

Settings accessible at any stage via ⚙ button.

Thread-safety notes
-------------------
* Only one analysis can run at a time (_analysis_running guard).
* The worker thread never writes to Tkinter widgets directly; all GUI
  mutations go through self.after(0, ...) to run on the main thread.
* self._bursts is assigned exclusively on the main thread
  (_on_analysis_complete), so BurstReviewFrame always reads a fully
  constructed list.
* BurstReviewFrame installs key bindings on the root window; cleanup()
  is called before _clear_content() to remove those bindings and prevent
  stale callbacks from reaching a destroyed frame.
"""

import threading
import logging
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from ..core.burst_detector import collect_images, detect_candidates
from ..core.analysis_manager import analyze_photos_and_pairs
from ..core.exif_sorter import get_exif_timestamp
from ..core.perf_log import PerfStats
from .burst_review import BurstReviewFrame
from .keeper_grid import KeeperGridFrame
from .settings_panel import open_settings, DEFAULT_SETTINGS

logger = logging.getLogger("pba.gui")


def main():
    app = App()
    app.mainloop()


# ── Default session settings ──────────────────────────────────────────────────

def _make_settings():
    return dict(DEFAULT_SETTINGS)


def _settings_to_scoring(s: dict) -> tuple[dict, dict]:
    """Split app settings into (scoring_settings, scoring_weights) dicts."""
    scoring_settings = {
        "use_face_detection": s.get("use_face_detection", True),
        "top_tile_pct": s.get("top_tile_pct", 20) / 100.0,
        "tile_count": 8,
    }
    scoring_weights = {
        "sharpness": s.get("sharpness_weight", 50),
        "exposure": s.get("exposure_weight", 30),
    }
    return scoring_settings, scoring_weights


# ── App ───────────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Photo Burst Analyzer")
        self.geometry("1280x860")
        self.configure(bg="#1a1a1a")

        self._settings = _make_settings()
        self._bursts: list = []        # multi-photo burst dicts; written on main thread
        self._single_bursts: list = [] # 1-photo dicts for images not in any burst
        self._kept_paths: set = set()
        self._input_dir: str = ""

        # Re-entrancy guard: set True while the analysis thread is alive.
        # Read and written only on the main thread (set before thread starts,
        # cleared via after() inside the worker's finally block).
        self._analysis_running: bool = False

        # Reference to the live BurstReviewFrame so we can call cleanup()
        # before destroying it (removes root-window key bindings).
        self._burst_review_frame: BurstReviewFrame | None = None

        self._build_chrome()
        self._show_welcome()

    # ── Chrome (persistent header) ────────────────────────────────────────────

    def _build_chrome(self):
        nav = tk.Frame(self, bg="#111", pady=0)
        nav.pack(fill="x")

        self._app_lbl = tk.Label(nav, text="Photo Burst Analyzer", bg="#111", fg="#eee",
                                 font=("Arial", 14, "bold"))
        self._app_lbl.pack(side="left", padx=14, pady=8)

        self._funnel_lbl = tk.Label(nav, text="", bg="#111", fg="#aaa", font=("Arial", 10))
        self._funnel_lbl.pack(side="left", padx=20)

        self._stage_lbl = tk.Label(nav, text="", bg="#111", fg="#888", font=("Arial", 10))
        self._stage_lbl.pack(side="left", padx=12)

        # Use tk.Label for nav buttons — tk.Button with custom bg/fg renders
        # invisible text on macOS until clicked. Labels always paint immediately.
        tk.Label(nav, text="⚙  Settings", bg="#333", fg="#eee", font=("Arial", 10),
                 padx=8, pady=4, cursor="hand2").pack(side="right", padx=10, pady=6)
        nav.winfo_children()[-1].bind("<Button-1>", lambda e: self._open_settings())

        self._new_folder_btn = tk.Label(
            nav, text="⟳  New Folder", bg="#333", fg="#eee", font=("Arial", 10),
            padx=8, pady=4, cursor="hand2")
        self._new_folder_btn.pack(side="right", padx=4, pady=6)
        self._new_folder_btn.bind("<Button-1>", lambda e: self._new_folder())
        self._folder_btn_enabled = True

        self._content = tk.Frame(self, bg="#1a1a1a")
        self._content.pack(fill="both", expand=True)

    def _clear_content(self):
        """Destroy content children, cleaning up any active stage first."""
        # Give the active BurstReviewFrame a chance to remove its root bindings
        # before the frame is destroyed.
        if self._burst_review_frame is not None:
            try:
                self._burst_review_frame.cleanup()
            except Exception:
                pass
            self._burst_review_frame = None
        for w in self._content.winfo_children():
            w.destroy()

    # ── Welcome / loading screens ─────────────────────────────────────────────

    def _show_welcome(self):
        self._stage_lbl.config(text="")
        self._clear_content()
        frame = tk.Frame(self._content, bg="#1a1a1a")
        frame.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(frame, text="📷", font=("Arial", 48), bg="#1a1a1a").pack(pady=8)
        tk.Label(frame, text="Select a folder of photos to begin",
                 font=("Arial", 16), fg="#ccc", bg="#1a1a1a").pack()
        tk.Label(frame, text="Bursts will be detected and ranked automatically",
                 font=("Arial", 11), fg="#777", bg="#1a1a1a").pack(pady=(4, 20))
        tk.Button(frame, text="  Select Photo Folder  ", font=("Arial", 13),
                  bg="#3cb371", fg="white", relief="flat", padx=16, pady=8,
                  command=self._new_folder).pack()

    def _show_loading(self, total_tasks: int):
        self._clear_content()
        frame = tk.Frame(self._content, bg="#1a1a1a")
        frame.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(frame, text="Analysing photos…", font=("Arial", 14), fg="#ccc",
                 bg="#1a1a1a").pack(pady=(0, 16))

        self._progress_bar = ttk.Progressbar(frame, orient="horizontal", length=400,
                                             mode="determinate", maximum=max(1, total_tasks))
        self._progress_bar.pack()

        self._progress_lbl = tk.Label(frame, text="", font=("Arial", 10), fg="#888",
                                      bg="#1a1a1a")
        self._progress_lbl.pack(pady=6)

        self._worker_lbl = tk.Label(frame, text="", font=("Arial", 9), fg="#666",
                                    bg="#1a1a1a")
        self._worker_lbl.pack()

    # ── Stage transitions ─────────────────────────────────────────────────────

    def _show_burst_review(self):
        self._stage_lbl.config(text="Stage 1 of 2: Burst Review")
        self._clear_content()
        frame = BurstReviewFrame(
            self._content,
            bursts=self._bursts,
            on_stage_complete=self._on_burst_review_done,
            settings=self._settings,
        )
        frame.pack(fill="both", expand=True)
        self._burst_review_frame = frame

    def _on_burst_review_done(self, kept_paths: set):
        self._burst_review_frame = None  # frame is calling back, it will self-clean
        # Automatically include all single photos (not part of any burst)
        for b in self._single_bursts:
            kept_paths.add(b["burst"][0])
        self._kept_paths = kept_paths
        total = sum(len(b["burst"]) for b in self._bursts)
        self._update_funnel(
            total=total,
            after_stage1=len(kept_paths),
            singles=len(self._single_bursts),
        )
        self._show_keeper_grid()

    def _show_keeper_grid(self):
        self._stage_lbl.config(text="Stage 2 of 2: Final Selection")
        self._clear_content()
        # Pass burst photos + single photos together so keeper grid orders them correctly
        all_bursts = self._bursts + self._single_bursts
        frame = KeeperGridFrame(
            self._content,
            kept_paths=self._kept_paths,
            all_bursts=all_bursts,
            on_export_done=self._on_export_done,
            settings=self._settings,
        )
        frame.pack(fill="both", expand=True)

    def _on_export_done(self, count: int, dest: str):
        self._stage_lbl.config(text=f"Exported {count} photos")

    # ── Funnel counter ────────────────────────────────────────────────────────

    def _update_funnel(self, total: int, after_stage1: int = None, singles: int = 0):
        parts = [f"Loaded: {total:,}"]
        if singles:
            parts.append(f"Singles (auto-kept): {singles:,}")
        if after_stage1 is not None:
            parts.append(f"After burst review: {after_stage1:,}")
        self._funnel_lbl.config(text="   |   ".join(parts))

    # ── Folder selection & analysis ───────────────────────────────────────────

    def _new_folder(self):
        if self._analysis_running:
            messagebox.showinfo(
                "Analysis in progress",
                "Please wait for the current analysis to finish.")
            return
        d = filedialog.askdirectory(title="Select photo folder")
        if not d:
            return
        self._input_dir = d
        self._start_analysis(d)

    def _start_analysis(self, directory: str):
        # Guard set on the main thread before the worker thread starts.
        self._analysis_running = True
        self._new_folder_btn.config(fg="#666", cursor="arrow")
        self._new_folder_btn.unbind("<Button-1>")
        self._folder_btn_enabled = False

        self._show_loading(0)
        self._stage_lbl.config(text="Analysing…")
        t = self._settings.get("burst_threshold", 1.0)
        s_settings, s_weights = _settings_to_scoring(self._settings)
        max_w = self._settings.get("max_workers", 0) or None

        threading.Thread(
            target=self._analyze_worker,
            args=(directory, t, s_settings, s_weights, max_w),
            daemon=True,
        ).start()

    def _analyze_worker(self, directory, threshold, s_settings, s_weights, max_workers):
        """Runs on a background thread. Never touches Tkinter widgets directly."""
        import os as _os
        perf = PerfStats("Photo Burst Analyzer")
        n_workers_used = max(1, min(int(max_workers or (_os.cpu_count() or 4)), 32))
        augmented = None

        try:
            # ── Phase 1: Image collection ─────────────────────────────────────
            with perf.phase("Image collection (os.walk)"):
                files = collect_images(directory)

            if not files:
                self.after(0, lambda: messagebox.showwarning(
                    "No images", f"No supported images found in:\n{directory}"))
                self.after(0, self._show_welcome)
                return

            # ── Phase 2: EXIF extraction ──────────────────────────────────────
            photos = []
            with perf.phase("EXIF extraction", count=len(files)):
                for f in files:
                    ts = get_exif_timestamp(f)
                    if ts is not None:
                        photos.append((f, ts))

            if not photos:
                self.after(0, lambda: messagebox.showwarning(
                    "No EXIF timestamps",
                    "No photos with EXIF timestamps found.\n"
                    "Burst detection requires DateTimeOriginal in EXIF."))
                self.after(0, self._show_welcome)
                return

            # ── Phase 3: Burst detection ──────────────────────────────────────
            with perf.phase("Burst detection", count=len(photos)):
                candidates = detect_candidates(photos, threshold)

            # Any image file not in a burst (including files with no EXIF) goes
            # straight to the keeper grid without needing burst review.
            burst_paths = {p for c in candidates for p, _ in c}
            all_file_paths = set(files)
            # Files with EXIF but outside every burst
            single_paths = {p for p, _ in photos if p not in burst_paths}
            # Files without EXIF timestamps at all
            no_exif_paths = all_file_paths - {p for p, _ in photos}
            single_paths.update(no_exif_paths)

            if not candidates:
                # No bursts at all — put everything in keeper grid as singles
                all_singles = [{"burst": [p], "blur_scores": [None],
                                "exposures": [None], "composites": [None],
                                "has_faces": [False], "sads": [None],
                                "best_idx": 0, "proc_time": 0.0, "avg_proc_time": 0.0}
                               for p in sorted(single_paths)]
                self.after(0, lambda s=all_singles: self._on_analysis_complete([], s))
                return

            total_photos = sum(len(c) for c in candidates)
            total_pairs = sum(len(c) - 1 for c in candidates)
            total_tasks = total_photos + total_pairs

            self.after(0, lambda: self._show_loading(total_tasks))
            self.after(0, lambda: self._update_funnel(total=len(files)))

            def progress_cb(completed, total, pcounts, cores):
                nonlocal n_workers_used
                n_workers_used = cores
                self.after(0, lambda: self._update_loading_progress(completed, total, pcounts, cores))

            # ── Phase 4: Scoring (blur + exposure + SAD) ──────────────────────
            with perf.phase("Scoring (blur + exposure + SAD)", count=total_photos + total_pairs):
                augmented = analyze_photos_and_pairs(
                    candidates,
                    do_blur=True,
                    do_sad=True,
                    max_workers=max_workers,
                    progress_callback=progress_cb,
                    settings=s_settings,
                    weights=s_weights,
                    perf=perf,
                )

            # ── Emit full performance report ──────────────────────────────────
            perf.report(
                n_photos=total_photos,
                n_bursts=len(candidates),
                n_workers=n_workers_used,
                directory=directory,
            )

            # Build single-photo burst dicts for images outside any burst.
            single_burst_dicts = [
                {"burst": [p], "blur_scores": [None], "exposures": [None],
                 "composites": [None], "has_faces": [False], "sads": [None],
                 "best_idx": 0, "proc_time": 0.0, "avg_proc_time": 0.0}
                for p in sorted(single_paths)
            ]

            # Hand results to the main thread; self._bursts is assigned there,
            # so BurstReviewFrame always reads a fully initialised value.
            self.after(0, lambda a=augmented, s=single_burst_dicts:
                       self._on_analysis_complete(a, s))

        except Exception as e:
            logger.exception("Analysis failed")
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
            self.after(0, self._show_welcome)

        finally:
            # Always release the guard on the main thread so the button
            # re-enables regardless of success, early return, or exception.
            self.after(0, self._release_analysis_guard)

    def _on_analysis_complete(self, augmented: list, single_bursts: list = None):
        """Runs on the main thread. Safe to assign instance state."""
        self._bursts = augmented
        self._single_bursts = single_bursts or []
        n_singles = len(self._single_bursts)
        if n_singles:
            total = sum(len(b["burst"]) for b in self._bursts)
            self._update_funnel(total=total, singles=n_singles)
        if self._bursts:
            self._show_burst_review()
        else:
            # Only singles — skip burst review entirely
            self._kept_paths = {b["burst"][0] for b in self._single_bursts}
            self._show_keeper_grid()

    def _release_analysis_guard(self):
        """Runs on the main thread. Resets the re-entrancy guard."""
        self._analysis_running = False
        self._new_folder_btn.config(fg="#eee", cursor="hand2")
        self._new_folder_btn.bind("<Button-1>", lambda e: self._new_folder())
        self._folder_btn_enabled = True

    def _update_loading_progress(self, completed, total, pcounts, cores):
        try:
            self._progress_bar["maximum"] = max(1, total)
            self._progress_bar["value"] = completed
            pct = int(completed / max(1, total) * 100)
            self._progress_lbl.config(text=f"{completed} / {total} tasks  ({pct}%)")
            self._worker_lbl.config(text=f"{cores} worker threads")
        except Exception:
            pass

    # ── Settings ──────────────────────────────────────────────────────────────

    def _open_settings(self):
        self._settings = open_settings(self, self._settings)
