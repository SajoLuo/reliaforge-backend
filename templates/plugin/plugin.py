"""Lifecycle orchestration for {{plugin_name}}."""

from reliaforge.plugins.contract import BasePlugin, HealthStatus, PluginHealth, PluginManifest

from .models import Message
from .router import create_router
from .service import MessageService, MessageUnavailableError
from .settings import GeneratedPluginSettings


class Plugin(BasePlugin):
    """Generated plugin entry point."""

    settings_class = GeneratedPluginSettings

    def __init__(self, manifest: PluginManifest) -> None:
        super().__init__(manifest)
        self.service: MessageService | None = None
        self.router = create_router(self)

    async def _on_initialize(self) -> None:
        if self.context is None:
            raise RuntimeError("plugin context is unavailable")
        settings = self.context.get_settings(GeneratedPluginSettings)
        self.service = MessageService(settings)
        self.context.register_service("{{plugin_id}}.message", self.service)

    async def _on_start(self) -> None:
        if self.context is None or self.service is None:
            raise RuntimeError("plugin service is unavailable")
        self.service.start()

    async def _on_stop(self) -> None:
        if self.service is not None:
            self.service.stop()
        self.service = None

    def _on_health_check(self) -> PluginHealth:
        running = self.service is not None and self.service.is_running
        return PluginHealth(
            status=HealthStatus.HEALTHY if running else HealthStatus.DEGRADED,
            details={"service_running": running},
        )

    def get_message(self) -> Message:
        if self.service is None:
            raise MessageUnavailableError("plugin service is unavailable")
        return self.service.get_message()
