"""Manifest-first plugin discovery with isolated dynamic packages."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from reliaforge.plugins.contract import BasePlugin, PluginManifest


class PluginLoadError(RuntimeError):
    """Raised when a manifest or declared entry point cannot be loaded."""


@dataclass(frozen=True)
class PluginCandidate:
    """A validated manifest whose code has not been imported yet."""

    manifest: PluginManifest
    source_dir: Path


class PluginLoader:
    """Discover plugin directories without importing unmanifested files."""

    def discover_root(self, root: Path) -> tuple[PluginCandidate, ...]:
        """Read manifest-bearing direct children without importing plugin code."""

        if not root.exists():
            raise PluginLoadError(f"plugin path does not exist: {root}")
        if not root.is_dir():
            raise PluginLoadError(f"plugin path is not a directory: {root}")

        discovered: list[PluginCandidate] = []
        for child in sorted(path for path in root.iterdir() if path.is_dir()):
            manifest_path = child / "manifest.json"
            if manifest_path.is_file():
                discovered.append(self._read_candidate(child, manifest_path))
        return tuple(discovered)

    def load(self, candidate: PluginCandidate) -> BasePlugin:
        """Import one candidate only after the manager validates the full manifest set."""

        package_name = self._package_name(candidate.source_dir, candidate.manifest)
        self._remove_package_modules(package_name)
        instance = self._load_entrypoint(candidate.source_dir, candidate.manifest, package_name)
        if instance.manifest != candidate.manifest:
            self._remove_package_modules(package_name)
            raise PluginLoadError(
                f"entry point changed its validated manifest: {candidate.manifest.id}"
            )
        return instance

    def unload(self, candidate: PluginCandidate) -> None:
        """Remove one candidate's isolated module namespace."""

        self._remove_package_modules(self._package_name(candidate.source_dir, candidate.manifest))

    def _read_candidate(self, plugin_dir: Path, manifest_path: Path) -> PluginCandidate:
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            manifest = PluginManifest.model_validate(raw)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise PluginLoadError(
                f"invalid manifest at {manifest_path}: {type(exc).__name__}"
            ) from None

        if manifest.id != plugin_dir.name:
            raise PluginLoadError(f"manifest id must match directory name: {plugin_dir.name}")
        return PluginCandidate(manifest, plugin_dir)

    def _load_entrypoint(
        self,
        plugin_dir: Path,
        manifest: PluginManifest,
        package_name: str,
    ) -> BasePlugin:
        init_path = plugin_dir / "__init__.py"
        if not init_path.is_file():
            raise PluginLoadError(f"plugin package is missing __init__.py: {manifest.id}")

        module_name, class_name = manifest.entrypoint.split(":", maxsplit=1)
        module_path = plugin_dir.joinpath(*module_name.split(".")).with_suffix(".py")
        if not module_path.is_file():
            raise PluginLoadError(f"entry point module is missing: {manifest.id}")

        package_spec = importlib.util.spec_from_file_location(
            package_name,
            init_path,
            submodule_search_locations=[str(plugin_dir)],
        )
        if package_spec is None or package_spec.loader is None:
            raise PluginLoadError(f"cannot create package spec: {manifest.id}")

        package = importlib.util.module_from_spec(package_spec)
        sys.modules[package_name] = package
        try:
            package_spec.loader.exec_module(package)
            qualified_module = f"{package_name}.{module_name}"
            module_spec = importlib.util.spec_from_file_location(qualified_module, module_path)
            if module_spec is None or module_spec.loader is None:
                raise PluginLoadError(f"cannot create module spec: {manifest.id}")
            module = importlib.util.module_from_spec(module_spec)
            sys.modules[qualified_module] = module
            module_spec.loader.exec_module(module)
            plugin_class = getattr(module, class_name)
            if not isinstance(plugin_class, type) or not issubclass(plugin_class, BasePlugin):
                raise PluginLoadError(f"entry point must extend BasePlugin: {manifest.id}")
            return plugin_class(manifest)
        except PluginLoadError:
            self._remove_package_modules(package_name)
            raise
        except Exception as exc:
            self._remove_package_modules(package_name)
            raise PluginLoadError(
                f"entry point import failed for {manifest.id}: {type(exc).__name__}"
            ) from None
        except BaseException:
            self._remove_package_modules(package_name)
            raise

    @staticmethod
    def _package_name(plugin_dir: Path, manifest: PluginManifest) -> str:
        digest = hashlib.sha256(str(plugin_dir.resolve()).encode()).hexdigest()[:12]
        return f"_reliaforge_plugin_{manifest.id}_{digest}"

    @staticmethod
    def _remove_package_modules(package_name: str) -> None:
        prefix = f"{package_name}."
        for module_name in tuple(sys.modules):
            if module_name == package_name or module_name.startswith(prefix):
                sys.modules.pop(module_name, None)
