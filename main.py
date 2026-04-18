"""Photo Burst Analyzer - verified 2025-10-17, hotfix VER4.7

Entry-point wrapper safe for PyInstaller one-file/one-dir builds.
Fixes the "second instance launches / no images load" symptom by:
- Avoiding multiprocessing spawn of the GUI entrypoint (analysis now uses threads)
- Ensuring GUI modules are imported only inside main()
"""

import logging
import multiprocessing as _mp


def _configure_logging():
    """Set up console + optional file logging.

    Developer perf stats are emitted at INFO level on the 'pba.perf' logger.
    Set PBA_LOG_FILE env var to also write to a file, e.g.:
        PBA_LOG_FILE=pba.log python main.py
    """
    import os
    fmt = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
    datefmt = "%H:%M:%S"
    handlers = [logging.StreamHandler()]

    log_file = os.environ.get("PBA_LOG_FILE")
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(level=logging.INFO, format=fmt, datefmt=datefmt, handlers=handlers)

    # Suppress noisy third-party loggers
    for noisy in ("PIL", "PIL.Image", "PIL.TiffImagePlugin"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def main():
    _configure_logging()
    from photo_burst_analyzer.gui import main_window
    main_window.main()


if __name__ == "__main__":
    _mp.freeze_support()
    main()
