"""Thin HTTP router for the neutral runbook preview."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, HTTPException, Query, status

from .models import RunbookPreview
from .service import RunbookUnavailableError

if TYPE_CHECKING:
    from .plugin import Plugin


def create_router(plugin: Plugin) -> APIRouter:
    """Create the authenticated runbook preview route."""

    router = APIRouter(tags=["runbook"])

    @router.get("/preview", response_model=RunbookPreview)
    async def preview(
        title: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    ) -> RunbookPreview:
        try:
            return await plugin.preview(title)
        except RunbookUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Runbook plugin is not running",
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            plugin.logger.error("runbook preview failed (%s)", type(exc).__name__)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error",
            ) from exc

    return router
