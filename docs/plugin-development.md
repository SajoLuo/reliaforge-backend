# Plugin development

[简体中文](zh/plugin-development.md)

Generate a plugin first, then replace the example service with your operations task:

```bash
reliaforge-scaffold sample_tool --destination ./local-plugins
```

## Files in a plugin

- `manifest.json` describes the plugin.
- The plugin class handles initialize, start, health, and stop.
- The settings class reads environment variables.
- The service contains the operations task and does not import FastAPI.
- The router validates HTTP input and calls the service.
- Tests cover the plugin's API, state changes, health, and cleanup.

## Manifest

The supported fields are:

- `id`, `name`, `version`, `description`, and `api_version`;
- `entrypoint` in `module:Class` form, relative to the plugin directory;
- `dependencies`, with a plugin `id` and accepted SemVer `version` range;
- `capabilities`, unique dotted names for services the plugin provides;
- optional `frontend.category`, used to group plugins in the console.

Plugin IDs use lowercase snake case. Set `api_version` to `"v1"`. A dependency looks like this:

```json
{
  "dependencies": [
    { "id": "metrics_provider", "version": "^1.2.0" }
  ]
}
```

ReliaForge checks the complete set of manifests before importing plugin code. Missing dependencies,
version mismatches, cycles, duplicate IDs, and duplicate capability names stop the affected plugins
from loading.

## Lifecycle and health

The plugin manager calls hooks in this order:

```text
discover -> validate -> initialize -> start -> health -> stop
```

Lifecycle hooks are asynchronous and must respond to cancellation. Move synchronous I/O to a
bounded worker and set a timeout. Health is a fast, synchronous snapshot and must not make network,
database, filesystem, or command calls.

During initialization, register every service listed in `capabilities`. ReliaForge removes a
plugin's services and event subscriptions when the plugin stops, including after a failed stop.

`context.publish(...)` sends an in-process event to current subscribers. Handlers run concurrently
with a timeout, and one failed handler does not fail the publisher. Events are not persisted, so do
not use them as a job queue.

## Routes and shared services

ReliaForge mounts each router below `/api/v1/plugins/{plugin_id}`. Keep business logic in the
service and HTTP validation in the router. The root-relative `/start`, `/stop`, and `/restart`
paths are reserved for plugin lifecycle operations.

To use another plugin's service, define the interface you need and ask the context for the named
capability:

```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class GreetingCapability(Protocol):
    def message(self) -> str: ...


greeting = context.get_service("demo.greeting", GreetingCapability)
```

## Settings

Declare configuration fields in a `PluginSettings` subclass:

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

Environment variables use the `RELIAFORGE_<PLUGIN_ID>_` prefix and `__` for nested fields. Restart
reads settings again for the loaded plugin. Use `SecretStr` for secrets and inject values through
the process environment or deployment secret storage. Never put secrets in defaults, logs, schemas,
or error messages.

Plugin routes and lifecycle operations require management authentication. Catalog and status reads
remain public. The backend includes `available_actions` in each plugin response; clients display
this list, while the backend authenticates and checks every action request.

The bundled `demo` and `runbook` plugins show a provider and consumer using a typed shared service.
