"""Thin FastAPI routes for the neutral demo plugin."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, status

from .models import GreetingResponse
from .service import GreetingUnavailableError

if TYPE_CHECKING:
    from .plugin import Plugin


def create_router(plugin: Plugin) -> APIRouter:
    """Create the demo greeting router."""

    router = APIRouter(tags=["demo"])

    @router.get("/greeting", response_model=GreetingResponse)
    async def greeting() -> GreetingResponse:
        try:
            result = plugin.greet()
            return GreetingResponse.model_validate(result.model_dump())
        except GreetingUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Demo plugin is not running",
            ) from exc
        except HTTPException:
            raise
        except Exception as exc:
            plugin.logger.error("demo greeting failed (%s)", type(exc).__name__)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error",
            ) from exc

    return router
