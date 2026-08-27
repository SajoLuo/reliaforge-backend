"""Event delivery isolation, observability, and lifecycle cleanup."""

import asyncio

import pytest

from reliaforge.events import EventBus, PluginEvent
from reliaforge.plugins.context import PluginContext
from reliaforge.plugins.contract import (
    BasePlugin,
    HealthStatus,
    PluginHealth,
    PluginManifest,
    PluginState,
)
from reliaforge.services import ServiceContainer


def _event(sequence: int = 1) -> PluginEvent:
    return PluginEvent(topic="test.event", plugin_id="test_plugin", payload={"sequence": sequence})


async def test_handler_exception_is_isolated_and_reported(
    capsys: pytest.CaptureFixture[str],
) -> None:
    bus = EventBus(0.1)
    delivered: list[int] = []
    private_value = "private-event-handler-value"

    async def failing_handler(event: PluginEvent) -> None:
        raise RuntimeError(private_value)

    async def successful_handler(event: PluginEvent) -> None:
        sequence = event.payload["sequence"]
        assert isinstance(sequence, int)
        delivered.append(sequence)

    bus.subscribe("test.event", "failing_plugin", failing_handler)
    bus.subscribe("test.event", "healthy_plugin", successful_handler)

    report = await bus.publish(_event())

    assert delivered == [1]
    assert report.delivered == 1
    assert [failure.model_dump() for failure in report.failures] == [
        {"owner": "failing_plugin", "reason": "handler_error"}
    ]
    assert private_value not in capsys.readouterr().err


async def test_handler_timeout_is_isolated_and_reported() -> None:
    bus = EventBus(0.01)
    cancelled = asyncio.Event()
    delivered = asyncio.Event()

    async def slow_handler(event: PluginEvent) -> None:
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def successful_handler(event: PluginEvent) -> None:
        delivered.set()

    bus.subscribe("test.event", "slow_plugin", slow_handler)
    bus.subscribe("test.event", "healthy_plugin", successful_handler)

    report = await bus.publish(_event())

    assert delivered.is_set()
    assert cancelled.is_set()
    assert report.delivered == 1
    assert [failure.model_dump() for failure in report.failures] == [
        {"owner": "slow_plugin", "reason": "handler_timeout"}
    ]


async def test_unsubscribe_owner_removes_only_owned_handlers() -> None:
    bus = EventBus(0.1)
    called: list[str] = []

    async def first_handler(event: PluginEvent) -> None:
        called.append("first")

    async def second_handler(event: PluginEvent) -> None:
        called.append("second")

    bus.subscribe("test.event", "first_plugin", first_handler)
    bus.subscribe("test.event", "second_plugin", second_handler)
    bus.unsubscribe_owner("first_plugin")

    report = await bus.publish(_event())

    assert called == ["second"]
    assert report.delivered == 1
    assert report.failures == ()


async def test_publisher_cancellation_propagates_to_handlers() -> None:
    bus = EventBus(1.0)
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def blocking_handler(event: PluginEvent) -> None:
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    bus.subscribe("test.event", "blocking_plugin", blocking_handler)
    publishing = asyncio.create_task(bus.publish(_event()))
    await entered.wait()
    publishing.cancel()

    with pytest.raises(asyncio.CancelledError):
        await publishing
    assert cancelled.is_set()


class CleanupPlugin(BasePlugin):
    """Register context-owned resources used to prove unconditional cleanup."""

    async def _on_initialize(self) -> None:
        if self.context is None:
            raise RuntimeError("plugin context is unavailable")
        self.context.register_service("cleanup.service", object())

        async def slow_stopped_handler(event: PluginEvent) -> None:
            await asyncio.Event().wait()

        self.context.subscribe("plugin.stopped", slow_stopped_handler)

    async def _on_start(self) -> None:
        return None

    async def _on_stop(self) -> None:
        return None

    def _on_health_check(self) -> PluginHealth:
        return PluginHealth(status=HealthStatus.HEALTHY)


class FailingStopPlugin(CleanupPlugin):
    """Fail its plugin-owned stop hook after registering platform resources."""

    async def _on_stop(self) -> None:
        raise RuntimeError("expected stop failure")


class BlockingStopPlugin(CleanupPlugin):
    """Block long enough for the caller's lifecycle deadline to cancel stop."""

    async def _on_stop(self) -> None:
        await asyncio.Event().wait()


def _cleanup_fixture(
    plugin_type: type[CleanupPlugin],
) -> tuple[CleanupPlugin, ServiceContainer, EventBus, PluginContext]:
    manifest = PluginManifest.model_validate(
        {
            "id": "cleanup_plugin",
            "name": "Cleanup Plugin",
            "version": "1.0.0",
            "description": "Lifecycle cleanup fixture",
            "api_version": "v1",
            "entrypoint": "plugin:Plugin",
            "capabilities": ["cleanup.service"],
        }
    )
    services = ServiceContainer()
    bus = EventBus(0.01)
    plugin = plugin_type(manifest)
    plugin.mark_validated()
    context = PluginContext(manifest.id, services, bus, manifest.capabilities)
    return plugin, services, bus, context


async def test_stop_cleanup_is_unconditional_when_event_handler_times_out() -> None:
    plugin, services, bus, context = _cleanup_fixture(CleanupPlugin)

    assert await plugin.initialize(context) is True
    assert await plugin.stop() is True
    assert plugin.state is PluginState.STOPPED
    assert plugin.context is None
    assert services.list_records() == ()

    assert await plugin.stop() is True
    after_cleanup = await bus.publish(
        PluginEvent(topic="plugin.stopped", plugin_id="cleanup_plugin")
    )
    assert after_cleanup.delivered == 0
    assert after_cleanup.failures == ()


async def test_stop_cleanup_is_unconditional_when_plugin_hook_fails() -> None:
    plugin, services, bus, context = _cleanup_fixture(FailingStopPlugin)

    assert await plugin.initialize(context) is True
    assert await plugin.stop() is False
    assert plugin.state is PluginState.ERROR
    assert plugin.context is None
    assert services.list_records() == ()
    after_cleanup = await bus.publish(
        PluginEvent(topic="plugin.stopped", plugin_id="cleanup_plugin")
    )
    assert after_cleanup.delivered == 0


async def test_stop_cleanup_is_unconditional_when_deadline_cancels_hook() -> None:
    plugin, services, bus, context = _cleanup_fixture(BlockingStopPlugin)

    assert await plugin.initialize(context) is True
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.01):
            await plugin.stop()

    assert plugin.state is PluginState.ERROR
    assert plugin.context is None
    assert services.list_records() == ()
    after_cleanup = await bus.publish(
        PluginEvent(topic="plugin.stopped", plugin_id="cleanup_plugin")
    )
    assert after_cleanup.delivered == 0
