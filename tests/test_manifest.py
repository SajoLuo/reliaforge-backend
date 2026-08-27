"""Manifest contract behavior."""

import pytest
from pydantic import ValidationError

from reliaforge.plugins.contract import PluginManifest


def _manifest(**overrides: object) -> PluginManifest:
    raw: dict[str, object] = {
        "id": "alpha",
        "name": "Alpha",
        "version": "1.2.3",
        "description": "A test plugin",
        "api_version": "v1",
        "entrypoint": "plugin:Plugin",
        "dependencies": [],
        "capabilities": ["alpha.read"],
        "frontend": {},
    }
    raw.update(overrides)
    return PluginManifest.model_validate(raw)


def test_manifest_valid_input_round_trips_with_pydantic_v2() -> None:
    manifest = _manifest()
    restored = PluginManifest.model_validate(manifest.model_dump())
    assert restored == manifest


def test_manifest_accepts_semver_build_metadata() -> None:
    assert _manifest(version="1.2.3-beta.1+public.4").version == "1.2.3-beta.1+public.4"


def test_manifest_invalid_identity_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _manifest(id="Invalid Name")


def test_manifest_non_semver_plugin_version_is_rejected() -> None:
    with pytest.raises(ValidationError, match="valid SemVer"):
        _manifest(version="1.2")


def test_manifest_unsupported_api_version_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _manifest(api_version="v2")


def test_manifest_string_dependency_and_invalid_range_are_rejected() -> None:
    with pytest.raises(ValidationError):
        _manifest(dependencies=["beta"])
    with pytest.raises(ValidationError, match="valid SemVer range"):
        _manifest(dependencies=[{"id": "beta", "version": "not a range"}])


def test_manifest_duplicate_dependency_ids_are_rejected() -> None:
    with pytest.raises(ValidationError, match="dependency ids must be unique"):
        _manifest(
            dependencies=[
                {"id": "beta", "version": "^1.0.0"},
                {"id": "beta", "version": "^2.0.0"},
            ]
        )


def test_manifest_duplicate_capabilities_are_rejected() -> None:
    with pytest.raises(ValidationError):
        _manifest(capabilities=["alpha.read", "alpha.read"])


def test_manifest_capabilities_must_be_dotted_service_names() -> None:
    with pytest.raises(ValidationError, match="dotted public service names"):
        _manifest(capabilities=["read"])


def test_manifest_rejects_removed_settings_route_and_icon_contracts() -> None:
    with pytest.raises(ValidationError, match="settings_schema"):
        _manifest(settings_schema={"type": "object"})
    with pytest.raises(ValidationError, match="route"):
        _manifest(frontend={"route": "/plugins/beta"})
    with pytest.raises(ValidationError, match="icon"):
        _manifest(frontend={"icon": "plug"})
    with pytest.raises(ValidationError):
        _manifest(frontend={"route": "https://example.com/plugins/alpha"})
