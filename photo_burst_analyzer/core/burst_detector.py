import os, logging
from .exif_sorter import get_exif_timestamp
logger = logging.getLogger('pba.detector')

def collect_images(root, exts=None):
    if exts is None:
        exts = {'.jpg','.jpeg','.png','.tif','.tiff','.webp'}
    out = []
    for p, _, files in os.walk(root):
        for f in files:
            if os.path.splitext(f)[1].lower() in exts:
                out.append(os.path.join(p, f))
    return out

def detect_candidates(photos, t_metadata=1.0):
    candidates = []
    if not photos:
        return candidates
    photos.sort(key=lambda x: x[1])
    current = [photos[0]]
    for a, b in zip(photos, photos[1:]):
        dt = (b[1] - a[1]).total_seconds()
        if dt <= t_metadata:
            current.append(b)
        else:
            if len(current) >= 2:
                candidates.append(current.copy())
            current = [b]
    if len(current) >= 2:
        candidates.append(current.copy())
    return candidates
