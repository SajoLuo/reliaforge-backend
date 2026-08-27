"""Lifecycle, cleanup, event, and error-state behavior."""

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from reliaforge.app import create_app
from reliaforge.config import AppSettings
from reliaforge.events import EventBus
from reliaforge.plugins.context import PluginContext
from reliaforge.plugins.contract import (
    BasePlugin,
    HealthStatus,
    PluginHealth,
    PluginManifest,
    PluginState,
)
from reliaforge.plugins.manager import PluginManager, PluginOperationError
from reliaforge.scaffold import scaffold_plugin
from reliaforge.services import ServiceContainer


def _bundled_root() -> Path:
    import reliaforge.plugins

    return Path(reliaforge.plugins.__file__).parent


async def test_demo_full_lifecycle_registers_events_and_cleans_up() -> None:
    manager = PluginManager((_bundled_root(),), 5.0, 1.0)
    manager.discover()
    manager.validate()
    assert manager.get_view("demo").state is PluginState.VALIDATED

    await manager.start_all()
    running = manager.get_view("demo")
    assert running.state is PluginState.RUNNING
    assert running.health.status is HealthStatus.HEALTHY

    await manager.stop_all()
    stopped = manager.get_view("demo")
    assert stopped.state is PluginState.STOPPED
    assert stopped.health.status is HealthStatus.STOPPED


async def test_bundled_plugins_start_dependency_first_and_stop_in_reverse() -> None:
    manager = PluginManager((_bundled_root(),), 5.0, 1.0)
    manager.discover()
    manager.validate()
    demo = manager._records["demo"].instance
    runbook = manager._records["runbook"].instance
    assert demo is not None and runbook is not None

    order: list[str] = []
    demo_start = demo._on_start
    runbook_start = runbook._on_start
    demo_stop = demo._on_stop
    runbook_stop = runbook._on_stop

    async def tracked_demo_start() -> None:
        order.append("start:demo")
        await demo_start()

    async def tracked_runbook_start() -> None:
        order.append("start:runbook")
        await runbook_start()

    async def tracked_demo_stop() -> None:
        order.append("stop:demo")
        await demo_stop()

    async def tracked_runbook_stop() -> None:
        order.append("stop:runbook")
        await runbook_stop()

    demo._on_start = tracked_demo_start  # type: ignore[method-assign]
    runbook._on_start = tracked_runbook_start  # type: ignore[method-assign]
    demo._on_stop = tracked_demo_stop  # type: ignore[method-assign]
    runbook._on_stop = tracked_runbook_stop  # type: ignore[method-assign]

    await manager.start_all()
    await manager.stop_all()
    assert order == ["start:demo", "start:runbook", "stop:runbook", "stop:demo"]


async def test_shutdown_budget_reaches_plugins_after_one_stop_times_out() -> None:
    manager = PluginManager((_bundled_root(),), 5.0, 1.0)
    manager.discover()
    manager.validate()
    demo = manager._records["demo"].instance
    runbook = manager._records["runbook"].instance
    assert demo is not None and runbook is not None

    order: list[str] = []

    async def slow_runbook_stop() -> bool:
        order.append("stop:runbook")
        await asyncio.sleep(1)
        return True

    async def fast_demo_stop() -> bool:
        order.append("stop:demo")
        return True

    runbook.stop = slow_runbook_stop  # type: ignore[method-assign]
    demo.stop = fast_demo_stop  # type: ignore[method-assign]

    loop = asyncio.get_running_loop()
    started_at = loop.time()
    await manager.stop_all(timeout_seconds=0.05)

    assert order == ["stop:runbook", "stop:demo"]
    assert loop.time() - started_at < 0.15
    assert runbook.state is PluginState.ERROR
    assert runbook.context is None


