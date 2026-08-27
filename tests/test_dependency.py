"""Dependency validation and deterministic ordering."""

import pytest

from reliaforge.plugins.contract import PluginManifest
from reliaforge.plugins.dependency import DependencyResolver, PluginDependencyError


def _manifest(
    plugin_id: str,
    dependencies: list[tuple[str, str]] | None = None,
    version: str = "1.0.0",
) -> PluginManifest:
    return PluginManifest.model_validate(
        {
            "id": plugin_id,
            "name": plugin_id.title(),
            "version": version,
            "description": "Dependency fixture",
            "api_version": "v1",
            "entrypoint": "plugin:Plugin",
            "dependencies": [
                {"id": dependency_id, "version": version_range}
                for dependency_id, version_range in dependencies or []
            ],
            "capabilities": [],
            "frontend": {},
        }
    )


def test_resolver_valid_graph_returns_dependency_first_order() -> None:
    order = DependencyResolver().resolve(
        [
            _manifest("gamma", [("beta", "^1.0.0")]),
            _manifest("alpha"),
            _manifest("beta", [("alpha", ">=1.0.0,<2.0.0")]),
        ]
    )
    assert order == ("alpha", "beta", "gamma")


def test_resolver_missing_dependency_raises_stable_error() -> None:
    with pytest.raises(PluginDependencyError, match="missing dependency"):
        DependencyResolver().resolve([_manifest("alpha", [("missing", "^1.0.0")])])


def test_resolver_cycle_raises_stable_error() -> None:
    with pytest.raises(PluginDependencyError, match="cycle"):
        DependencyResolver().resolve(
            [
                _manifest("alpha", [("beta", "^1.0.0")]),
                _manifest("beta", [("alpha", "^1.0.0")]),
            ]
        )


def test_resolver_version_mismatch_raises_before_startup() -> None:
    with pytest.raises(PluginDependencyError, match="version mismatch"):
        DependencyResolver().resolve(
            [
                _manifest("provider", version="2.0.0"),
                _manifest("consumer", [("provider", "^1.0.0")]),
            ]
        )
