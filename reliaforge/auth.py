"""Management authentication dependencies."""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable
from ipaddress import ip_address

from fastapi import HTTPException, Request, status
from pydantic import BaseModel

from reliaforge.config import AppSettings


class ManagementPrincipal(BaseModel):
    """Minimal authenticated identity passed to management routes."""

    identity: str
    source: str


ManagementAuth = Callable[[Request], Awaitable[ManagementPrincipal]]


def _development_origin_is_allowed(request: Request, settings: AppSettings) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return True
    host = f"[{settings.host}]" if ":" in settings.host else settings.host
    allowed_origins = {
        f"http://{host}:{settings.port}",
        *(value.rstrip("/") for value in settings.cors_origins),
    }
    return origin.rstrip("/") in allowed_origins


def _authenticate_development(request: Request, settings: AppSettings) -> ManagementPrincipal:
    if not _development_origin_is_allowed(request, settings):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Development management origin is not allowed",
        )
    client_host = request.client.host if request.client else ""
    if settings.environment == "test" and client_host == "testclient":
        return ManagementPrincipal(identity="local-test", source="development")
    try:
        is_loopback = ip_address(client_host).is_loopback
    except ValueError:
        is_loopback = False
    if not is_loopback:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Development management access is loopback-only",
        )
    return ManagementPrincipal(identity="local-development", source="development")


def build_management_auth(settings: AppSettings) -> ManagementAuth:
    """Create a request dependency bound to validated runtime settings."""

    async def require_management_auth(request: Request) -> ManagementPrincipal:
        if settings.auth_mode == "development":
            return _authenticate_development(request, settings)

        identity = request.headers.get(settings.proxy_identity_header, "").strip()
        provided = request.headers.get(settings.proxy_secret_header, "")
        configured = settings.proxy_shared_secret
        client_host = request.client.host if request.client else ""
        try:
            client_address = ip_address(client_host)
        except ValueError:
            client_address = None
        if client_address is None or not any(
            client_address.version == network.version and client_address in network
            for network in settings.trusted_proxy_networks()
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Management proxy is not trusted",
            )
        if not identity or configured is None or not provided:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Management authentication required",
            )
        if not secrets.compare_digest(provided, configured.get_secret_value()):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Management authentication rejected",
            )
        return ManagementPrincipal(identity=identity, source="proxy")

    return require_management_auth
