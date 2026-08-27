# Plugin development

[简体中文](zh/plugin-development.md)

Each plugin directory contains `manifest.json`, `__init__.py`, an entry-point module, a service,
models, settings, and a thin router. Use `reliaforge-scaffold` to create the initial files.

## Manifest

The public manifest fields are:

- `id`, `name`, `version`, `description`, and `api_version`.
- `entrypoint`, in `module:Class` form relative to the plugin directory.
- `dependencies`, a list of objects containing a plugin `id` and accepted SemVer `version` range.
- `capabilities`, a list of unique dotted public service names.
- `frontend`, optional category metadata for the generic catalog.

`settings_schema`, frontend `route`/`icon`, and service registration versions are intentionally not
manifest fields. The UI derives `/plugins/{plugin_id}`, settings schema comes from Python, and the
provider plugin SemVer dependency is the compatibility boundary.

Plugin IDs use lowercase snake case. ReliaForge 0.1 accepts `api_version: "v1"`. Dependencies
use the new public object form; old string-only dependency declarations are intentionally rejected:

```json
{
  "dependencies": [
    { "id": "metrics_provider", "version": "^1.2.0" }
  ]
}
```

Dependency resolution is deterministic and rejects missing plugins, incompatible versions, or
cycles. The complete manifest set is validated before any entry point is imported.

## Lifecycle

The manager drives this sequence:

```text
discover -> validate -> initialize -> start -> health -> stop
```

Initialization registers local services through `PluginContext`; start makes them available;
stop releases resources. Lifecycle hooks are async and must honor cancellation. Lifecycle state
uses `running`; degraded runtime quality is represented only by `HealthStatus.DEGRADED`. Synchronous I/O
must be moved to a bounded execution domain with an explicit timeout. Health is a synchronous,
side-effect-free snapshot.

`context.publish(...)` returns an `EventDeliveryReport`. Subscribers run concurrently under the
platform handler timeout. One subscriber's exception or timeout is reported with the stable
`handler_error` or `handler_timeout` reason and does not fail the publisher; cancellation of the
publisher itself still propagates. Event delivery is process-local and non-durable; each report
describes only its publish call, so do not use the bus as a workflow queue. Context-owned
subscriptions and services are always removed when stop finishes or fails.

Every service registered through `context.register_service(...)` must appear in the provider's
manifest capabilities. Initialization also fails when a declared capability is not registered,
or when two manifests claim the same capability.

## Routes and services

The platform mounts a plugin router under `/api/v1/plugins/{plugin_id}`. Routers validate and
translate HTTP errors only. Domain behavior stays in services, which do not import FastAPI.
The platform reserves the root-relative `/start`, `/stop`, and `/restart` paths for lifecycle
operations. Validation isolates a plugin with the stable `reserved_route` reason when its router
can match one of those paths, whether by a literal, dynamic parameter, catch-all, or trailing
slash. Nested paths such as `/admin/start` remain available to plugin code.

Development CORS intentionally permits only `GET` and `POST`; use same-origin deployment for
plugins that need other HTTP methods rather than assuming a broader cross-origin contract.

Plugins request another plugin's public capability with a caller-owned runtime Protocol; direct
imports of another plugin package are unsupported:

```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class GreetingCapability(Protocol):
    def message(self) -> str: ...


greeting = context.get_service("demo.greeting", GreetingCapability)
```

## Settings

Declare fields once in a subclass of the platform base and point the plugin class at it:

```python
from pydantic import Field
from reliaforge.plugins.settings import PluginSettings


class SampleSettings(PluginSettings):
    message: str = Field(default="Ready", min_length=1, max_length=200)


class Plugin(BasePlugin):
    settings_class = SampleSettings

    async def _on_initialize(self) -> None:
        settings = self.context.get_settings(SampleSettings)
```

The manager owns the `RELIAFORGE_<PLUGIN_ID>_` prefix and `__` nested delimiter. It creates one
instance before the initialize hook, derives the public schema, and recreates settings on restart.
Use `SecretStr` for secrets and inject them through process environment or deployment secret
storage. Do not provide secret defaults or log validation exception text.

The platform mounts all plugin routes behind management authentication. Catalog, detail, `/live`,
`/ready`, and `/status` remain public and read-only. There is no manifest opt-out for anonymous
plugin routes.

Catalog and detail responses include `available_actions` with `start`, `stop`, and `restart`
values. The manager derives the list from runtime state and dependency protection; plugin code and
clients do not declare it. Treat the field as a UI affordance, not authorization: every lifecycle
request is still authenticated and revalidated by the backend.

The management `restart` operation runs stop, initialize, and start against the loaded plugin. It
does not reload Python source or the manifest from disk.

The built-in runbook example demonstrates `demo ^1.0.0`, typed capability lookup, deterministic
preview data, reverse shutdown order, and provider lifecycle protection without executing commands
or performing network, database, or filesystem I/O.
