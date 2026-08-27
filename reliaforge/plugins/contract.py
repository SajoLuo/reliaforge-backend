"""Stable public manifest and lifecycle contract for ReliaForge plugins."""

from __future__ import annotations

import asyncio
import re
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import ClassVar, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator
from semantic_version import SimpleSpec, Version

from reliaforge.logging import get_plugin_logger
from reliaforge.plugins.context import PluginContext
from reliaforge.plugins.settings import PluginSettings

CAPABILITY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_-]*)+$")


class PluginState(StrEnum):
    """Externally visible plugin lifecycle states."""

    DISCOVERED = "discovered"
    VALIDATED = "validated"
    INITIALIZED = "initialized"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


class PluginAction(StrEnum):
    """Lifecycle operations currently available for a plugin record."""

    START = "start"
    STOP = "stop"
    RESTART = "restart"


class HealthStatus(StrEnum):
    """Stable health status vocabulary."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    ERROR = "error"
    STOPPED = "stopped"


class FrontendMetadata(BaseModel):
    """Optional hints consumed by a neutral management UI."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: str | None = None


class PluginDependency(BaseModel):
    """A required plugin and the accepted SemVer range."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    version: str = Field(min_length=1, max_length=100)

    @field_validator("version")
    @classmethod
    def validate_version_range(cls, value: str) -> str:
        try:
            SimpleSpec(value)
        except ValueError as exc:
            raise ValueError("dependency version must be a valid SemVer range") from exc
        return value

    def accepts(self, version: str) -> bool:
        """Return whether a provider version satisfies this dependency."""

        return bool(SimpleSpec(self.version).match(Version(version)))


class PluginManifest(BaseModel):
    """Validated metadata loaded before any plugin code executes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    name: str = Field(min_length=1, max_length=80)
    version: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=500)
    api_version: Literal["v1"]
    entrypoint: str = Field(pattern=r"^[a-z_][a-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$")
    dependencies: tuple[PluginDependency, ...] = ()
    capabilities: tuple[str, ...] = ()
    frontend: FrontendMetadata = Field(default_factory=FrontendMetadata)

    @field_validator("capabilities")
    @classmethod
    def reject_duplicates(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("values must be unique")
        return values

    @field_validator("dependencies")
    @classmethod
    def reject_duplicate_dependencies(
        cls,
        values: tuple[PluginDependency, ...],
    ) -> tuple[PluginDependency, ...]:
        dependency_ids = [dependency.id for dependency in values]
        if len(dependency_ids) != len(set(dependency_ids)):
            raise ValueError("dependency ids must be unique")
        return values

    @field_validator("version")
    @classmethod
    def validate_plugin_version(cls, value: str) -> str:
        try:
            Version(value)
        except ValueError as exc:
            raise ValueError("plugin version must be valid SemVer") from exc
        return value

    @field_validator("capabilities")
    @classmethod
    def validate_capability_names(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(CAPABILITY_PATTERN.fullmatch(value) is None for value in values):
            raise ValueError("capabilities must be dotted public service names")
        return values


class PluginHealth(BaseModel):
    """A side-effect-free health snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: HealthStatus
    details: dict[str, JsonValue] | None = None


class BasePlugin(ABC):
    """Async lifecycle state machine shared by every public plugin."""

    settings_class: ClassVar[type[PluginSettings] | None] = None

    def __init__(self, manifest: PluginManifest) -> None:
        self.manifest = manifest
        self.state = PluginState.DISCOVERED
        self.context: PluginContext | None = None
        self.router: APIRouter | None = None
        self.logger = get_plugin_logger(manifest.id)
        self._lifecycle_lock = asyncio.Lock()
        self._last_error_type: str | None = None

    def mark_validated(self) -> None:
        """Move a discovered plugin into the validated state."""

        if self.state is not PluginState.DISCOVERED:
            raise RuntimeError("only discovered plugins can be validated")
        self.state = PluginState.VALIDATED

    async def initialize(self, context: PluginContext) -> bool:
        """Initialize plugin-owned resources without hiding cancellation."""

        async with self._lifecycle_lock:
            if self.state not in {PluginState.VALIDATED, PluginState.STOPPED, PluginState.ERROR}:
                return False
            self.context = context
            try:
                await self._on_initialize()
                self.state = PluginState.INITIALIZED
                self._last_error_type = None
                await context.publish("plugin.initialized", {"state": self.state.value})
                return True
            except asyncio.CancelledError:
                self._set_error("CancelledError")
                context.cleanup()
                self.context = None
                raise
            except Exception as exc:
                self._set_error(type(exc).__name__)
                self.logger.error("plugin initialization failed (%s)", type(exc).__name__)
                context.cleanup()
                self.context = None
                return False

    async def start(self) -> bool:
        """Start an initialized plugin."""

        async with self._lifecycle_lock:
            if self.state is not PluginState.INITIALIZED or self.context is None:
                return False
            try:
                await self._on_start()
                snapshot = self._on_health_check()
                if snapshot.status is HealthStatus.ERROR:
                    self._set_error(f"initial_health_{snapshot.status.value}")
                    return False
                self.state = PluginState.RUNNING
                await self.context.publish("plugin.started", {"state": self.state.value})
                return True
            except asyncio.CancelledError:
                self._set_error("CancelledError")
                raise
            except Exception as exc:
                self._set_error(type(exc).__name__)
                self.logger.error("plugin start failed (%s)", type(exc).__name__)
                return False

    async def stop(self) -> bool:
        """Stop a plugin and unconditionally release its context-owned resources."""

        async with self._lifecycle_lock:
            if self.state is PluginState.STOPPED:
                return True
            if self.state in {PluginState.DISCOVERED, PluginState.VALIDATED}:
                self.state = PluginState.STOPPED
                return True
            context = self.context
            if context is None:
                self.state = PluginState.STOPPED
                self._last_error_type = None
                return True
            succeeded = False
            try:
                await self._on_stop()
                await context.publish("plugin.stopped", {"state": "stopped"})
                succeeded = True
            except asyncio.CancelledError:
                self._set_error("CancelledError")
                raise
            except Exception as exc:
                self._set_error(type(exc).__name__)
                self.logger.error("plugin stop failed (%s)", type(exc).__name__)
            finally:
                context.cleanup()
                self.context = None
            if not succeeded:
                return False
            self.state = PluginState.STOPPED
            self._last_error_type = None
            return True

    def health(self) -> PluginHealth:
        """Read an in-process snapshot without external I/O or repair writes."""

        if self.state is PluginState.ERROR:
            details: dict[str, JsonValue] | None = (
                {"reason": self._last_error_type} if self._last_error_type else None
            )
            return PluginHealth(status=HealthStatus.ERROR, details=details)
        if self.state is PluginState.RUNNING:
            try:
                return self._on_health_check()
            except Exception as exc:
                return PluginHealth(
                    status=HealthStatus.ERROR,
                    details={"reason": type(exc).__name__},
                )
        return PluginHealth(status=HealthStatus.STOPPED)

    def mark_error(self, reason: str) -> None:
        """Expose a safe manager error and release platform-owned resources."""

        if self.context is not None:
            self.context.cleanup()
            self.context = None
        self._set_error(reason)

    def _set_error(self, reason: str) -> None:
        self.state = PluginState.ERROR
        self._last_error_type = reason

    @abstractmethod
    async def _on_initialize(self) -> None:
        """Create local resources and register public services."""

    @abstractmethod
    async def _on_start(self) -> None:
        """Start local resources."""

    @abstractmethod
    async def _on_stop(self) -> None:
        """Release resources."""

    @abstractmethod
    def _on_health_check(self) -> PluginHealth:
        """Return a side-effect-free in-memory snapshot."""
