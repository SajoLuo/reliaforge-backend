# Architecture

[简体中文](zh/architecture.md)

The FastAPI application exposes the management API and plugin-owned routes. One plugin manager
loads plugins and controls their state.

```text
FastAPI application
  -> management API
  -> plugin manager
       -> reads and validates manifests
       -> orders dependencies
       -> imports plugins
       -> initializes, starts, checks, and stops plugins
       -> records status, health, and safe errors
  -> plugin API routes -> plugin services
```

## Discovery and dependency checks

The manager reads all `manifest.json` files before importing Python code. It checks duplicate IDs,
API versions, missing or incompatible dependencies, cycles, and duplicate capability names. Any
validation error stops backend startup. After the complete graph passes, plugins are imported in
dependency order.

An import or constructor failure becomes a `load_error` record without the original exception text.
Plugins that depend on it become `dependency_unavailable`. Unrelated plugins and the management API
remain available. A failed import is removed from its temporary module namespace before another load.

## Plugin context and shared services

Each plugin receives its own `PluginContext`. The context records which services and event
subscriptions the plugin created, so cleanup removes only that plugin's resources.

A plugin lists each shared service in `capabilities`, then registers it during initialization.
Consumers request the service by name and validate it against their own runtime-checkable Python
`Protocol`. Startup fails when a declared service is missing or a plugin registers an undeclared
service.

## Settings

Each plugin can provide one `PluginSettings` subclass. The manager reads variables with the
`RELIAFORGE_<PLUGIN_ID>_` prefix, creates one validated instance, and places it in the plugin
context. The same class generates the public configuration schema. Secret values are not included
in API responses or lifecycle errors.

## State, health, and actions

Lifecycle state records whether a plugin is discovered, validated, initialized, running, stopped,
or in error. Health separately records healthy, degraded, error, or stopped.

`/live`, `/ready`, and `/status` return in-memory state. They do not contact external systems or
repair anything. Initialization, startup, shutdown, and each event handler have time limits.

Each plugin response includes `available_actions`. The manager calculates it from the current
instance, state, dependencies, and running dependents. The API authenticates and rechecks every
requested action.

## Events and shutdown

The event bus calls current subscribers concurrently. A handler error or timeout appears in the
delivery report without failing other handlers. Events stay in memory and are not a durable queue.

When a plugin stops, the manager removes its services and subscriptions even if the stop hook fails.
Lifecycle timeouts include time waiting for the manager lock. During process shutdown, ReliaForge
does not bypass that lock or mutate a plugin operation already in progress.

Plugins run as trusted code inside the backend process. They are not isolated from the process or
from one another by a security sandbox.
