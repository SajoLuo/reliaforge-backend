"""Runtime configuration with production-safe authentication defaults."""

from __future__ import annotations

import os
from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MINIMUM_PROXY_SECRET_LENGTH = 32
PROXY_SECRET_PLACEHOLDERS = {
    "change-me",
    "placeholder",
    "replace-me",
    "replace-with-a-random-value",
}


class AppSettings(BaseSettings):
    """Validated settings for one ReliaForge process."""

    model_config = SettingsConfigDict(
        env_prefix="RELIAFORGE_",
        env_file=".env",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    auth_mode: Literal["development", "proxy"] = "development"
    proxy_identity_header: str = "X-ReliaForge-Identity"
    proxy_secret_header: str = "X-ReliaForge-Proxy-Secret"
    proxy_shared_secret: SecretStr | None = Field(default=None, repr=False)
    proxy_trusted_networks: list[str] = Field(default_factory=list)
    cors_origins: list[str] = Field(default_factory=list)
    plugin_paths: str = ""
    plugin_operation_timeout_seconds: float = Field(default=10.0, gt=0, le=300)
    app_startup_timeout_seconds: float = Field(default=30.0, gt=0, le=600)
    shutdown_timeout_seconds: float = Field(default=10.0, gt=0, le=300)
    event_handler_timeout_seconds: float = Field(default=2.0, gt=0, le=30)

    @model_validator(mode="after")
    def validate_auth_boundary(self) -> Self:
        """Reject configurations that could expose anonymous management operations."""

        try:
            bind_address = ip_address(self.host)
        except ValueError as exc:
            raise ValueError("host must be an IP address") from exc

        self._validate_development_auth(bind_address.is_loopback)
        self._validate_proxy_auth()
        self._validate_cors_origins()
        return self

    def _validate_development_auth(self, is_loopback: bool) -> None:
        if self.auth_mode != "development":
            return
        if self.environment not in {"development", "test"}:
            raise ValueError("production requires proxy authentication")
        if not is_loopback:
            raise ValueError("development authentication requires a loopback host")

    def _validate_proxy_auth(self) -> None:
        if self.auth_mode != "proxy":
            return
        if self.proxy_shared_secret is None:
            raise ValueError("proxy authentication requires an injected shared secret")
        secret_value = self.proxy_shared_secret.get_secret_value()
        if any(not 33 <= ord(character) <= 126 for character in secret_value):
            raise ValueError("proxy shared secret must use printable ASCII without spaces")
        if (
            len(secret_value) < MINIMUM_PROXY_SECRET_LENGTH
            or secret_value.strip().lower() in PROXY_SECRET_PLACEHOLDERS
        ):
            raise ValueError("proxy authentication requires a strong injected shared secret")
        if not self.proxy_identity_header.strip() or not self.proxy_secret_header.strip():
            raise ValueError("proxy authentication headers must be non-empty")
        if not self.proxy_trusted_networks:
            raise ValueError("proxy authentication requires at least one trusted network")
        try:
            networks = [ip_network(value, strict=False) for value in self.proxy_trusted_networks]
        except ValueError as exc:
            raise ValueError("proxy trusted networks must be valid IP networks") from exc
        if any(network.prefixlen == 0 for network in networks):
            raise ValueError("proxy trusted networks must not trust every address")
        if len(networks) != len(set(networks)):
            raise ValueError("proxy trusted networks must be unique")

    def _validate_cors_origins(self) -> None:
        for origin in self.cors_origins:
            parsed = urlsplit(origin)
            if origin == "*":
                raise ValueError("wildcard CORS origins are not allowed")
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("CORS origins must be explicit HTTP origins")

    def trusted_proxy_networks(self) -> tuple[IPv4Network | IPv6Network, ...]:
        """Return the validated direct-peer networks trusted to inject identity headers."""

        return tuple(ip_network(value, strict=False) for value in self.proxy_trusted_networks)

    def external_plugin_paths(self) -> tuple[Path, ...]:
        """Return normalized external plugin roots without touching the filesystem."""

        if not self.plugin_paths.strip():
            return ()
        return tuple(
            Path(value).expanduser().resolve()
            for value in self.plugin_paths.split(os.pathsep)
            if value.strip()
        )
