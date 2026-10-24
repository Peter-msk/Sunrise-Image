"""Bounded local diagnostics, independent of the installation directory."""
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def diagnostics_folder():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'SunriseImage' / 'Diagnostics'


def configure_logging():
    logger = logging.getLogger('sunrise_image')
    if logger.handlers:
        return logger
    logger.setLevel(logging.WARNING)
    logger.propagate = False
    try:
        folder = diagnostics_folder()
        folder.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(folder / 'application.log', maxBytes=1024 * 1024,
                                      backupCount=3, encoding='utf-8')
    except OSError:
        handler = logging.NullHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
    logger.addHandler(handler)
    return logger
