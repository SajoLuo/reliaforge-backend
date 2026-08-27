"""Logger factory concurrency behavior."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from reliaforge.logging import _configure_logger


def test_concurrent_first_configuration_adds_one_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger_name = "reliaforge.test.concurrent-configuration"
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    original_stream_handler = logging.StreamHandler

    def delayed_stream_handler() -> logging.StreamHandler[Any]:
        time.sleep(0.01)
        return original_stream_handler()

    monkeypatch.setattr(logging, "StreamHandler", delayed_stream_handler)

    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            configured = list(executor.map(_configure_logger, [logger_name] * 16))

        assert all(item is logger for item in configured)
        assert len(logger.handlers) == 1
    finally:
        logger.handlers.clear()
