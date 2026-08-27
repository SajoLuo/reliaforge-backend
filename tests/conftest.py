"""Shared fixtures for public backend tests."""

import pytest

from reliaforge.config import AppSettings


@pytest.fixture
def test_settings() -> AppSettings:
    """Return explicit loopback-only settings for TestClient."""

    return AppSettings(
        environment="test",
        host="127.0.0.1",
        auth_mode="development",
    )
