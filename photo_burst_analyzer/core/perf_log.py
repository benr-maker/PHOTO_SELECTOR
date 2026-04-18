"""photo_burst_analyzer.core.perf_log

Developer performance logger.

Usage
-----
    stats = PerfStats()

    with stats.phase("EXIF extraction"):
        ...

    with stats.io_phase(est_bytes=file_size):
        image = Image.open(path)

    stats.report(n_photos=7000, n_bursts=312, n_workers=8)

All timing is wall-clock via time.perf_counter().
CPU time is measured at the process level (time.process_time()), which
accumulates across all threads — a value > 100 % of wall time confirms
multi-core parallelism is working.
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger("pba.perf")


# ── Phase record ──────────────────────────────────────────────────────────────

@dataclass
class PhaseRecord:
    wall: float = 0.0      # accumulated wall seconds
    count: int = 0         # number of operations timed


# ── PerfStats ─────────────────────────────────────────────────────────────────

class PerfStats:
    """Thread-safe performance statistics accumulator."""

    def __init__(self, label: str = ""):
        self._label = label
        self._lock = threading.Lock()
        self._phases: dict[str, PhaseRecord] = {}
        self._io_wall: float = 0.0
        self._io_bytes: int = 0
        self._wall_start = time.perf_counter()
        self._cpu_start = time.process_time()
        self._run_date = datetime.now()

    # ── Context managers ──────────────────────────────────────────────────────

    @contextmanager
    def phase(self, name: str, count: int = 1):
        """Time a named phase block. Thread-safe; accumulates across calls."""
        t0 = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - t0
            self._record_phase(name, elapsed, count)

    @contextmanager
    def io_phase(self, est_bytes: int = 0):
        """Time a file I/O block and accumulate byte count."""
        t0 = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - t0
            with self._lock:
                self._io_wall += elapsed
                self._io_bytes += est_bytes

    # ── Manual recording (for worker threads returning dicts) ─────────────────

    def record_phase(self, name: str, wall: float, count: int = 1):
        self._record_phase(name, wall, count)

    def record_io(self, wall: float, bytes_read: int = 0):
        with self._lock:
            self._io_wall += wall
            self._io_bytes += bytes_read

    # ── Internal ──────────────────────────────────────────────────────────────

    def _record_phase(self, name: str, wall: float, count: int):
        with self._lock:
            if name not in self._phases:
                self._phases[name] = PhaseRecord()
            self._phases[name].wall += wall
            self._phases[name].count += count

    # ── Report ────────────────────────────────────────────────────────────────

    def report(
        self,
        n_photos: int = 0,
        n_bursts: int = 0,
        n_workers: int = 1,
        directory: str = "",
    ) -> str:
        total_wall = time.perf_counter() - self._wall_start
        total_cpu = time.process_time() - self._cpu_start
        cpu_util_pct = (total_cpu / max(total_wall, 1e-6)) * 100.0

        W = 62
        lines: list[str] = []

        def bar(ch="─"): lines.append(ch * W)
        def hdr(ch="═"): lines.append(ch * W)
        def row(label, value, unit="", note=""):
            note_str = f"  ({note})" if note else ""
            lines.append(f"  {label:<30} {value:>12} {unit:<6}{note_str}")

        hdr()
        lines.append(f"  PERFORMANCE REPORT  –  {self._label or 'Photo Burst Analyzer'}")
        hdr()
        row("Run date", self._run_date.strftime("%Y-%m-%d  %H:%M:%S"))
        if directory:
            # Truncate long paths
            d = directory if len(directory) <= 46 else "…" + directory[-45:]
            row("Directory", d)
        bar()

        # Input summary
        lines.append("  INPUT")
        row("Photos found", f"{n_photos:,}", "photos")
        row("Bursts detected", f"{n_bursts:,}", "bursts",
            f"{n_photos / max(n_bursts, 1):.1f} photos/burst avg")
        row("Worker threads", f"{n_workers:,}")
        bar()

        # Elapsed time
        lines.append("  ELAPSED TIME")
        row("Total wall time", f"{total_wall:.3f}", "s")
        row("Total CPU time", f"{total_cpu:.3f}", "s",
            f"{cpu_util_pct:.0f}% CPU util – "
            + ("multi-core active" if cpu_util_pct > 120 else "single-core"))
        bar()

        # Phase breakdown
        if self._phases:
            lines.append("  PHASE BREAKDOWN")
            lines.append(
                f"  {'Phase':<28} {'Wall (s)':>9}  {'% wall':>6}  {'ops/s':>9}  {'count':>7}"
            )
            bar()
            sorted_phases = sorted(self._phases.items(), key=lambda x: -x[1].wall)
            for name, rec in sorted_phases:
                pct = rec.wall / max(total_wall, 1e-6) * 100.0
                rate = rec.count / max(rec.wall, 1e-6)
                lines.append(
                    f"  {name:<28} {rec.wall:>9.3f}  {pct:>5.1f}%  {rate:>9.1f}  {rec.count:>7,}"
                )

            # Unaccounted time
            phase_total = sum(r.wall for r in self._phases.values())
            unaccounted = total_wall - phase_total
            if unaccounted > 0.05:
                pct = unaccounted / max(total_wall, 1e-6) * 100.0
                lines.append(f"  {'(overhead / UI / other)':<28} {unaccounted:>9.3f}  {pct:>5.1f}%")
            bar()

        # I/O summary
        lines.append("  I/O SUMMARY")
        io_pct = self._io_wall / max(total_wall, 1e-6) * 100.0
        row("Total I/O wall time", f"{self._io_wall:.3f}", "s",
            f"{io_pct:.1f}% of wall time")
        compute_wall = total_wall - self._io_wall
        row("Est. compute wall time", f"{compute_wall:.3f}", "s",
            f"{100.0 - io_pct:.1f}% of wall time")
        if self._io_bytes > 0:
            mb = self._io_bytes / 1_000_000
            mb_per_s = mb / max(self._io_wall, 1e-6)
            row("Total data read", f"{mb:.1f}", "MB")
            row("I/O throughput", f"{mb_per_s:.1f}", "MB/s")
        bar()

        # Throughput
        lines.append("  THROUGHPUT")
        if n_photos > 0:
            photos_per_s = n_photos / max(total_wall, 1e-6)
            ms_per_photo = total_wall / n_photos * 1000.0
            row("Overall rate", f"{photos_per_s:.2f}", "photos/s")
            row("Time per photo", f"{ms_per_photo:.1f}", "ms/photo")
            if n_workers > 1:
                row("Effective rate/worker", f"{photos_per_s / n_workers:.2f}", "photos/s/worker")
        hdr()

        report_str = "\n".join(lines)
        for line in lines:
            logger.info(line)

        return report_str