async def test_zero_shutdown_budget_still_enters_every_stop() -> None:
    manager = PluginManager((_bundled_root(),), 5.0, 1.0)
    manager.discover()
    manager.validate()
    await manager.start_all()
    demo = manager._records["demo"].instance
    runbook = manager._records["runbook"].instance
    assert demo is not None and runbook is not None

    entered: list[str] = []

    async def enter_runbook_stop() -> bool:
        entered.append("runbook")
        await asyncio.sleep(0)
        return True

    async def enter_demo_stop() -> bool:
        entered.append("demo")
        await asyncio.sleep(0)
        return True

    runbook.stop = enter_runbook_stop  # type: ignore[method-assign]
    demo.stop = enter_demo_stop  # type: ignore[method-assign]

    await manager.stop_all(timeout_seconds=0)

    assert entered == ["runbook", "demo"]
    assert runbook.context is None
    assert demo.context is None


async def test_shutdown_waits_for_the_operation_lock() -> None:
    manager = PluginManager((_bundled_root(),), 5.0, 1.0)
    manager.discover()
    manager.validate()
    await manager.start_all()
    demo = manager._records["demo"].instance
    assert demo is not None and demo.context is not None

    await manager._operation_lock.acquire()
    shutdown = asyncio.create_task(manager.stop_all())
    await asyncio.sleep(0)
    assert shutdown.done() is False
    assert demo.context is not None

    manager._operation_lock.release()
    await shutdown
    assert demo.context is None


async def test_operation_lock_wait_counts_against_action_and_shutdown_budgets() -> None:
    manager = PluginManager((_bundled_root(),), 0.01, 1.0)
    manager.discover()
    manager.validate()
    await manager.start_all()
    runbook = manager._records["runbook"].instance
    assert runbook is not None and runbook.context is not None

    await manager._operation_lock.acquire()
    try:
        with pytest.raises(TimeoutError):
            await manager.stop_plugin("runbook")
        assert runbook.context is not None

        await manager.stop_all(timeout_seconds=0.01)
        assert runbook.context is not None
        assert runbook.state is PluginState.RUNNING
    finally:
        manager._operation_lock.release()

    await manager.stop_all()
    assert runbook.context is None


async def test_shutdown_isolates_unexpected_stop_failure() -> None:
    manager = PluginManager((_bundled_root(),), 5.0, 1.0)
    manager.discover()
    manager.validate()
    await manager.start_all()
    demo = manager._records["demo"].instance
    runbook = manager._records["runbook"].instance
    assert demo is not None and runbook is not None

    demo_stopped = False

    async def unexpected_runbook_stop() -> bool:
        raise RuntimeError("unexpected fixture failure")

    async def tracked_demo_stop() -> bool:
        nonlocal demo_stopped
        demo_stopped = True
        return True

    runbook.stop = unexpected_runbook_stop  # type: ignore[method-assign]
    demo.stop = tracked_demo_stop  # type: ignore[method-assign]

    await manager.stop_all()

    assert demo_stopped is True
    assert runbook.state is PluginState.ERROR
    assert runbook.context is None


async def test_shutdown_budget_is_not_capped_by_operation_timeout() -> None:
    manager = PluginManager((_bundled_root(),), 0.01, 1.0)
    manager.discover()
    manager.validate()
    demo = manager._records["demo"].instance
    runbook = manager._records["runbook"].instance
    assert demo is not None and runbook is not None

    order: list[str] = []

    async def delayed_runbook_stop() -> bool:
        order.append("begin:runbook")
        await asyncio.sleep(0.04)
        order.append("complete:runbook")
        return True

    async def fast_demo_stop() -> bool:
        order.append("stop:demo")
        return True

    runbook.stop = delayed_runbook_stop  # type: ignore[method-assign]
    demo.stop = fast_demo_stop  # type: ignore[method-assign]

    await manager.stop_all(timeout_seconds=0.2)

    assert order == ["begin:runbook", "complete:runbook", "stop:demo"]
    assert runbook.state is not PluginState.ERROR


