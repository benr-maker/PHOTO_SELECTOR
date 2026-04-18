"""photo_burst_analyzer.core.blur_sad_analysis

Enhanced image quality scoring:
- Tile-based sharpness (top-N% of tiles) handles bokeh/vignette correctly
- Face detection via OpenCV Haar cascade with tile-based fallback
- Exposure quality via histogram analysis
- Weighted composite score with configurable weights
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Optional

from PIL import Image, ImageChops, ImageOps, ImageStat, ImageFilter

logger = logging.getLogger("pba.scoring")

DEFAULT_WEIGHTS = {"sharpness": 50, "exposure": 30}
DEFAULT_SETTINGS = {
    "use_face_detection": True,
    "top_tile_pct": 0.20,
    "tile_count": 8,
}

# Cascade initialisation uses double-checked locking so the OpenCV load
# happens at most once, even when many worker threads call simultaneously.
# The lock ensures _face_cascade is fully assigned before _cascade_checked
# is set to True — preventing any thread from reading a half-initialised value.
_cascade_lock = threading.Lock()
_face_cascade = None
_cascade_checked = False


def _get_face_cascade():
    """Return the cached Haar cascade, loading it on first call (thread-safe)."""
    global _face_cascade, _cascade_checked
    # Fast path — already initialised; no lock needed for a plain bool read.
    if _cascade_checked:
        return _face_cascade
    with _cascade_lock:
        # Re-check inside the lock: another thread may have initialised while
        # we were waiting to acquire it.
        if _cascade_checked:
            return _face_cascade
        try:
            import cv2
            path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            cas = cv2.CascadeClassifier(path)
            _face_cascade = None if cas.empty() else cas
        except Exception as e:
            logger.debug("OpenCV face cascade unavailable: %s", e)
            _face_cascade = None
        finally:
            # Set the flag last, inside the lock, so that the fast-path read
            # above is safe: if _cascade_checked is True, _face_cascade is
            # already fully assigned.
            _cascade_checked = True
    return _face_cascade


def _open_gray(path: str, max_side: int = 1200) -> Image.Image:
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)
    im = im.convert("L")
    w, h = im.size
    m = max(w, h)
    if m > max_side and m > 0:
        scale = max_side / float(m)
        im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
    return im


def _laplacian_var(gray_im: Image.Image) -> float:
    try:
        lap = gray_im.filter(
            ImageFilter.Kernel(
                size=(3, 3),
                kernel=[-1., -1., -1., -1., 8., -1., -1., -1., -1.],
                scale=1.0, offset=0.0,
            )
        )
    except Exception:
        lap = gray_im.filter(ImageFilter.FIND_EDGES)
    stat = ImageStat.Stat(lap)
    return float(stat.var[0]) if stat.var else 0.0


def tile_sharpness(gray_im: Image.Image, tiles: int = 8, top_pct: float = 0.20) -> float:
    """Mean Laplacian variance of the top-scoring tiles.

    Ignores low-sharpness background/bokeh regions automatically.
    """
    w, h = gray_im.size
    tw, th = max(1, w // tiles), max(1, h // tiles)
    scores = []
    for row in range(tiles):
        for col in range(tiles):
            x0, y0 = col * tw, row * th
            tile = gray_im.crop((x0, y0, min(x0 + tw, w), min(y0 + th, h)))
            scores.append(_laplacian_var(tile))
    if not scores:
        return 0.0
    scores.sort(reverse=True)
    n = max(1, int(len(scores) * top_pct))
    return float(sum(scores[:n]) / n)


def face_sharpness(gray_im: Image.Image) -> Optional[float]:
    """Laplacian variance of the sharpest detected face region.

    Returns None if no faces detected or OpenCV unavailable.
    """
    cascade = _get_face_cascade()
    if cascade is None:
        return None
    try:
        import cv2
        import numpy as np
        arr = np.array(gray_im)
        faces = cascade.detectMultiScale(arr, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        if not len(faces):
            return None
        scores = []
        for (x, y, fw, fh) in faces:
            region = gray_im.crop((x, y, x + fw, y + fh))
            scores.append(_laplacian_var(region))
        return float(max(scores))
    except Exception as e:
        logger.debug("Face sharpness failed: %s", e)
        return None


def blur_score(path: str, settings: Optional[dict] = None) -> tuple[float, bool]:
    """Sharpness score + whether a face was used for scoring.

    Returns (score, has_face). Higher score = sharper.
    Uses face detection first, falls back to tile-based.
    """
    s = settings or DEFAULT_SETTINGS
    gray = _open_gray(path)
    if s.get("use_face_detection", True):
        fs = face_sharpness(gray)
        if fs is not None:
            return fs, True
    tiles = s.get("tile_count", 8)
    pct = s.get("top_tile_pct", 0.20)
    return tile_sharpness(gray, tiles=tiles, top_pct=pct), False


def exposure_score(path: str) -> float:
    """Exposure quality 0-100. Penalises clipping; rewards balanced histogram."""
    try:
        im = Image.open(path)
        im = ImageOps.exif_transpose(im)
        im = im.convert("L")
        im.thumbnail((400, 400))
        hist = im.histogram()
        total = sum(hist) or 1
        shadow_clip = sum(hist[:5]) / total
        highlight_clip = sum(hist[250:]) / total
        clip_penalty = (shadow_clip + highlight_clip) * 200
        stat = ImageStat.Stat(im)
        mean = stat.mean[0]
        stddev = stat.stddev[0]
        center_penalty = abs(mean - 128) / 128 * 30
        contrast_bonus = min(20.0, stddev / 5.0)
        return float(max(0.0, min(100.0, 80.0 - clip_penalty - center_penalty + contrast_bonus)))
    except Exception:
        return 50.0


def sad_score(path: str, reference_path: str) -> float:
    """Normalised mean absolute pixel difference vs. reference. Lower = more similar."""
    a = _open_gray(reference_path)
    b = _open_gray(path)
    if a.size != b.size:
        b = b.resize(a.size, Image.Resampling.BILINEAR)
    diff = ImageChops.difference(a, b)
    stat = ImageStat.Stat(diff)
    return float(stat.mean[0]) if stat.mean else 0.0


def composite_score(blur: float, exposure: float, weights: dict) -> float:
    """Weighted composite 0-100. Blur is normalised on a log-like curve."""
    w_sharp = float(weights.get("sharpness", 50))
    w_exp = float(weights.get("exposure", 30))
    total_w = w_sharp + w_exp
    if total_w == 0:
        return 0.0
    # Map blur (Laplacian var) to 0-100: sqrt curve, ~1000 var → ~100
    norm_blur = min(100.0, (blur ** 0.5) * 3.16)
    return float((norm_blur * w_sharp + exposure * w_exp) / total_w)


@dataclass
class ScoreResult:
    path: str
    blur: float
    exposure: float
    composite: float
    has_face: bool
    sad: Optional[float] = None


def score_photo(path: str, settings: Optional[dict] = None, weights: Optional[dict] = None) -> ScoreResult:
    s = settings or DEFAULT_SETTINGS
    w = weights or DEFAULT_WEIGHTS
    blur, has_face = blur_score(path, s)
    exp = exposure_score(path)
    comp = composite_score(blur, exp, w)
    return ScoreResult(path=path, blur=blur, exposure=exp, composite=comp, has_face=has_face)


# ── Worker-friendly wrappers ────────────────────────────────────────────────

def task_blur(args) -> dict:
    """Thread worker: score one photo. args = (path, settings, weights).

    Returns timing fields prefixed with '_t_' for aggregation by the caller:
      _t_io       – wall seconds spent opening/decoding image files
      _t_compute  – wall seconds spent on sharpness + exposure computation
      _io_bytes   – estimated bytes read (file size)
    """
    if isinstance(args, (tuple, list)):
        path = args[0]
        settings = args[1] if len(args) > 1 else DEFAULT_SETTINGS
        weights = args[2] if len(args) > 2 else DEFAULT_WEIGHTS
    else:
        path, settings, weights = args, DEFAULT_SETTINGS, DEFAULT_WEIGHTS

    t_io = 0.0
    t_compute = 0.0
    io_bytes = 0

    # ── I/O + decode ─────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    gray = _open_gray(path)
    t_io += time.perf_counter() - t0
    try:
        io_bytes += os.path.getsize(path)
    except OSError:
        pass

    # ── Sharpness computation ─────────────────────────────────────────────────
    has_face = False
    fs = None
    t1 = time.perf_counter()
    if settings.get("use_face_detection", True):
        fs = face_sharpness(gray)
        has_face = fs is not None
    blur = fs if fs is not None else tile_sharpness(
        gray,
        tiles=settings.get("tile_count", 8),
        top_pct=settings.get("top_tile_pct", 0.20),
    )
    t_compute += time.perf_counter() - t1

    # ── Exposure (separate file open + histogram) ─────────────────────────────
    t2 = time.perf_counter()
    try:
        im = Image.open(path)
        im = ImageOps.exif_transpose(im)
        im = im.convert("L")
        t_io += time.perf_counter() - t2          # open/decode counted as I/O
        try:
            io_bytes += os.path.getsize(path)     # counted twice (two opens); acceptable
        except OSError:
            pass

        t3 = time.perf_counter()
        im.thumbnail((400, 400))
        hist = im.histogram()
        total = sum(hist) or 1
        shadow_clip = sum(hist[:5]) / total
        highlight_clip = sum(hist[250:]) / total
        clip_penalty = (shadow_clip + highlight_clip) * 200
        from PIL import ImageStat as _IStat
        stat = _IStat.Stat(im)
        mean = stat.mean[0]
        stddev = stat.stddev[0]
        center_penalty = abs(mean - 128) / 128 * 30
        contrast_bonus = min(20.0, stddev / 5.0)
        exp = float(max(0.0, min(100.0, 80.0 - clip_penalty - center_penalty + contrast_bonus)))
        t_compute += time.perf_counter() - t3
    except Exception:
        exp = 50.0
        t_compute += time.perf_counter() - t2

    comp = composite_score(blur, exp, weights)

    return {
        "type": "blur",
        "path": path,
        "value": blur,
        "exposure": exp,
        "composite": comp,
        "has_face": has_face,
        "_t_io": t_io,
        "_t_compute": t_compute,
        "_io_bytes": io_bytes,
    }


def task_sad(path_or_pair, reference_path=None) -> dict:
    """Thread worker: compute SAD between a pair. Returns timing fields."""
    if reference_path is None and isinstance(path_or_pair, (tuple, list)) and len(path_or_pair) == 2:
        path, reference_path = path_or_pair
    else:
        path = path_or_pair

    t_io = 0.0
    t_compute = 0.0
    io_bytes = 0

    if reference_path:
        t0 = time.perf_counter()
        a = _open_gray(reference_path)
        b = _open_gray(path)
        t_io = time.perf_counter() - t0
        for p in (path, reference_path):
            try:
                io_bytes += os.path.getsize(p)
            except OSError:
                pass

        t1 = time.perf_counter()
        if a.size != b.size:
            b = b.resize(a.size, Image.Resampling.BILINEAR)
        diff = ImageChops.difference(a, b)
        stat = ImageStat.Stat(diff)
        value = float(stat.mean[0]) if stat.mean else 0.0
        t_compute = time.perf_counter() - t1
    else:
        value = 0.0

    return {
        "type": "sad",
        "path": path,
        "reference_path": reference_path,
        "value": value,
        "_t_io": t_io,
        "_t_compute": t_compute,
        "_io_bytes": io_bytes,
    }
