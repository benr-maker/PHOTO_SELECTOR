from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing, os, logging
from .blur_sad_analysis import task_blur, task_sad
logger = logging.getLogger('pba.manager')

def analyze_photos_and_pairs(bursts, do_blur=True, do_sad=True, max_workers=None, progress_callback=None):
    photo_paths = []
    pairs = []
    for b in bursts:
        paths = [p for p, _ in b]
        photo_paths.extend(paths)
        for a, bp in zip(paths, paths[1:]):
            pairs.append((a, bp))
    seen = set(); unique_photos = []
    for p in photo_paths:
        if p not in seen:
            seen.add(p); unique_photos.append(p)
    total_tasks = (len(unique_photos) if do_blur else 0) + (len(pairs) if do_sad else 0)
    if total_tasks == 0:
        augmented = []
        for b in bursts:
            paths = [p for p, _ in b]
            augmented.append({'burst': paths, 'blur_scores': [None]*len(paths), 'sads': [None]*len(paths)})
        return augmented
    manager = multiprocessing.Manager()
    per_pid_counts = manager.dict()
    results_blur = {}
    results_sad = {}
    completed = 0
    cores = max_workers or (os.cpu_count() or 1)
    with ProcessPoolExecutor(max_workers=cores) as ex:
        futures = {}
        if do_blur:
            for p in unique_photos:
                fut = ex.submit(task_blur, p)
                futures[fut] = ('blur', p)
        if do_sad:
            for pair in pairs:
                fut = ex.submit(task_sad, pair)
                futures[fut] = ('sad', pair)
        for fut in as_completed(futures):
            try:
                res = fut.result()
                pid = res.get('pid')
                per_pid_counts[pid] = per_pid_counts.get(pid, 0) + 1
                if res.get('type') == 'blur':
                    results_blur[res['path']] = res['value']
                else:
                    results_sad[(res['path_a'], res['path_b'])] = res['value']
            except Exception:
                logger.exception('worker task failed')
            finally:
                completed += 1
                if progress_callback:
                    try:
                        pcounts = dict(per_pid_counts)
                    except Exception:
                        pcounts = {}
                    progress_callback(completed, total_tasks, pcounts, cores)
    augmented = []
    for b in bursts:
        paths = [p for p, _ in b]
        blur_list = [results_blur.get(p) for p in paths] if do_blur else [None]*len(paths)
        sad_list = [results_sad.get((a, b)) for a, b in zip(paths, paths[1:])] if do_sad else [None]*(len(paths)-1)
        sad_list = sad_list + [None]
        augmented.append({'burst': paths, 'blur_scores': blur_list, 'sads': sad_list, 'proc_time': None, 'avg_proc_time': None})
    return augmented
