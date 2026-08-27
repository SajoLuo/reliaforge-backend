"""Neutral demo plugin lifecycle orchestration."""

from __future__ import annotations

from reliaforge.plugins.contract import BasePlugin, HealthStatus, PluginHealth, PluginManifest

from .models import Greeting
from .router import create_router
from .service import GreetingService, GreetingUnavailableError
from .settings import DemoSettings


class Plugin(BasePlugin):
    """Demonstrate the public contract without network, storage, or credentials."""

    settings_class = DemoSettings

    def __init__(self, manifest: PluginManifest) -> None:
        super().__init__(manifest)
        self.service: GreetingService | None = None
        self.router = create_router(self)

    async def _on_initialize(self) -> None:
        if self.context is None:
            raise RuntimeError("plugin context is unavailable")
        settings = self.context.get_settings(DemoSettings)
        self.service = GreetingService(settings)
        self.context.register_service("demo.greeting", self.service)
        await self.context.publish("demo.lifecycle", {"phase": "initialized"})

    async def _on_start(self) -> None:
        if self.context is None or self.service is None:
            raise RuntimeError("demo service is unavailable")
        self.service.start()
        await self.context.publish("demo.lifecycle", {"phase": "started"})

    async def _on_stop(self) -> None:
        if self.service is not None:
            self.service.stop()
        if self.context is not None:
            await self.context.publish("demo.lifecycle", {"phase": "stopped"})
        self.service = None

    def _on_health_check(self) -> PluginHealth:
        running = self.service is not None and self.service.is_running
        return PluginHealth(
            status=HealthStatus.HEALTHY if running else HealthStatus.DEGRADED,
            details={"service_running": running},
        )

    def greet(self) -> Greeting:
        """Delegate greeting behavior to the service layer."""

        if self.service is None:
            raise GreetingUnavailableError("greeting service is unavailable")
        return self.service.greet()