def test_shutdown_timeout_does_not_mask_startup_failure() -> None:
    settings = AppSettings(
        environment="test",
        host="127.0.0.1",
        auth_mode="development",
        shutdown_timeout_seconds=0.02,
    )
    app = create_app(settings)
    manager = app.state.plugin_manager
    runbook = manager._records["runbook"].instance
    assert runbook is not None

    async def fail_startup() -> None:
        raise RuntimeError("original startup failure")

    async def slow_stop() -> bool:
        await asyncio.sleep(1)
        return True

    manager.start_all = fail_startup
    runbook.stop = slow_stop

    with pytest.raises(RuntimeError, match="original startup failure"):
        with TestClient(app):
            pass


def test_discovery_and_validation_are_single_use_even_for_empty_roots(tmp_path: Path) -> None:
    manager = PluginManager((tmp_path,), 1.0, 1.0)
    with pytest.raises(PluginOperationError, match="discovery must run"):
        manager.validate()
    manager.discover()
    with pytest.raises(PluginOperationError, match="discovery can only run once"):
        manager.discover()
    manager.validate()
    with pytest.raises(PluginOperationError, match="validation can only run once"):
        manager.validate()


class FailingPlugin(BasePlugin):
    """Test double that fails during initialization."""

    async def _on_initialize(self) -> None:
        raise RuntimeError("expected lifecycle failure")

    async def _on_start(self) -> None:
        if self.context is not None:
            await self.context.publish("test.started")

    async def _on_stop(self) -> None:
        if self.context is not None:
            await self.context.publish("test.stopped")

    def _on_health_check(self) -> PluginHealth:
        return PluginHealth(status=HealthStatus.HEALTHY)


class ErrorHealthPlugin(FailingPlugin):
    """Test double whose initial snapshot rejects startup."""

    async def _on_initialize(self) -> None:
        return None

    def _on_health_check(self) -> PluginHealth:
        return PluginHealth(status=HealthStatus.ERROR)


class DegradedHealthPlugin(ErrorHealthPlugin):
    """Test double whose degraded health remains a running lifecycle state."""

    def _on_health_check(self) -> PluginHealth:
        return PluginHealth(status=HealthStatus.DEGRADED)


class SecretFailingPlugin(FailingPlugin):
    """Test double whose exception message must never be re-logged by the runtime."""

    def __init__(self, manifest: PluginManifest, private_value: str) -> None:
        super().__init__(manifest)
        self._private_value = private_value

    async def _on_initialize(self) -> None:
        raise RuntimeError(self._private_value)


async def test_initialize_failure_enters_safe_error_state() -> None:
    manifest = PluginManifest.model_validate(
        {
            "id": "failure_case",
            "name": "Failure Case",
            "version": "1.0.0",
            "description": "Lifecycle failure fixture",
            "api_version": "v1",
            "entrypoint": "plugin:Plugin",
        }
    )
    plugin = FailingPlugin(manifest)
    plugin.mark_validated()
    context = PluginContext("failure_case", ServiceContainer(), EventBus(1.0))

    assert await plugin.initialize(context) is False
    assert plugin.state is PluginState.ERROR
    assert plugin.health().status is HealthStatus.ERROR
    assert plugin.health().details == {"reason": "RuntimeError"}

    async def fail_if_stop_hook_runs() -> None:
        raise AssertionError("stop hook must not run without an initialized context")

    plugin._on_stop = fail_if_stop_hook_runs  # type: ignore[method-assign]
    assert await plugin.stop() is True
    assert plugin.health().status is HealthStatus.STOPPED
    assert plugin.context is None


async def test_initial_error_health_rejects_startup() -> None:
    manifest = PluginManifest.model_validate(
        {
            "id": "health_error",
            "name": "Health Error",
            "version": "1.0.0",
            "description": "Initial health error fixture",
            "api_version": "v1",
            "entrypoint": "plugin:Plugin",
        }
    )
    plugin = ErrorHealthPlugin(manifest)
    plugin.mark_validated()
    context = PluginContext("health_error", ServiceContainer(), EventBus(1.0))

    assert await plugin.initialize(context) is True
    with pytest.raises(PluginOperationError, match="plugin start failed"):
        await PluginManager._start_initialized("health_error", plugin)
    assert plugin.state is PluginState.ERROR
    assert plugin.context is None
    assert plugin.health().details == {"reason": "initial_health_error"}


