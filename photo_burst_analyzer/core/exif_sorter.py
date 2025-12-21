from PIL import Image, ExifTags
from datetime import datetime
from dateutil import parser as _p
import logging
logger = logging.getLogger('pba.exif')

def get_exif_timestamp(path):
    try:
        img = Image.open(path)
        exif = img._getexif()
        if not exif:
            return None
        tags = {ExifTags.TAGS.get(k,k): v for k,v in exif.items()}
        for key in ('DateTimeOriginal', 'DateTime', 'DateTimeDigitized'):
            if key in tags:
                val = tags[key]
                try:
                    return datetime.strptime(val, "%Y:%m:%d %H:%M:%S")
                except Exception:
                    try:
                        return _p.parse(val)
                    except Exception:
                        continue
        return None
    except Exception:
        logger.exception('Failed to read EXIF from %s', path)
        return None
