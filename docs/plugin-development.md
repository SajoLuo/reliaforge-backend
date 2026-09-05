# Plugin development

[简体中文](zh/plugin-development.md)

This tutorial turns a Python team lookup function into an API. You will generate a plugin, add a
function, expose it through HTTP, and test it while the plugin is running and stopped.

Start in a backend checkout with its Python environment activated. Follow the
[quick start](../README.md#quick-start) if the backend is not installed yet.

## 1. Generate the plugin

Stop any backend running in this checkout with Ctrl+C, then run:

```bash
reliaforge-scaffold sample_tool --destination ./local-plugins
```

If you already generated `sample_tool` in the quick start, use that directory. The command refuses
to overwrite it. The files below are relative to `local-plugins/sample_tool/`.

## 2. Add your function

Create `ownership.py` with this content:

```python
"""Example service ownership records for the plugin tutorial."""

OWNERS = {
    "payments": "payments-ops",
    "search": "search-ops",
}


def find_owner(service_name: str) -> str | None:
    return OWNERS.get(service_name)
```

The two records are example data. This function takes a service name and returns its owning team,
or `None` when the service is unknown. Keep your tool's own code in a module like this so it can be
used without FastAPI.

## 3. Give it an API

Replace `router.py` with the following file. It keeps the generated `/message` endpoint and adds
`/owner`. The new endpoint reads `service_name`, calls `find_owner`, and returns a JSON object.

```python
"""Thin HTTP routes for Sample Tool."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict

from reliaforge.plugins.contract import PluginState

from .models import Message
from .ownership import find_owner
from .service import MessageUnavailableError

if TYPE_CHECKING:
    from .plugin import Plugin


class ServiceOwner(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: str
    team: str


def create_router(plugin: Plugin) -> APIRouter:
    router = APIRouter(tags=["sample_tool"])

    @router.get("/message", response_model=Message)
    async def message() -> Message:
        try:
            return plugin.get_message()
        except MessageUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Plugin is not running",
            ) from exc
        except HTTPException:
            raise
        except Exception as exc:
            plugin.logger.error("generated plugin request failed (%s)", type(exc).__name__)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error",
            ) from exc

    @router.get("/owner", response_model=ServiceOwner)
    async def owner(
        service_name: Annotated[str, Query(min_length=1, max_length=64)],
    ) -> ServiceOwner:
        if plugin.state is not PluginState.RUNNING:
            raise HTTPException(status_code=503, detail="Plugin is not running")
        team = find_owner(service_name)
        if team is None:
            raise HTTPException(status_code=404, detail="Service not found")
        return ServiceOwner(service=service_name, team=team)

    return router
```

The lookup is only allowed while the plugin is running. The state check returns `503` after a stop;
an unknown service returns `404`. FastAPI validates the required query parameter and documents
the response using `ServiceOwner`.

This example only reads a dictionary. For a function that waits on a network or database, use
asynchronous I/O or a worker with a concurrency limit and a timeout; see [Lifecycle and health](#lifecycle-and-health).

## 4. Load it and try the API

From the backend directory, start the process with the plugin's parent directory:

```bash
RELIAFORGE_PLUGIN_PATHS=./local-plugins reliaforge
```

In PowerShell, use:

```powershell
$env:RELIAFORGE_PLUGIN_PATHS = "./local-plugins"
reliaforge
```

In another terminal, call:

```bash
curl "http://127.0.0.1:8000/api/v1/plugins/sample_tool/owner?service_name=payments"
```

Expected response:

```json
{"service": "payments", "team": "payments-ops"}
```

In local development, open `http://127.0.0.1:8000/api/v1/docs` to browse and try the endpoint.
The console's plugin list should show `sample_tool` as running.

Check failures and start and stop behavior as well:

```bash
curl -i "http://127.0.0.1:8000/api/v1/plugins/sample_tool/owner?service_name=unknown"
curl -i "http://127.0.0.1:8000/api/v1/plugins/sample_tool/owner"
curl -X POST http://127.0.0.1:8000/api/v1/plugins/sample_tool/stop
curl -i "http://127.0.0.1:8000/api/v1/plugins/sample_tool/owner?service_name=payments"
curl -X POST http://127.0.0.1:8000/api/v1/plugins/sample_tool/start
curl "http://127.0.0.1:8000/api/v1/plugins/sample_tool/owner?service_name=payments"
```

The unknown service returns `404`; the missing parameter returns `422`. Stopping the plugin returns
its `stopped` state, and a lookup then returns `503`. Starting it again returns `running`, and the
last lookup succeeds with `200` and the same team as before.

Run the generated lifecycle test from the plugin directory:

```bash
python -m pytest tests/test_plugin.py
```

## 5. Give your team the plugin and its usage instructions

Give the deployment maintainer the `sample_tool` directory and any Python dependency requirements.
The maintainer installs those requirements, adds the directory's parent to `RELIAFORGE_PLUGIN_PATHS`,
and restarts the backend. Code changes also require a backend restart; the console's plugin restart
button continues to use already loaded code.

Update the plugin's README with its URL, required `service_name` parameter, response fields, and
the `404`, `422`, and `503` cases above. In production, users must authenticate through the deployment's
proxy before calling the API. See [production authentication](development.md#configure-production-authentication)
when setting this up.

The remaining sections describe the fields and runtime rules you need when extending the plugin.

## Manifest

The manifest describes what the platform should load. The supported fields are:

- `id`, `name`, `version`, `description`, and `api_version`;
- `entrypoint` in `module:Class` form, relative to the plugin directory;
- `dependencies`, with a plugin `id` and accepted SemVer `version` range;
- `capabilities`, unique dotted names for Python services shared with other plugins;
- optional `frontend.category`, used to group plugins in the console.

Plugin IDs use lowercase snake case. Set `api_version` to `"v1"`. A dependency looks like this:

```json
{
  "dependencies": [
    { "id": "metrics_provider", "version": "^1.2.0" }
  ]
}
```

ReliaForge checks the complete set of manifests before importing plugin code. A missing dependency,
version mismatch, cycle, duplicate ID, or duplicate capability name stops backend startup before any
plugin code is imported.

## Lifecycle and health

The backend discovers and validates plugins, then calls `_on_initialize()` and `_on_start()`.
It reads `_on_health_check()` when reporting the health of a running plugin, and calls `_on_stop()`
to release resources. Health checks can run repeatedly between startup and shutdown.

Startup and stop hooks are asynchronous and must respond to cancellation. Use asynchronous clients
for network and database calls where possible. Run synchronous I/O in worker threads, limit how
many calls can run at once, and set a timeout on the I/O itself. Cancelling the waiting coroutine
does not stop a thread that is already running.

Health checks report information already held in memory. Keep them fast and synchronous; do not
make network, database, filesystem, or command calls from `_on_health_check()`.

During initialization, register every service listed in `capabilities`. Use an empty list when the
plugin does not share Python objects with other plugins. HTTP endpoints do not need a capability.

The manager calls `_on_stop()` after failed or cancelled initialization, within the operation's
remaining time budget. That hook must handle partially created resources: check whether a client
or task exists before releasing it, and use `finally` for local cleanup. After the stop attempt,
the platform removes service registrations and event subscriptions. A timeout cannot force
uncooperative Python code to release resources.

When calling `BasePlugin.initialize()` directly in a test, always call `stop()` in `finally`, even
if initialization returned `False`. The context remains attached until the stop attempt so that
the hook can release partially initialized resources.

`context.publish(...)` sends an in-process event to current subscribers. Handlers run concurrently
with a timeout, and one failed handler does not fail the publisher. Events are not persisted, so do
not use them as a job queue.

## Routes and shared services

ReliaForge mounts each router below `/api/v1/plugins/{plugin_id}`. Keep business logic in the
service and HTTP validation in the router. The root-relative `/start`, `/stop`, and `/restart`
paths are reserved for plugin lifecycle operations.

Cross-origin development requests support `GET` and `POST`. Deploy the frontend and backend on the
same origin when a plugin route needs another HTTP method.

To use another plugin's shared Python service, first declare its provider in `dependencies`. Then
define the interface you need and ask the context for the named service. The platform rejects a
lookup whose provider is not a declared dependency:

```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class GreetingCapability(Protocol):
    def message(self) -> str: ...


greeting = context.get_service("demo.greeting", GreetingCapability)
```

## Load and call your service

Point `RELIAFORGE_PLUGIN_PATHS` at the parent directory containing the generated plugin and restart
the backend. The default scaffold exposes `GET /api/v1/plugins/sample_tool/message`. A successful
request returns the message defined by the example service.

Give the plugin's users a README listing its endpoints, parameters, responses, settings, and
authentication requirements. The console lists the loaded plugin and manages its lifecycle.
Changing code or the manifest requires a backend restart; the plugin restart action reuses the
loaded code.

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