async def test_initial_degraded_health_still_enters_running_lifecycle() -> None:
    manifest = PluginManifest.model_validate(
        {
            "id": "health_degraded",
            "name": "Health Degraded",
            "version": "1.0.0",
            "description": "Independent health fixture",
            "api_version": "v1",
            "entrypoint": "plugin:Plugin",
        }
    )
    plugin = DegradedHealthPlugin(manifest)
    plugin.mark_validated()
    context = PluginContext("health_degraded", ServiceContainer(), EventBus(1.0))

    assert await plugin.initialize(context) is True
    assert await plugin.start() is True
    assert plugin.state is PluginState.RUNNING
    assert plugin.health().status is HealthStatus.DEGRADED


async def test_lifecycle_logs_error_type_without_exception_value(
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_value = "-".join(("sensitive", "runtime", "fixture"))
    manifest = PluginManifest.model_validate(
        {
            "id": "secret_failure",
            "name": "Secret Failure",
            "version": "1.0.0",
            "description": "Safe logging fixture",
            "api_version": "v1",
            "entrypoint": "plugin:Plugin",
        }
    )
    plugin = SecretFailingPlugin(manifest, private_value)
    plugin.mark_validated()
    context = PluginContext("secret_failure", ServiceContainer(), EventBus(1.0))

    assert await plugin.initialize(context) is False
    captured = capsys.readouterr()
    assert private_value not in captured.err
    assert "RuntimeError" in captured.err


def _make_slow_plugin(tmp_path: Path, plugin_id: str = "slow_plugin") -> None:
    plugin_dir = scaffold_plugin(plugin_id, tmp_path)
    source_path = plugin_dir / "plugin.py"
    source = source_path.read_text(encoding="utf-8")
    source = source.replace(
        '"""Lifecycle orchestration',
        'import asyncio\n\n"""Lifecycle orchestration',
        1,
    )
    source = source.replace(
        "        self.service.start()",
        "        await asyncio.sleep(0.1)\n        self.service.start()",
        1,
    )
    source_path.write_text(source, encoding="utf-8")


def test_start_timeout_returns_503_instead_of_success(tmp_path: Path) -> None:
    _make_slow_plugin(tmp_path)
    settings = AppSettings(
        environment="test",
        host="127.0.0.1",
        auth_mode="development",
        plugin_paths=str(tmp_path),
        plugin_operation_timeout_seconds=0.01,
        app_startup_timeout_seconds=1.0,
    )
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/v1/plugins/slow_plugin/start")
        assert response.status_code == 503
        assert response.json() == {"detail": "Plugin operation timed out"}


async def test_restart_uses_one_end_to_end_operation_deadline() -> None:
    manager = PluginManager((_bundled_root(),), 0.05, 1.0)
    manager.discover()
    manager.validate()
    await manager.start_all()
    runbook = manager._records["runbook"].instance
    assert runbook is not None
    original_stop = runbook._on_stop

    async def delayed_stop() -> None:
        await asyncio.sleep(0.03)
        await original_stop()

    async def delayed_start() -> None:
        await asyncio.sleep(0.05)

    runbook._on_stop = delayed_stop  # type: ignore[method-assign]
    runbook._on_start = delayed_start  # type: ignore[method-assign]
    loop = asyncio.get_running_loop()
    started_at = loop.time()

    with pytest.raises(PluginOperationError, match="startup timed out"):
        await manager.restart_plugin("runbook")

    assert loop.time() - started_at < 0.09
    assert runbook.context is None
    assert runbook.state is PluginState.ERROR


def test_app_startup_timeout_cleans_already_started_plugins(tmp_path: Path) -> None:
    _make_slow_plugin(tmp_path)
    settings = AppSettings(
        environment="test",
        host="127.0.0.1",
        auth_mode="development",
        plugin_paths=str(tmp_path),
        plugin_operation_timeout_seconds=1.0,
        app_startup_timeout_seconds=0.01,
    )
    app = create_app(settings)
    demo = app.state.plugin_manager._records["demo"].instance
    assert demo is not None
    demo_stop = demo._on_stop
    stop_called = False

    async def tracked_demo_stop() -> None:
        nonlocal stop_called
        stop_called = True
        await demo_stop()

    demo._on_stop = tracked_demo_stop
    with pytest.raises(TimeoutError):
        with TestClient(app):
            pass
    assert stop_called is True
    assert app.state.plugin_manager.get_view("demo").state is PluginState.STOPPED


async def test_restart_rejects_provider_with_active_dependent(tmp_path: Path) -> None:
    scaffold_plugin("provider_plugin", tmp_path)
    dependent_dir = scaffold_plugin("dependent_plugin", tmp_path)
    manifest_path = dependent_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["dependencies"] = [{"id": "provider_plugin", "version": "^0.1.0"}]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    manager = PluginManager((tmp_path,), 1.0, 1.0)
    manager.discover()
    manager.validate()
    await manager.start_all()
    with pytest.raises(PluginOperationError, match="active dependents prevent restart"):
        await manager.restart_plugin("provider_plugin")
    await manager.stop_all()


def test_failed_plugin_and_blocked_dependent_leave_management_api_available(
    tmp_path: Path,
) -> None:
    broken_dir = scaffold_plugin("broken_plugin", tmp_path)
    dependent_dir = scaffold_plugin("dependent_plugin", tmp_path)

    broken_source = (broken_dir / "plugin.py").read_text(encoding="utf-8")
    broken_source = broken_source.replace(
        "settings = self.context.get_settings(GeneratedPluginSettings)",
        'raise RuntimeError("fixture initialization failure")',
        1,
    )
    (broken_dir / "plugin.py").write_text(broken_source, encoding="utf-8")

    dependent_manifest_path = dependent_dir / "manifest.json"
    dependent_manifest = json.loads(dependent_manifest_path.read_text(encoding="utf-8"))
    dependent_manifest["dependencies"] = [{"id": "broken_plugin", "version": "^0.1.0"}]
    dependent_manifest_path.write_text(
        json.dumps(dependent_manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    settings = AppSettings(
        environment="test",
        host="127.0.0.1",
        auth_mode="development",
        plugin_paths=str(tmp_path),
    )
    with TestClient(create_app(settings)) as client:
        catalog = client.get("/api/v1/plugins")
        assert catalog.status_code == 200
        states = {item["id"]: item["state"] for item in catalog.json()["plugins"]}
        assert states == {
            "broken_plugin": "error",
            "demo": "running",
            "dependent_plugin": "error",
            "runbook": "running",
        }
        actions = {item["id"]: item["available_actions"] for item in catalog.json()["plugins"]}
        assert actions["broken_plugin"] == ["start"]
        assert actions["dependent_plugin"] == []

        retry = client.post("/api/v1/plugins/broken_plugin/start")
        assert retry.status_code == 409
        assert retry.json() == {"detail": "plugin initialize failed: broken_plugin"}


async def test_platform_status_counts_are_mutually_exclusive_and_complete() -> None:
    manager = PluginManager((_bundled_root(),), 5.0, 1.0)
    manager.discover()
    manager.validate()
    await manager.start_all()

    await manager.stop_plugin("runbook")
    demo = manager._records["demo"].instance
    assert demo is not None
    demo._on_health_check = lambda: PluginHealth(status=HealthStatus.DEGRADED)  # type: ignore[method-assign]

    summary = manager.platform_status().plugins
    assert summary.model_dump() == {
        "total": 2,
        "running": 0,
        "degraded": 1,
        "stopped": 1,
        "error": 0,
    }
    assert summary.total == summary.running + summary.degraded + summary.stopped + summary.error

    demo.mark_error("fixture_error")
    errored = manager.platform_status().plugins
    assert errored.error == 1
    assert errored.stopped == 1
    assert errored.total == (errored.running + errored.degraded + errored.stopped + errored.error)
