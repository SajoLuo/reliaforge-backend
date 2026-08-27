"""Thin management HTTP routes over the plugin manager service."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from reliaforge import __version__
from reliaforge.api.models import (
    LivenessResponse,
    PlatformStatusResponse,
    PluginListResponse,
    PluginView,
    ReadinessResponse,
)
from reliaforge.auth import ManagementAuth
from reliaforge.logging import get_platform_logger
from reliaforge.plugins.manager import (
    PluginManager,
    PluginNotFoundError,
    PluginOperationError,
    PluginOperationTimeoutError,
)
from reliaforge.runtime import RuntimePhase, RuntimeState

logger = get_platform_logger()


def create_management_router(
    manager: PluginManager,
    management_auth: ManagementAuth,
    runtime_state: RuntimeState,
) -> APIRouter:
    """Create the platform probes, status, catalog, and lifecycle routes."""

    router = APIRouter(prefix="/api/v1", tags=["platform"])
    router.include_router(_create_probe_router(runtime_state))
    router.include_router(_create_catalog_router(manager))
    router.include_router(_create_lifecycle_router(manager, management_auth))
    return router


def _create_probe_router(runtime_state: RuntimeState) -> APIRouter:
    router = APIRouter()

    @router.get("/live", response_model=LivenessResponse)
    async def live() -> LivenessResponse:
        return LivenessResponse(version=__version__)

    @router.get(
        "/ready",
        response_model=ReadinessResponse,
        responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
    )
    async def ready() -> ReadinessResponse | JSONResponse:
        phase = runtime_state.phase
        snapshot = ReadinessResponse(
            status="ready" if phase is RuntimePhase.READY else "not_ready",
            version=__version__,
            phase=phase,
        )
        if phase is not RuntimePhase.READY:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content=snapshot.model_dump(mode="json"),
            )
        return snapshot

    return router


def _create_catalog_router(manager: PluginManager) -> APIRouter:
    router = APIRouter()

    @router.get("/status", response_model=PlatformStatusResponse)
    async def platform_status() -> PlatformStatusResponse:
        return manager.platform_status()

    @router.get("/plugins", response_model=PluginListResponse)
    async def list_plugins() -> PluginListResponse:
        return manager.list_views()

    @router.get("/plugins/{plugin_id}", response_model=PluginView)
    async def get_plugin(plugin_id: str) -> PluginView:
        try:
            return manager.get_view(plugin_id)
        except PluginNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return router


def _create_lifecycle_router(
    manager: PluginManager,
    management_auth: ManagementAuth,
) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/plugins/{plugin_id}/start",
        response_model=PluginView,
        dependencies=[Depends(management_auth)],
    )
    async def start_plugin(plugin_id: str) -> PluginView:
        return await _run_operation(manager.start_plugin, plugin_id)

    @router.post(
        "/plugins/{plugin_id}/stop",
        response_model=PluginView,
        dependencies=[Depends(management_auth)],
    )
    async def stop_plugin(plugin_id: str) -> PluginView:
        return await _run_operation(manager.stop_plugin, plugin_id)

    @router.post(
        "/plugins/{plugin_id}/restart",
        response_model=PluginView,
        dependencies=[Depends(management_auth)],
    )
    async def restart_plugin(plugin_id: str) -> PluginView:
        return await _run_operation(manager.restart_plugin, plugin_id)

    return router


async def _run_operation(
    operation: Callable[[str], Awaitable[PluginView]],
    plugin_id: str,
) -> PluginView:
    try:
        return await operation(plugin_id)
    except PluginNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PluginOperationTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Plugin operation timed out",
        ) from exc
    except PluginOperationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Plugin operation timed out",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("plugin management operation failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from exc
