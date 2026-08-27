"""Starter behavior test for {{plugin_name}}."""

from pathlib import Path

import pytest

from reliaforge.plugins.manager import PluginManager


@pytest.mark.asyncio
async def test_generated_plugin_starts_and_reports_healthy() -> None:
    root = Path(__file__).parents[2]
    manager = PluginManager((root,), 5.0, 1.0)
    manager.discover()
    manager.validate()
    await manager.start_all()
    view = manager.get_view("{{plugin_id}}")
    assert view.state == "running"
    assert view.health.status == "healthy"
    await manager.stop_all()
