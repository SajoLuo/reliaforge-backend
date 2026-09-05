"""Two-phase discovery and executable capability contract behavior."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from reliaforge.plugins.dependency import PluginDependencyError
from reliaforge.plugins.loader import PluginLoadError
from reliaforge.plugins.manager import PluginManager, PluginOperationError
from reliaforge.scaffold import scaffold_plugin


def _update_manifest(plugin_dir: Path, **updates: object) -> None:
    manifest_path = plugin_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(updates)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _prepend_import_marker(plugin_dir: Path, marker: Path) -> None:
    source_path = plugin_dir / "plugin.py"
    source = source_path.read_text(encoding="utf-8")
    marker_statement = f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
    source_path.write_text(marker_statement + source, encoding="utf-8")


def test_invalid_dependency_graph_fails_before_any_plugin_import(tmp_path: Path) -> None:
    plugin_dir = scaffold_plugin("invalid_graph", tmp_path)
    marker = tmp_path / "imported.marker"
    _update_manifest(
        plugin_dir,
        dependencies=[{"id": "missing_plugin", "version": "^1.0.0"}],
    )
    _prepend_import_marker(plugin_dir, marker)

    manager = PluginManager((tmp_path,), 1.0, 1.0)
    manager.discover()
    assert not marker.exists()
    with pytest.raises(PluginDependencyError, match="missing dependency"):
        manager.validate()
    assert not marker.exists()


def test_dependency_cycle_fails_before_any_plugin_import(tmp_path: Path) -> None:
    first = scaffold_plugin("cycle_first", tmp_path)
    second = scaffold_plugin("cycle_second", tmp_path)
    first_marker = tmp_path / "cycle-first.marker"
    second_marker = tmp_path / "cycle-second.marker"
    _update_manifest(
        first,
        dependencies=[{"id": "cycle_second", "version": "^0.1.0"}],
    )
    _update_manifest(
        second,
        dependencies=[{"id": "cycle_first", "version": "^0.1.0"}],
    )
    _prepend_import_marker(first, first_marker)
    _prepend_import_marker(second, second_marker)

    manager = PluginManager((tmp_path,), 1.0, 1.0)
    manager.discover()
    with pytest.raises(PluginDependencyError, match="cycle"):
        manager.validate()
    assert not first_marker.exists()
    assert not second_marker.exists()


def test_unsupported_api_version_fails_before_plugin_import(tmp_path: Path) -> None:
    plugin_dir = scaffold_plugin("future_contract", tmp_path)
    marker = tmp_path / "future.marker"
    _update_manifest(plugin_dir, api_version="v2")
    _prepend_import_marker(plugin_dir, marker)

    manager = PluginManager((tmp_path,), 1.0, 1.0)
    with pytest.raises(PluginLoadError, match="invalid manifest"):
        manager.discover()
    assert not marker.exists()


def test_utf8_bom_manifest_is_accepted(tmp_path: Path) -> None:
    plugin_dir = scaffold_plugin("bom_manifest", tmp_path)
    manifest_path = plugin_dir / "manifest.json"
    manifest = manifest_path.read_text(encoding="utf-8")
    manifest_path.write_text(manifest, encoding="utf-8-sig")

    manager = PluginManager((tmp_path,), 1.0, 1.0)
    manager.discover()
    manager.validate()

    assert manager.get_view("bom_manifest").state == "validated"


def test_duplicate_capability_owners_fail_before_plugin_import(tmp_path: Path) -> None:
    first = scaffold_plugin("first_plugin", tmp_path)
    second = scaffold_plugin("second_plugin", tmp_path)
    first_marker = tmp_path / "first.marker"
    second_marker = tmp_path / "second.marker"
    _update_manifest(first, capabilities=["shared.service"])
    _update_manifest(second, capabilities=["shared.service"])
    _prepend_import_marker(first, first_marker)
    _prepend_import_marker(second, second_marker)

    manager = PluginManager((tmp_path,), 1.0, 1.0)
    manager.discover()
    with pytest.raises(PluginOperationError, match="multiple owners"):
        manager.validate()
    assert not first_marker.exists()
    assert not second_marker.exists()


def test_dependency_version_mismatch_fails_before_plugin_import(tmp_path: Path) -> None:
    provider = scaffold_plugin("versioned_provider", tmp_path)
    consumer = scaffold_plugin("versioned_consumer", tmp_path)
    provider_marker = tmp_path / "versioned-provider.marker"
    consumer_marker = tmp_path / "versioned-consumer.marker"
    _update_manifest(provider, version="2.0.0")
    _update_manifest(
        consumer,
        dependencies=[{"id": "versioned_provider", "version": "^1.0.0"}],
    )
    _prepend_import_marker(provider, provider_marker)
    _prepend_import_marker(consumer, consumer_marker)

    manager = PluginManager((tmp_path,), 1.0, 1.0)
    manager.discover()
    with pytest.raises(PluginDependencyError, match="version mismatch"):
        manager.validate()
    assert not provider_marker.exists()
    assert not consumer_marker.exists()


async def test_failed_entrypoint_is_isolated_and_leaves_no_dynamic_modules(
    tmp_path: Path,
) -> None:
    plugin_dir = scaffold_plugin("broken_import", tmp_path)
    healthy_dir = scaffold_plugin("healthy_plugin", tmp_path)
    dependent_dir = scaffold_plugin("blocked_dependent", tmp_path)
    marker = tmp_path / "dependent-imported.marker"
    (plugin_dir / "plugin.py").write_text(
        'raise RuntimeError("expected import failure")\n',
        encoding="utf-8",
    )
    _update_manifest(
        dependent_dir,
        dependencies=[{"id": "broken_import", "version": "^0.1.0"}],
    )
    _prepend_import_marker(dependent_dir, marker)

    manager = PluginManager((tmp_path,), 1.0, 1.0)
    manager.discover()
    manager.validate()
    assert not any(name.startswith("_reliaforge_plugin_broken_import_") for name in sys.modules)
    assert not marker.exists()
    assert manager.get_view("broken_import").health.details == {"reason": "load_error"}
    assert manager.get_view("broken_import").available_actions == []
    assert manager.get_view("blocked_dependent").health.details == {
        "reason": "dependency_unavailable"
    }
    assert manager.get_view("blocked_dependent").available_actions == []
    assert manager.get_view("broken_import").settings_schema == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    await manager.start_all()
    assert manager.get_view(healthy_dir.name).state == "running"
    with pytest.raises(PluginOperationError, match="plugin is unavailable"):
        await manager.start_plugin("broken_import")


def test_constructor_failure_is_wrapped_and_isolated_as_load_error(tmp_path: Path) -> None:
    plugin_dir = scaffold_plugin("broken_constructor", tmp_path)
    source_path = plugin_dir / "plugin.py"
    source = source_path.read_text(encoding="utf-8")
    source = source.replace(
        "        super().__init__(manifest)",
        '        raise RuntimeError("constructor fixture")',
        1,
    )
    source_path.write_text(source, encoding="utf-8")

    manager = PluginManager((tmp_path,), 1.0, 1.0)
    manager.discover()
    manager.validate()
    assert manager.get_view("broken_constructor").health.details == {"reason": "load_error"}
    assert not any(
        name.startswith("_reliaforge_plugin_broken_constructor_") for name in sys.modules
    )


def test_invalid_entrypoint_class_is_isolated_as_load_error(tmp_path: Path) -> None:
    plugin_dir = scaffold_plugin("invalid_entrypoint", tmp_path)
    (plugin_dir / "plugin.py").write_text("class Plugin:\n    pass\n", encoding="utf-8")

    manager = PluginManager((tmp_path,), 1.0, 1.0)
    manager.discover()
    manager.validate()

    assert manager.get_view("invalid_entrypoint").health.details == {"reason": "load_error"}
    assert not any(
        name.startswith("_reliaforge_plugin_invalid_entrypoint_") for name in sys.modules
    )


@pytest.mark.parametrize(
    "reserved_path",
    ["/start", "/stop/", "/restart", "/{action}", "/{path:path}"],
)
def test_reserved_lifecycle_routes_are_isolated(
    tmp_path: Path,
    reserved_path: str,
) -> None:
    plugin_dir = scaffold_plugin("reserved_route", tmp_path)
    router_path = plugin_dir / "router.py"
    source = router_path.read_text(encoding="utf-8")
    router_path.write_text(
        source.replace('@router.get("/message"', f'@router.get("{reserved_path}"'),
        encoding="utf-8",
    )

    manager = PluginManager((tmp_path,), 1.0, 1.0)
    manager.discover()
    manager.validate()

    assert manager.get_view("reserved_route").health.details == {"reason": "reserved_route"}
    assert manager.routers() == ()
    assert not any(name.startswith("_reliaforge_plugin_reserved_route_") for name in sys.modules)


def test_nested_lifecycle_route_name_remains_available(tmp_path: Path) -> None:
    plugin_dir = scaffold_plugin("nested_route", tmp_path)
    router_path = plugin_dir / "router.py"
    source = router_path.read_text(encoding="utf-8")
    router_path.write_text(
        source.replace('@router.get("/message"', '@router.get("/admin/{action}"'),
        encoding="utf-8",
    )

    manager = PluginManager((tmp_path,), 1.0, 1.0)
    manager.discover()
    manager.validate()

    assert manager.get_view("nested_route").state == "validated"
    assert [plugin_id for plugin_id, _ in manager.routers()] == ["nested_route"]


def test_reserved_mount_is_isolated(tmp_path: Path) -> None:
    plugin_dir = scaffold_plugin("reserved_mount", tmp_path)
    router_path = plugin_dir / "router.py"
    source = router_path.read_text(encoding="utf-8")
    source = source.replace(
        "from fastapi import APIRouter, HTTPException, status",
        "from fastapi import APIRouter, HTTPException, status\n"
        "from starlette.applications import Starlette\n"
        "from starlette.routing import Mount",
    )
    router_path.write_text(
        source.replace(
            "    return router",
            '    router.routes.append(Mount("/start", app=Starlette()))\n    return router',
        ),
        encoding="utf-8",
    )

    manager = PluginManager((tmp_path,), 1.0, 1.0)
    manager.discover()
    manager.validate()

    assert manager.get_view("reserved_mount").health.details == {"reason": "reserved_route"}
    assert manager.routers() == ()


async def test_capabilities_reject_undeclared_and_missing_services(tmp_path: Path) -> None:
    undeclared = scaffold_plugin("undeclared_service", tmp_path)
    _update_manifest(undeclared, capabilities=[])

    missing = scaffold_plugin("missing_service", tmp_path)
    _update_manifest(
        missing,
        capabilities=["missing_service.message", "missing_service.extra"],
    )

    manager = PluginManager((tmp_path,), 1.0, 1.0)
    manager.discover()
    manager.validate()
    await manager.start_all()

    undeclared_view = manager.get_view("undeclared_service")
    missing_view = manager.get_view("missing_service")
    assert undeclared_view.state == "error"
    assert undeclared_view.health.details == {"reason": "UndeclaredCapabilityError"}
    assert missing_view.state == "error"
    assert missing_view.health.details == {"reason": "capability_contract"}


def test_bundled_plugins_keep_internal_imports_in_dynamic_package_namespace() -> None:
    """Self-imports must remain removable by the loader's package cleanup."""

    plugins_root = Path(__file__).parents[1] / "reliaforge" / "plugins"
    for plugin_id in ("demo", "runbook"):
        for source_path in (plugins_root / plugin_id).glob("*.py"):
            source = source_path.read_text(encoding="utf-8")
            assert f"reliaforge.plugins.{plugin_id}" not in source, source_path


@pytest.mark.parametrize("declared", [False, True])
async def test_service_consumption_requires_a_declared_provider(
    tmp_path: Path, declared: bool
) -> None:
    import reliaforge.plugins

    root = Path(reliaforge.plugins.__file__).parent
    for plugin_id in ("demo", "runbook"):
        shutil.copytree(
            root / plugin_id, tmp_path / plugin_id, ignore=shutil.ignore_patterns("__pycache__")
        )
    if not declared:
        _update_manifest(tmp_path / "runbook", dependencies=[])
    manager = PluginManager((tmp_path,), 1.0, 0.1)
    manager.discover()
    manager.validate()
    try:
        await manager.start_all()
        consumer = manager.get_view("runbook")
        if declared:
            assert consumer.state == "running"
            assert manager.get_view("demo").available_actions == []
        else:
            assert consumer.state == "error"
            assert consumer.health.details == {"reason": "UndeclaredDependencyError"}
            assert (await manager.stop_plugin("demo")).state == "stopped"
    finally:
        await manager.stop_all()
