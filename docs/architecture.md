# Architecture

[简体中文](zh/architecture.md)

ReliaForge separates the platform control plane from plugin domain logic.

```text
FastAPI application
  -> management router
  -> plugin manager
       -> manifest loader
       -> dependency resolver
       -> plugin records (candidate / instance / safe error category)
       -> lifecycle state machine
       -> controlled plugin context
            -> service container
            -> failure-isolating event bus
  -> plugin routers -> plugin services
```

Plugin discovery first reads and validates every `manifest.json` without importing plugin code.
The manager rejects duplicate identities, unsupported API versions, missing or version-incompatible dependencies, cycles,
and duplicate capability owners across the complete manifest set. Only then does it import entry
points in dependency order. A failed import, entry-point check, or constructor becomes a
secret-safe `load_error` record; its dependents are not imported and become
`dependency_unavailable`, while independent branches and the management plane continue. Failed
imports clean their isolated module namespace so a later load cannot reuse half-imported modules.

Every plugin receives a provider-scoped context. Service registration records ownership and
cleanup removes only resources owned by that plugin. Plugins never import another plugin's
implementation directly. Consumers resolve capabilities with their own `@runtime_checkable Protocol`;
missing and structurally incompatible services fail with different stable errors.
Manifest capabilities are executable service contracts: a plugin cannot
register an undeclared service, and startup fails if a declared capability was not registered.

Each plugin may declare one `PluginSettings` subclass. The manager constructs it with the canonical
`RELIAFORGE_<PLUGIN_ID>_` prefix, injects it into `PluginContext`, and derives public schema from
`model_json_schema()`. Manifests contain no hand-written settings schema. Secret values are never
included in catalog data or lifecycle error messages.

`/live`, `/ready`, and `/status` read process-local lifecycle and service snapshots. They do not
query external systems or repair state. Initialization and startup execute within configured
deadlines. Plugins are trusted in-process extensions, not a sandbox boundary.

Lifecycle state never uses `degraded`; that value belongs to health. Platform counts classify every
record once as running, degraded, stopped, or error. Plugin-owned routers inherit the same
management authentication dependency as lifecycle actions, while liveness, readiness, status,
catalog, and detail remain public read-only endpoints.

The event bus invokes current subscribers concurrently with a per-handler deadline. Handler
exceptions and timeouts are isolated from publishers and represented by stable, secret-safe
delivery reports; publisher cancellation still propagates. Delivery is process-local and is not a
durable queue or diagnostic store. Plugin stop always releases context-owned services and
subscriptions, including when a stop hook or event delivery fails.

Lifecycle action deadlines include time spent waiting for the manager operation lock. The supported
ASGI server drains request tasks before invoking lifespan shutdown. `stop_all` still counts a
defensive lock wait against the shutdown budget; if that wait expires, it returns without racing the
current lock owner or mutating its plugin context, and process exit remains the final recovery.

Catalog lifecycle affordances are also server-owned. `available_actions` is derived from the
runtime instance, state, running dependencies, and active dependents. A failed load record or a
provider currently protected by a running dependent exposes an empty list, preventing clients from
guessing rules that the manager would reject.
