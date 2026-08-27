"""Small, centralized logger factories used by the public runtime."""

from __future__ import annotations

import logging
from threading import Lock

_configuration_lock = Lock()


def _configure_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    with _configuration_lock:
        if logger.handlers:
            return logger

        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def get_platform_logger() -> logging.Logger:
    """Return the platform logger."""

    return _configure_logger("reliaforge")


def get_plugin_logger(plugin_id: str) -> logging.Logger:
    """Return an isolated plugin logger without creating files."""

    return _configure_logger(f"reliaforge.plugin.{plugin_id}")
