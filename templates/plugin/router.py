"""Thin HTTP routes for {{plugin_name}}."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, status

from .models import Message
from .service import MessageUnavailableError

if TYPE_CHECKING:
    from .plugin import Plugin


def create_router(plugin: Plugin) -> APIRouter:
    router = APIRouter(tags=["{{plugin_id}}"])

    @router.get("/message", response_model=Message)
    async def message() -> Message:
        try:
            return plugin.get_message()
        except MessageUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Plugin is not running",
            ) from exc
        except HTTPException:
            raise
        except Exception as exc:
            plugin.logger.error("generated plugin request failed (%s)", type(exc).__name__)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error",
            ) from exc

    return router
