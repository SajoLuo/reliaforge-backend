"""Plugin discovery, validation, lifecycle orchestration, and public views."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import APIRouter

from reliaforge import __version__
from reliaforge.api.models import (
    PlatformStatusResponse,
    PluginCounts,
    PluginListResponse,
    PluginView,
)
from reliaforge.events import EventBus
from reliaforge.plugins.context import PluginContext
from reliaforge.plugins.contract import (
    BasePlugin,
    HealthStatus,
    PluginAction,
    PluginHealth,
    PluginManifest,
    PluginState,
)
from reliaforge.plugins.dependency import DependencyResolver
from reliaforge.plugins.loader import PluginCandidate, PluginLoader, PluginLoadError
from reliaforge.plugins.settings import (
    PluginSettings,
    empty_settings_schema,
    load_plugin_settings,
    public_settings_schema,
)
from reliaforge.services import ServiceContainer

RESERVED_PLUGIN_PATHS = frozenset({"/start", "/stop", "/restart"})


class PluginNotFoundError(LookupError):
    """Raised when a management operation targets an unknown plugin."""


class PluginOperationError(RuntimeError):
    """Raised when dependencies or lifecycle state reject an operation."""


class PluginOperationTimeoutError(PluginOperationError):
    """Raised when a lifecycle operation exceeds its configured deadline."""


@dataclass
class PluginRecord:
    """Static candidate plus optional runtime instance and safe load error."""

    candidate: PluginCandidate
    instance: BasePlugin | None = None
    error_reason: str | None = None

    @property
    def manifest(self) -> PluginManifest:
        return self.candidate.manifest


class PluginManager:
    """Own one process-local set of discovered plugin records."""

    def __init__(
        self,
        plugin_roots: Iterable[Path],
        operation_timeout_seconds: float,
        event_handler_timeout_seconds: float,
    ) -> None:
        self._plugin_roots = tuple(plugin_roots)
        self._operation_timeout_seconds = operation_timeout_seconds
        self._loader = PluginLoader()
        self._resolver = DependencyResolver()
        self._services = ServiceContainer()
        self._events = EventBus(event_handler_timeout_seconds)
        self._candidates: dict[str, PluginCandidate] = {}
        self._records: dict[str, PluginRecord] = {}
        self._startup_order: tuple[str, ...] = ()
        self._operation_lock = asyncio.Lock()
        self._discovered = False
        self._validated = False

    def discover(self) -> None:
        """Discover all configured roots once and reject duplicate IDs."""

        if self._discovered:
            raise PluginOperationError("plugin discovery can only run once")
        self._discovered = True
        for root in self._plugin_roots:
            for candidate in self._loader.discover_root(root):
                plugin_id = candidate.manifest.id
                if plugin_id in self._candidates:
                    raise PluginOperationError(f"duplicate plugin id: {plugin_id}")
                self._candidates[plugin_id] = candidate

    def validate(self) -> None:
        """Validate the static graph, then isolate individual code-load failures."""

        if not self._discovered:
            raise PluginOperationError("plugin discovery must run before validation")
        if self._validated:
            raise PluginOperationError("plugin validation can only run once")
        manifests = tuple(candidate.manifest for candidate in self._candidates.values())
        self._validate_capability_ownership(manifests)
        startup_order = self._resolver.resolve(manifests)
        records = {
            plugin_id: PluginRecord(candidate=candidate)
            for plugin_id, candidate in self._candidates.items()
        }
        for plugin_id in startup_order:
            record = records[plugin_id]
            unavailable = [
                dependency.id
                for dependency in record.manifest.dependencies
                if records[dependency.id].instance is None
            ]
            if unavailable:
                record.error_reason = "dependency_unavailable"
                continue
            try:
                plugin = self._loader.load(record.candidate)
            except PluginLoadError:
                record.error_reason = "load_error"
                continue
            if self._has_reserved_route(plugin.router):
                self._loader.unload(record.candidate)
                record.error_reason = "reserved_route"
                continue
            if plugin.settings_class is not None and (
                not isinstance(plugin.settings_class, type)
                or not issubclass(plugin.settings_class, PluginSettings)
            ):
                self._loader.unload(record.candidate)
                record.error_reason = "load_error"
                continue
            plugin.mark_validated()
            record.instance = plugin

        self._records = records
        self._startup_order = startup_order
        self._validated = True

    async def start_all(self) -> None:
        """Start loaded plugins in dependency order while isolating failures."""

        for plugin_id in self._startup_order:
            record = self._records[plugin_id]
            if record.instance is None:
                continue
            try:
                await self._start_plugin(plugin_id)
            except PluginOperationError:
                if record.instance.state is not PluginState.ERROR:
                    record.instance.mark_error("dependency_unavailable")

    async def stop_all(self, timeout_seconds: float | None = None) -> None:
        """Stop every loaded plugin in reverse order within one shared budget."""

        plugins = [
            plugin
            for plugin_id in reversed(self._startup_order)
            if (plugin := self._records[plugin_id].instance) is not None
        ]
        if not plugins:
            return

        loop = asyncio.get_running_loop()
        deadline = loop.time() + (
            self._operation_timeout_seconds if timeout_seconds is None else timeout_seconds
        )
        try:
            await self._acquire_operation_lock(deadline)
        except TimeoutError:
            return
        try:
            for index, plugin in enumerate(plugins):
                remaining_plugins = len(plugins) - index
                remaining_seconds = max(0.0, deadline - loop.time())
                slot_timeout = remaining_seconds / remaining_plugins
                try:
                    async with asyncio.timeout(slot_timeout):
                        await plugin.stop()
                except TimeoutError:
                    plugin.mark_error("shutdown_timeout")
                except Exception:
                    plugin.mark_error("shutdown_failure")
        finally:
            self._operation_lock.release()

    async def start_plugin(self, plugin_id: str) -> PluginView:
        """Start one plugin after checking all of its dependencies."""

        deadline = asyncio.get_running_loop().time() + self._operation_timeout_seconds
        await self._acquire_operation_lock(deadline)
        try:
            await self._start_plugin(plugin_id, deadline)
            return self.get_view(plugin_id)
        finally:
            self._operation_lock.release()

    async def stop_plugin(self, plugin_id: str) -> PluginView:
        """Stop one plugin unless an active dependent still needs it."""

        deadline = asyncio.get_running_loop().time() + self._operation_timeout_seconds
        await self._acquire_operation_lock(deadline)
        try:
            plugin = self._get_runtime_plugin(plugin_id)
            active_dependents = self._active_dependents(plugin_id)
            if active_dependents:
                joined = ", ".join(active_dependents)
                raise PluginOperationError(f"active dependents prevent stop: {joined}")
            async with asyncio.timeout(self._remaining_seconds(deadline)):
                if not await plugin.stop():
                    raise PluginOperationError(f"plugin stop failed: {plugin_id}")
            return self.get_view(plugin_id)
        finally:
            self._operation_lock.release()

    async def restart_plugin(self, plugin_id: str) -> PluginView:
        """Stop, reinitialize, and restart one plugin without reloading its code."""

        deadline = asyncio.get_running_loop().time() + self._operation_timeout_seconds
        await self._acquire_operation_lock(deadline)
        try:
            plugin = self._get_runtime_plugin(plugin_id)
            active_dependents = self._active_dependents(plugin_id)
            if active_dependents:
                joined = ", ".join(active_dependents)
                raise PluginOperationError(f"active dependents prevent restart: {joined}")
            async with asyncio.timeout(self._remaining_seconds(deadline)):
                if plugin.state not in {PluginState.STOPPED, PluginState.VALIDATED}:
                    if not await plugin.stop():
                        raise PluginOperationError(f"plugin stop failed: {plugin_id}")
            await self._start_plugin(plugin_id, deadline)
            return self.get_view(plugin_id)
        finally:
            self._operation_lock.release()

    def list_views(self) -> PluginListResponse:
        """Return a deterministic catalog, including isolated failure records."""

        return PluginListResponse(
            plugins=[self.get_view(plugin_id) for plugin_id in sorted(self._records)]
        )

    def get_view(self, plugin_id: str) -> PluginView:
        """Build one stable API representation from its record and health snapshot."""

        record = self._get_record(plugin_id)
        manifest = record.manifest
        if record.instance is None:
            state = PluginState.ERROR
            health = PluginHealth(
                status=HealthStatus.ERROR,
                details={"reason": record.error_reason or "load_error"},
            )
            settings_schema = empty_settings_schema()
        else:
            state = record.instance.state
            health = record.instance.health()
            settings_schema = public_settings_schema(record.instance.settings_class)
        return PluginView(
            id=manifest.id,
            name=manifest.name,
            version=manifest.version,
            description=manifest.description,
            api_version=manifest.api_version,
            state=state,
            available_actions=list(self._available_actions(plugin_id, record)),
            dependencies=list(manifest.dependencies),
            capabilities=list(manifest.capabilities),
            settings_schema=settings_schema,
            frontend=manifest.frontend,
            health=health,
        )

    def platform_status(self) -> PlatformStatusResponse:
        """Classify every record once from lifecycle and one health snapshot."""

        counts = {"running": 0, "degraded": 0, "stopped": 0, "error": 0}
        for record in self._records.values():
            if record.instance is None:
                counts["error"] += 1
                continue
            plugin = record.instance
            health = plugin.health()
            if plugin.state is PluginState.ERROR or health.status is HealthStatus.ERROR:
                counts["error"] += 1
            elif plugin.state is PluginState.RUNNING and health.status is HealthStatus.DEGRADED:
                counts["degraded"] += 1
            elif plugin.state is PluginState.RUNNING and health.status is HealthStatus.HEALTHY:
                counts["running"] += 1
            else:
                counts["stopped"] += 1

        total = len(self._records)
        status: Literal["healthy", "degraded"] = (
            "healthy"
            if counts["running"] == total and counts["degraded"] == counts["error"] == 0
            else "degraded"
        )
        return PlatformStatusResponse(
            status=status,
            version=__version__,
            plugins=PluginCounts(total=total, **counts),
        )

    def routers(self) -> tuple[tuple[str, APIRouter], ...]:
        """Return routers only for successfully loaded plugin instances."""

        routers: list[tuple[str, APIRouter]] = []
        for plugin_id, record in sorted(self._records.items()):
            if record.instance is not None and record.instance.router is not None:
                routers.append((plugin_id, record.instance.router))
        return tuple(routers)

    async def _start_plugin(self, plugin_id: str, deadline: float | None = None) -> None:
        plugin = self._get_runtime_plugin(plugin_id)
        if plugin.state is PluginState.RUNNING:
            return
        operation_deadline = (
            asyncio.get_running_loop().time() + self._operation_timeout_seconds
            if deadline is None
            else deadline
        )
        missing = self._missing_running_dependencies(plugin)
        if missing:
            raise PluginOperationError(
                f"dependencies are not running: {', '.join(sorted(missing))}"
            )

        try:
            settings = self._create_settings(plugin)
        except Exception:
            plugin.mark_error("settings_validation")
            raise PluginOperationError(f"plugin settings are invalid: {plugin_id}") from None
        context = PluginContext(
            plugin_id,
            self._services,
            self._events,
            plugin.manifest.capabilities,
            settings,
        )
        try:
            async with asyncio.timeout(self._remaining_seconds(operation_deadline)):
                await self._initialize_for_start(plugin_id, plugin, context)
                await self._start_initialized(plugin_id, plugin)
        except TimeoutError as exc:
            try:
                async with asyncio.timeout(self._remaining_seconds(operation_deadline)):
                    cleanup_succeeded = await plugin.stop()
            except TimeoutError:
                plugin.mark_error("cleanup_timeout")
            else:
                plugin.mark_error("startup_timeout" if cleanup_succeeded else "cleanup_failed")
            raise PluginOperationTimeoutError(f"plugin startup timed out: {plugin_id}") from exc

    @staticmethod
    def _remaining_seconds(deadline: float) -> float:
        return max(0.0, deadline - asyncio.get_running_loop().time())

    async def _acquire_operation_lock(self, deadline: float) -> None:
        async with asyncio.timeout(self._remaining_seconds(deadline)):
            await self._operation_lock.acquire()

    async def _initialize_for_start(
        self,
        plugin_id: str,
        plugin: BasePlugin,
        context: PluginContext,
    ) -> None:
        if plugin.state is PluginState.INITIALIZED:
            return
        if not await plugin.initialize(context):
            raise PluginOperationError(f"plugin initialize failed: {plugin_id}")
        missing_capabilities = context.missing_capabilities()
        if not missing_capabilities:
            return
        await plugin.stop()
        plugin.mark_error("capability_contract")
        joined = ", ".join(missing_capabilities)
        raise PluginOperationError(
            f"plugin did not register declared capabilities: {plugin_id}: {joined}"
        )

    @staticmethod
    async def _start_initialized(plugin_id: str, plugin: BasePlugin) -> None:
        if await plugin.start():
            return
        details = plugin.health().details
        failure_reason = details.get("reason") if details else None
        await plugin.stop()
        plugin.mark_error(failure_reason if isinstance(failure_reason, str) else "start_failed")
        raise PluginOperationError(f"plugin start failed: {plugin_id}")

    @staticmethod
    def _create_settings(plugin: BasePlugin) -> PluginSettings | None:
        settings_class = plugin.settings_class
        if settings_class is None:
            return None
        return load_plugin_settings(settings_class, plugin.manifest.id)

    def _missing_running_dependencies(self, plugin: BasePlugin) -> list[str]:
        missing: list[str] = []
        for dependency in plugin.manifest.dependencies:
            provider = self._get_record(dependency.id).instance
            if provider is None or provider.state is not PluginState.RUNNING:
                missing.append(dependency.id)
        return missing

    def _available_actions(
        self,
        plugin_id: str,
        record: PluginRecord,
    ) -> tuple[PluginAction, ...]:
        plugin = record.instance
        if (
            plugin is None
            or self._active_dependents(plugin_id)
            or self._missing_running_dependencies(plugin)
        ):
            return ()
        if plugin.state is PluginState.RUNNING:
            return (PluginAction.STOP, PluginAction.RESTART)
        return (PluginAction.START,)

    @staticmethod
    def _validate_capability_ownership(manifests: Iterable[PluginManifest]) -> None:
        owners: dict[str, str] = {}
        for manifest in manifests:
            for capability in manifest.capabilities:
                previous_owner = owners.get(capability)
                if previous_owner is not None:
                    raise PluginOperationError(
                        "capability has multiple owners: "
                        f"{capability}: {previous_owner}, {manifest.id}"
                    )
                owners[capability] = manifest.id

    @staticmethod
    def _has_reserved_route(router: APIRouter | None) -> bool:
        if router is None:
            return False
        reserved_variants = tuple(
            path
            for reserved_path in RESERVED_PLUGIN_PATHS
            for path in (reserved_path, f"{reserved_path}/")
        )
        for route in router.routes:
            path_regex = getattr(route, "path_regex", None)
            if isinstance(path_regex, re.Pattern) and any(
                path_regex.fullmatch(path) is not None for path in reserved_variants
            ):
                return True
        return False

    def _active_dependents(self, plugin_id: str) -> list[str]:
        return sorted(
            record.manifest.id
            for record in self._records.values()
            if record.instance is not None
            and any(dependency.id == plugin_id for dependency in record.manifest.dependencies)
            and record.instance.state is PluginState.RUNNING
        )

    def _get_record(self, plugin_id: str) -> PluginRecord:
        try:
            return self._records[plugin_id]
        except KeyError as exc:
            raise PluginNotFoundError(f"plugin not found: {plugin_id}") from exc

    def _get_runtime_plugin(self, plugin_id: str) -> BasePlugin:
        record = self._get_record(plugin_id)
        if record.instance is None:
            raise PluginOperationError(
                f"plugin is unavailable: {plugin_id}: {record.error_reason or 'load_error'}"
            )
        return record.instance
