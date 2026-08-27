"""Pydantic v2 models shared by management endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from reliaforge.plugins.contract import (
    FrontendMetadata,
    PluginAction,
    PluginDependency,
    PluginHealth,
    PluginState,
)
from reliaforge.runtime import RuntimePhase


class PluginView(BaseModel):
    """Stable plugin catalog and detail representation."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    version: str
    description: str
    api_version: Literal["v1"]
    state: PluginState
    available_actions: list[PluginAction]
    dependencies: list[PluginDependency]
    capabilities: list[str]
    settings_schema: dict[str, JsonValue]
    frontend: FrontendMetadata
    health: PluginHealth


class PluginListResponse(BaseModel):
    """Plugin catalog envelope."""

    plugins: list[PluginView]


class PluginCounts(BaseModel):
    """Health summary grouped by runtime state."""

    total: int = Field(ge=0)
    running: int = Field(ge=0)
    degraded: int = Field(ge=0)
    stopped: int = Field(ge=0)
    error: int = Field(ge=0)


class PlatformStatusResponse(BaseModel):
    """Side-effect-free plugin status summary for operators and the UI."""

    status: Literal["healthy", "degraded"]
    version: str
    plugins: PluginCounts


class LivenessResponse(BaseModel):
    """Process liveness response that does not inspect plugins or dependencies."""

    status: Literal["alive"] = "alive"
    version: str


class ReadinessResponse(BaseModel):
    """Process-local readiness snapshot."""

    status: Literal["ready", "not_ready"]
    version: str
    phase: RuntimePhase
