"""Controlled resources exposed to one plugin instance."""

from __future__ import annotations

from typing import Protocol, TypeVar, cast

from pydantic import JsonValue

from reliaforge.events import EventBus, EventDeliveryReport, EventHandler, PluginEvent
from reliaforge.plugins.settings import PluginSettings
from reliaforge.services import ServiceContainer

ServiceT = TypeVar("ServiceT")
ServiceT_co = TypeVar("ServiceT_co", covariant=True)
SettingsT = TypeVar("SettingsT", bound=PluginSettings)


class RuntimeInterface(Protocol[ServiceT_co]):
    """A class-like structural interface used only for runtime validation."""

    def __call__(self) -> ServiceT_co: ...


class UndeclaredCapabilityError(RuntimeError):
    """Raised when a plugin registers a service absent from its manifest."""


class ServiceInterfaceError(TypeError):
    """Raised when a capability does not implement the requested runtime interface."""


class PluginSettingsUnavailableError(LookupError):
    """Raised when a plugin requests settings that were not declared."""


class PluginSettingsTypeError(TypeError):
    """Raised when a plugin requests the wrong settings type."""


class PluginContext:
    """Provider-scoped access to services and events."""

    def __init__(
        self,
        plugin_id: str,
        services: ServiceContainer,
        events: EventBus,
        declared_capabilities: tuple[str, ...] = (),
        settings: PluginSettings | None = None,
    ) -> None:
        self.plugin_id = plugin_id
        self._services = services
        self._events = events
        self._declared_capabilities = frozenset(declared_capabilities)
        self._settings = settings

    def register_service(self, name: str, instance: object) -> None:
        """Register a service owned by this plugin."""

        if name not in self._declared_capabilities:
            raise UndeclaredCapabilityError(f"service is not declared by manifest: {name}")
        self._services.register(name, self.plugin_id, instance)

    def get_service(self, name: str, interface: RuntimeInterface[ServiceT]) -> ServiceT:
        """Resolve a capability and enforce the caller-owned runtime interface."""

        instance = self._services.get(name)
        try:
            compatible = isinstance(instance, cast(type[object], interface))
        except TypeError:
            compatible = False
        if not compatible:
            raise ServiceInterfaceError(f"service interface is incompatible: {name}")
        return cast(ServiceT, instance)

    def get_settings(self, expected_type: type[SettingsT]) -> SettingsT:
        """Return the manager-created settings instance with a runtime type check."""

        if self._settings is None:
            raise PluginSettingsUnavailableError(
                f"plugin settings are not declared: {self.plugin_id}"
            )
        if not isinstance(self._settings, expected_type):
            raise PluginSettingsTypeError(f"plugin settings type is incompatible: {self.plugin_id}")
        return self._settings

    def subscribe(self, topic: str, handler: EventHandler) -> None:
        """Register an event handler owned by this plugin."""

        self._events.subscribe(topic, self.plugin_id, handler)

    async def publish(
        self,
        topic: str,
        payload: dict[str, JsonValue] | None = None,
    ) -> EventDeliveryReport:
        """Publish an event and return its isolated delivery outcome."""

        return await self._events.publish(
            PluginEvent(
                topic=topic,
                plugin_id=self.plugin_id,
                payload=payload or {},
            )
        )

    def cleanup(self) -> None:
        """Remove services and subscriptions owned by this plugin."""

        self._services.unregister_provider(self.plugin_id)
        self._events.unsubscribe_owner(self.plugin_id)
        self._settings = None

    def missing_capabilities(self) -> tuple[str, ...]:
        """Return declared services that this plugin has not registered."""

        registered = {
            record.name
            for record in self._services.list_records()
            if record.provider == self.plugin_id
        }
        return tuple(sorted(self._declared_capabilities - registered))
