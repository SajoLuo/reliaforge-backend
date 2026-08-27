"""Typed service and single-source plugin settings contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, runtime_checkable

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import SettingsConfigDict

from reliaforge.app import create_app
from reliaforge.config import AppSettings
from reliaforge.events import EventBus
from reliaforge.plugins.context import (
    PluginContext,
    PluginSettingsTypeError,
    ServiceInterfaceError,
)
from reliaforge.plugins.contract import BasePlugin, PluginHealth, PluginManifest
from reliaforge.plugins.manager import PluginManager
from reliaforge.plugins.settings import (
    PluginSettings,
    load_plugin_settings,
    public_settings_schema,
)
from reliaforge.services import ServiceContainer, ServiceNotFoundError


@runtime_checkable
class MessageCapability(Protocol):
    def message(self) -> str: ...


class CompatibleService:
    def message(self) -> str:
        return "ready"


class IncompatibleService:
    pass


class NestedPolicy(BaseModel):
    limit: int = Field(default=3, ge=1, le=10)


class NestedSettings(PluginSettings):
    policy: NestedPolicy = Field(default_factory=NestedPolicy)


class OtherSettings(PluginSettings):
    enabled: bool = True


class DotenvOptInSettings(PluginSettings):
    model_config = SettingsConfigDict(env_file=".env")

    enabled: bool = True


class SecretSettings(PluginSettings):
    token: SecretStr = Field(min_length=20)


class DefaultSecretSettings(PluginSettings):
    token: SecretStr = SecretStr("masked-default-fixture")


class SettingsPlugin(BasePlugin):
    settings_class = NestedSettings

    async def _on_initialize(self) -> None:
        return None

    async def _on_start(self) -> None:
        return None

    async def _on_stop(self) -> None:
        return None

    def _on_health_check(self) -> PluginHealth:
        raise NotImplementedError


def _manifest(plugin_id: str = "nested_plugin") -> PluginManifest:
    return PluginManifest.model_validate(
        {
            "id": plugin_id,
            "name": "Nested Plugin",
            "version": "1.0.0",
            "description": "Settings contract fixture",
            "api_version": "v1",
            "entrypoint": "plugin:Plugin",
        }
    )


def test_get_service_enforces_caller_owned_runtime_protocol() -> None:
    services = ServiceContainer()
    services.register("provider.message", "provider", CompatibleService())
    services.register("provider.other", "provider", IncompatibleService())
    context = PluginContext("consumer", services, EventBus(1.0))

    capability = context.get_service("provider.message", MessageCapability)
    assert capability.message() == "ready"
    with pytest.raises(ServiceNotFoundError, match="service not found"):
        context.get_service("provider.missing", MessageCapability)
    with pytest.raises(ServiceInterfaceError, match="interface is incompatible"):
        context.get_service("provider.other", MessageCapability)


def test_manager_owns_env_prefix_nested_parsing_and_settings_injection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RELIAFORGE_NESTED_PLUGIN_POLICY__LIMIT", "7")
    manager = PluginManager((), 1.0, 1.0)
    settings = manager._create_settings(SettingsPlugin(_manifest()))
    assert isinstance(settings, NestedSettings)
    assert settings.policy.limit == 7

    context = PluginContext("nested_plugin", ServiceContainer(), EventBus(1.0), settings=settings)
    assert context.get_settings(NestedSettings) is settings
    with pytest.raises(PluginSettingsTypeError, match="type is incompatible"):
        context.get_settings(OtherSettings)


def test_public_secret_schema_never_contains_secret_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_value = "fixture-secret-value-long-enough"
    monkeypatch.setenv("RELIAFORGE_SECRET_PLUGIN_TOKEN", secret_value)
    settings = load_plugin_settings(SecretSettings, "secret_plugin")
    assert settings.token.get_secret_value() == secret_value
    rendered = json.dumps(public_settings_schema(SecretSettings), sort_keys=True)
    assert secret_value not in rendered
    assert '"format": "password"' in rendered
    assert '"writeOnly": true' in rendered
    default_schema = public_settings_schema(DefaultSecretSettings)
    token_schema = default_schema["properties"]["token"]
    assert "default" not in token_schema
    assert "masked-default-fixture" not in json.dumps(default_schema)


def test_plugin_settings_do_not_parse_shared_dotenv_as_cross_plugin_extras(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / ".env").write_text(
        "RELIAFORGE_NESTED_PLUGIN_POLICY__LIMIT=9\n"
        "RELIAFORGE_OTHER_PLUGIN_ENABLED=false\n"
        "RELIAFORGE_ENVIRONMENT=production\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    nested = load_plugin_settings(NestedSettings, "nested_plugin")
    other = load_plugin_settings(OtherSettings, "other_plugin")
    assert nested.policy.limit == 3
    assert other.enabled is True


def test_platform_disables_plugin_subclass_dotenv_opt_in(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / ".env").write_text(
        "RELIAFORGE_DOTENV_OPT_IN_ENABLED=false\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    settings = load_plugin_settings(DotenvOptInSettings, "dotenv_opt_in")
    assert settings.enabled is True


def test_restart_rebuilds_settings_and_discards_old_context(
    monkeypatch: pytest.MonkeyPatch,
    test_settings: AppSettings,
) -> None:
    monkeypatch.setenv("RELIAFORGE_DEMO_GREETING", "First greeting")
    app = create_app(test_settings)
    with TestClient(app) as client:
        assert (
            client.get("/api/v1/plugins/demo/greeting")
            .json()["message"]
            .startswith("First greeting")
        )
        plugin = app.state.plugin_manager._records["demo"].instance
        assert plugin is not None and plugin.context is not None
        old_context = plugin.context
        old_settings = old_context.get_settings(plugin.settings_class)

        monkeypatch.setenv("RELIAFORGE_DEMO_GREETING", "Second greeting")
        assert client.post("/api/v1/plugins/runbook/stop").status_code == 200
        assert client.post("/api/v1/plugins/demo/restart").status_code == 200

        assert plugin.context is not None
        new_settings = plugin.context.get_settings(plugin.settings_class)
        assert new_settings is not old_settings
        with pytest.raises(LookupError, match="not declared"):
            old_context.get_settings(plugin.settings_class)
        assert (
            client.get("/api/v1/plugins/demo/greeting")
            .json()["message"]
            .startswith("Second greeting")
        )


def test_invalid_settings_error_does_not_echo_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from reliaforge.scaffold import scaffold_plugin

    plugin_dir = scaffold_plugin("secret_plugin", tmp_path)
    settings_path = plugin_dir / "settings.py"
    source = settings_path.read_text(encoding="utf-8")
    source = source.replace("from pydantic import Field", "from pydantic import Field, SecretStr")
    source = source.replace(
        'message: str = Field(default="Generated plugin is running", min_length=1, max_length=200)',
        'message: str = "safe"\n    token: SecretStr = Field(min_length=20)',
    )
    settings_path.write_text(source, encoding="utf-8")
    private_value = "short-private"
    monkeypatch.setenv("RELIAFORGE_SECRET_PLUGIN_TOKEN", private_value)

    manager = PluginManager((tmp_path,), 1.0, 1.0)
    manager.discover()
    manager.validate()
    import asyncio

    asyncio.run(manager.start_all())
    assert manager.get_view("secret_plugin").health.details == {"reason": "settings_validation"}
    captured = capsys.readouterr()
    assert private_value not in captured.out
    assert private_value not in captured.err


def test_runbook_has_no_provider_import_or_execution_primitives() -> None:
    root = Path(__file__).parents[1] / "reliaforge" / "plugins" / "runbook"
    source = "\n".join(path.read_text(encoding="utf-8") for path in sorted(root.glob("*.py")))
    assert "reliaforge.plugins.demo" not in source
    assert "from ..demo" not in source
    for forbidden in ("subprocess", "socket", "requests", "open(", "write_text", "write_bytes"):
        assert forbidden not in source
