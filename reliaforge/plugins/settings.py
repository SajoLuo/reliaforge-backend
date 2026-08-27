"""Single-source settings contract for ReliaForge plugins."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any, TypeVar, cast

from pydantic_settings import BaseSettings, SettingsConfigDict

SettingsT = TypeVar("SettingsT", bound="PluginSettings")


class PluginSettings(BaseSettings):
    """Base class with platform-owned settings source behavior."""

    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        extra="forbid",
    )


def plugin_env_prefix(plugin_id: str) -> str:
    """Return the canonical environment prefix for one plugin."""

    return f"RELIAFORGE_{plugin_id.upper()}_"


def load_plugin_settings(settings_class: type[SettingsT], plugin_id: str) -> SettingsT:
    """Construct settings with the platform-owned per-plugin environment scope."""

    factory = cast(Callable[..., SettingsT], settings_class)
    return factory(
        _env_prefix=plugin_env_prefix(plugin_id),
        _env_nested_delimiter="__",
        _env_file=None,
    )


def empty_settings_schema() -> dict[str, Any]:
    """Return the stable schema used by plugins without runtime settings."""

    return {"type": "object", "properties": {}, "additionalProperties": False}


def public_settings_schema(settings_class: type[PluginSettings] | None) -> dict[str, Any]:
    """Derive a public schema while removing defaults from secret fields."""

    if settings_class is None:
        return empty_settings_schema()
    schema = deepcopy(settings_class.model_json_schema())
    _strip_secret_defaults(schema)
    return schema


def _strip_secret_defaults(node: object) -> None:
    if isinstance(node, dict):
        if node.get("format") == "password" or node.get("writeOnly") is True:
            node.pop("default", None)
        for value in node.values():
            _strip_secret_defaults(value)
    elif isinstance(node, list):
        for value in node:
            _strip_secret_defaults(value)
