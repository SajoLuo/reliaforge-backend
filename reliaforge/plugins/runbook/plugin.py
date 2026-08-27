"""Lifecycle orchestration for the neutral runbook preview plugin."""

from __future__ import annotations

from reliaforge.plugins.contract import BasePlugin, HealthStatus, PluginHealth, PluginManifest

from .models import RunbookPreview
from .router import create_router
from .service import GreetingCapability, RunbookService, RunbookUnavailableError
from .settings import RunbookSettings


class Plugin(BasePlugin):
    """Demonstrate dependency, capability, settings, and lifecycle contracts."""

    settings_class = RunbookSettings

    def __init__(self, manifest: PluginManifest) -> None:
        super().__init__(manifest)
        self.service: RunbookService | None = None
        self.router = create_router(self)

    async def _on_initialize(self) -> None:
        if self.context is None:
            raise RuntimeError("plugin context is unavailable")
        settings = self.context.get_settings(RunbookSettings)
        greeting = self.context.get_service("demo.greeting", GreetingCapability)
        self.service = RunbookService(settings, greeting)
        self.context.register_service("runbook.preview", self.service)
        await self.context.publish("runbook.lifecycle", {"phase": "initialized"})

    async def _on_start(self) -> None:
        if self.context is None or self.service is None:
            raise RuntimeError("runbook service is unavailable")
        self.service.start()
        await self.context.publish("runbook.lifecycle", {"phase": "started"})

    async def _on_stop(self) -> None:
        if self.service is not None:
            self.service.stop()
        if self.context is not None:
            await self.context.publish("runbook.lifecycle", {"phase": "stopped"})
        self.service = None

    def _on_health_check(self) -> PluginHealth:
        running = self.service is not None and self.service.is_running
        return PluginHealth(
            status=HealthStatus.HEALTHY if running else HealthStatus.DEGRADED,
            details={"service_running": running},
        )

    async def preview(self, title: str | None = None) -> RunbookPreview:
        """Delegate preview generation and publish a metadata-only local event."""

        if self.service is None:
            raise RunbookUnavailableError("runbook service is unavailable")
        result = self.service.preview(title)
        if self.context is not None:
            await self.context.publish(
                "runbook.previewed",
                {"step_count": len(result.steps)},
            )
        return result
