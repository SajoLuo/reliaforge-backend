"""FastAPI application factory for the public ReliaForge backend."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from reliaforge import __version__
from reliaforge.api.router import create_management_router
from reliaforge.auth import build_management_auth
from reliaforge.config import AppSettings
from reliaforge.plugins.manager import PluginManager
from reliaforge.runtime import RuntimeState


def create_app(settings: AppSettings | None = None) -> FastAPI:
    """Build an app from validated settings and manifest-first discovery."""

    runtime_settings = settings or AppSettings()
    bundled_root = Path(__file__).parent / "plugins"
    manager = PluginManager(
        plugin_roots=(bundled_root, *runtime_settings.external_plugin_paths()),
        operation_timeout_seconds=runtime_settings.plugin_operation_timeout_seconds,
        event_handler_timeout_seconds=runtime_settings.event_handler_timeout_seconds,
    )
    manager.discover()
    manager.validate()
    runtime_state = RuntimeState()
    management_auth = build_management_auth(runtime_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            async with asyncio.timeout(runtime_settings.app_startup_timeout_seconds):
                await manager.start_all()
            runtime_state.mark_ready()
            yield
        finally:
            runtime_state.mark_stopping()
            await manager.stop_all(runtime_settings.shutdown_timeout_seconds)

    expose_api_docs = runtime_settings.environment != "production"
    app = FastAPI(
        title="ReliaForge API",
        description="Lifecycle-managed plugin platform API",
        version=__version__,
        docs_url="/api/v1/docs" if expose_api_docs else None,
        redoc_url=None,
        openapi_url="/api/v1/openapi.json" if expose_api_docs else None,
        lifespan=lifespan,
    )
    app.state.plugin_manager = manager
    app.state.runtime_state = runtime_state
    app.state.settings = runtime_settings
    if runtime_settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=runtime_settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Accept", "Content-Type"],
        )
    app.include_router(
        create_management_router(
            manager,
            management_auth,
            runtime_state,
        )
    )
    for plugin_id, plugin_router in manager.routers():
        app.include_router(
            plugin_router,
            prefix=f"/api/v1/plugins/{plugin_id}",
            dependencies=[Depends(management_auth)],
        )
    return app
