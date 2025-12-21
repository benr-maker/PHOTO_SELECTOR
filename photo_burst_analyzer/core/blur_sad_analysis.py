import numpy as np, cv2, os
from PIL import Image, ImageOps
import logging
logger = logging.getLogger('pba.blur')

def load_gray(path):
    try:
        im = Image.open(path)
        im = ImageOps.exif_transpose(im)
        im = im.convert('L')
        return np.array(im)
    except Exception:
        logger.exception('Failed to load %s', path)
        return None

def laplacian_variance(arr):
    try:
        if arr is None:
            return None
        return float(cv2.Laplacian(arr, cv2.CV_64F).var())
    except Exception:
        logger.exception('Laplacian failed')
        return None

def mean_sad(a, b):
    try:
        if a is None or b is None:
            return None
        if a.shape != b.shape:
            b = cv2.resize(b, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_AREA)
        diff = np.abs(a.astype('int32') - b.astype('int32'))
        return float(diff.mean())
    except Exception:
        logger.exception('SAD failed')
        return None

def task_blur(path):
    pid = os.getpid()
    arr = load_gray(path)
    val = laplacian_variance(arr)
    return {'type':'blur','path':path,'value':val,'pid':pid}

def task_sad(pair):
    pid = os.getpid()
    a,b = pair
    aval = load_gray(a); bval = load_gray(b)
    val = mean_sad(aval, bval)
    return {'type':'sad','path_a':a,'path_b':b,'value':val,'pid':pid}
