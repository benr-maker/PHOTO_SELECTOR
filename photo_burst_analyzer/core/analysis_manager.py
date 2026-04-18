"""photo_burst_analyzer.core.analysis_manager

ThreadPoolExecutor-based analysis coordinator.
Passes scoring settings and weights to workers; aggregates per-worker timing
into a PerfStats report logged at INFO level when analysis completes.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import time
import logging

from .blur_sad_analysis import task_blur, task_sad, DEFAULT_SETTINGS, DEFAULT_WEIGHTS
from .perf_log import PerfStats

logger = logging.getLogger("pba.manager")


def analyze_photos_and_pairs(
    bursts,
    do_blur=True,
    do_sad=True,
    max_workers=None,
    progress_callback=None,
    settings=None,
    weights=None,
    perf: PerfStats = None,
):
    """Compute per-photo blur/exposure/composite scores and per-pair SAD scores.

    bursts:            list[ list[ (path, meta) ] ]
    progress_callback: callable(completed, total, thread_counts, n_workers)
    settings:          scoring settings dict
    weights:           scoring weights dict
    perf:              optional PerfStats to record phases into (created internally if None)

    Returns list of burst dicts:
      { burst, blur_scores, exposures, composites, sads, best_idx, has_faces }
    """
    s = settings or DEFAULT_SETTINGS
    w = weights or DEFAULT_WEIGHTS

    # Use caller-supplied stats if provided, else create a local one
    _own_perf = perf is None
    if _own_perf:
        perf = PerfStats("Analysis")

    # ── Collect unique photos and pairs ───────────────────────────────────────
    photo_paths, pairs = [], []
    seen = set()
    for burst in bursts:
        paths = [p for p, _ in burst]
        for p in paths:
            if p not in seen:
                seen.add(p)
                photo_paths.append(p)
        for a, b in zip(paths, paths[1:]):
            pairs.append((a, b))

    total_tasks = (len(photo_paths) if do_blur else 0) + (len(pairs) if do_sad else 0)

    if total_tasks == 0:
        return _empty_augmented(bursts)

    results_blur: dict = {}
    results_sad: dict = {}

    # Timing accumulators (summed across all workers)
    acc_blur_io = 0.0
    acc_blur_compute = 0.0
    acc_blur_io_bytes = 0
    acc_sad_io = 0.0
    acc_sad_compute = 0.0
    acc_sad_io_bytes = 0

    completed = 0
    n_workers = max(1, min(int(max_workers or (os.cpu_count() or 4)), 32))
    thread_counts: dict = {}

    wall_start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=n_workers) as ex:
        futures = {}
        if do_blur:
            for p in photo_paths:
                futures[ex.submit(task_blur, (p, s, w))] = ("blur", p)
        if do_sad:
            for pair in pairs:
                futures[ex.submit(task_sad, pair)] = ("sad", pair)

        # NOTE: as_completed() yields futures one-at-a-time in the CALLING thread.
        # The loop body is sequential — no concurrent access to the accumulator
        # variables or result dicts below, so no lock is required here.
        for fut in as_completed(futures):
            kind, key = futures[fut]
            try:
                res = fut.result()
                if res.get("type") == "blur":
                    results_blur[res["path"]] = res
                    acc_blur_io += res.get("_t_io", 0.0)
                    acc_blur_compute += res.get("_t_compute", 0.0)
                    acc_blur_io_bytes += res.get("_io_bytes", 0)
                else:
                    path_a = res.get("path") or (key[0] if isinstance(key, tuple) else key)
                    path_b = res.get("reference_path") or (key[1] if isinstance(key, tuple) else None)
                    results_sad[(path_a, path_b)] = res.get("value")
                    acc_sad_io += res.get("_t_io", 0.0)
                    acc_sad_compute += res.get("_t_compute", 0.0)
                    acc_sad_io_bytes += res.get("_io_bytes", 0)
            except Exception:
                logger.exception("worker task failed for %s", key)
            finally:
                completed += 1
                if progress_callback:
                    try:
                        thread_counts["thread"] = completed
                        progress_callback(completed, total_tasks, dict(thread_counts), n_workers)
                    except Exception:
                        pass

    analysis_wall = time.perf_counter() - wall_start

    # ── Record phases in PerfStats ────────────────────────────────────────────
    if do_blur and photo_paths:
        perf.record_phase("Sharpness scoring", acc_blur_compute, count=len(photo_paths))
        perf.record_io(acc_blur_io, bytes_read=acc_blur_io_bytes)

    if do_sad and pairs:
        perf.record_phase("SAD (similarity) scoring", acc_sad_compute, count=len(pairs))
        perf.record_io(acc_sad_io, bytes_read=acc_sad_io_bytes)

    # Exposure scoring time is already inside acc_blur_compute but we separate it
    # for reporting by subtracting a rough estimate.  For a clean separation
    # task_blur embeds both in _t_compute; report them combined as "Scoring (blur+exposure)".

    # ── Assemble augmented burst dicts ────────────────────────────────────────
    augmented = []
    for burst in bursts:
        paths = [p for p, _ in burst]
        blur_list = [results_blur.get(p, {}).get("value") for p in paths] if do_blur else [None] * len(paths)
        exp_list = [results_blur.get(p, {}).get("exposure") for p in paths] if do_blur else [None] * len(paths)
        comp_list = [results_blur.get(p, {}).get("composite") for p in paths] if do_blur else [None] * len(paths)
        face_list = [bool(results_blur.get(p, {}).get("has_face")) for p in paths] if do_blur else [False] * len(paths)
        sad_list = (
            [results_sad.get((a, b)) for a, b in zip(paths, paths[1:])] if do_sad else [None] * (len(paths) - 1)
        ) + [None]

        valid_comps = [(i, c) for i, c in enumerate(comp_list) if c is not None]
        best_idx = max(valid_comps, key=lambda x: x[1])[0] if valid_comps else 0

        augmented.append({
            "burst": paths,
            "blur_scores": blur_list,
            "exposures": exp_list,
            "composites": comp_list,
            "has_faces": face_list,
            "sads": sad_list,
            "best_idx": best_idx,
            "proc_time": analysis_wall,
            "avg_proc_time": analysis_wall / max(len(photo_paths), 1),
        })

    # Log a summary line at manager level (full report emitted by caller)
    logger.info(
        "analysis_manager: %d photos, %d pairs — wall %.2fs, "
        "blur I/O %.2fs, blur compute %.2fs, SAD I/O %.2fs, SAD compute %.2fs, "
        "%d workers",
        len(photo_paths), len(pairs),
        analysis_wall,
        acc_blur_io, acc_blur_compute,
        acc_sad_io, acc_sad_compute,
        n_workers,
    )

    return augmented


def _empty_augmented(bursts):
    result = []
    for burst in bursts:
        paths = [p for p, _ in burst]
        n = len(paths)
        result.append({
            "burst": paths,
            "blur_scores": [None] * n,
            "exposures": [None] * n,
            "composites": [None] * n,
            "has_faces": [False] * n,
            "sads": [None] * n,
            "best_idx": 0,
            "proc_time": 0.0,
            "avg_proc_time": 0.0,
        })
    return result
