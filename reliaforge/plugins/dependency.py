"""Deterministic plugin dependency validation and topological ordering."""

from __future__ import annotations

import heapq
from collections import defaultdict
from collections.abc import Iterable

from reliaforge.plugins.contract import PluginManifest


class PluginDependencyError(ValueError):
    """Raised for invalid, missing, cyclic, or version-incompatible dependencies."""


class DependencyResolver:
    """Resolve manifests with a deterministic Kahn topological sort."""

    def resolve(self, manifests: Iterable[PluginManifest]) -> tuple[str, ...]:
        """Validate dependencies and return dependency-first plugin IDs."""

        by_id = {manifest.id: manifest for manifest in manifests}
        graph: dict[str, list[str]] = defaultdict(list)
        indegree = {plugin_id: 0 for plugin_id in by_id}

        for plugin_id, manifest in by_id.items():
            for dependency in manifest.dependencies:
                dependency_id = dependency.id
                if dependency_id == plugin_id:
                    raise PluginDependencyError(f"plugin depends on itself: {plugin_id}")
                if dependency_id not in by_id:
                    raise PluginDependencyError(
                        f"missing dependency for {plugin_id}: {dependency_id}"
                    )
                provider = by_id[dependency_id]
                if not dependency.accepts(provider.version):
                    raise PluginDependencyError(
                        "dependency version mismatch for "
                        f"{plugin_id}: {dependency_id} {dependency.version} "
                        f"does not accept {provider.version}"
                    )
                graph[dependency_id].append(plugin_id)
                indegree[plugin_id] += 1

        queue = [plugin_id for plugin_id, count in indegree.items() if count == 0]
        heapq.heapify(queue)
        result: list[str] = []
        while queue:
            current = heapq.heappop(queue)
            result.append(current)
            for dependent in sorted(graph[current]):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    heapq.heappush(queue, dependent)

        if len(result) != len(by_id):
            cyclic = sorted(plugin_id for plugin_id, count in indegree.items() if count > 0)
            raise PluginDependencyError(f"dependency cycle detected: {', '.join(cyclic)}")
        return tuple(result)
