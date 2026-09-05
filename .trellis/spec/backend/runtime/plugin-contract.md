# Plugin contract

## Product boundary

ReliaForge is a plugin-based operations platform. A plugin provides a developer-owned Python
service; a runbook is one possible service. Platform code owns loading, configuration, dependencies,
management authentication, and lifecycle. Do not turn plugin-specific workflows into mandatory
platform abstractions.

## Current architecture

`reliaforge/plugins/loader.py` reads and validates every manifest before importing entry points.
`reliaforge/plugins/dependency.py` validates the complete dependency graph. The manager in
`reliaforge/plugins/manager.py` owns instances, lifecycle transitions, settings construction,
capability registration, cleanup, health snapshots, and available actions.

The bundled `reliaforge/plugins/demo/` and `reliaforge/plugins/runbook/` packages demonstrate the
preferred package shape. `templates/plugin/` is the source for `reliaforge-scaffold` and must remain
consistent with the contract.

## Manifest and import rules

- Declare identity, SemVer, `api_version`, entry point, dependencies, capabilities, and optional
  frontend category in `manifest.json`.
- Plugin IDs use lowercase snake case. Capabilities use unique dotted public names.
- Dependencies are `{ "id": string, "version": semver-range }` objects.
- Do not place settings schema, lifecycle actions, arbitrary routes, or service implementation
  versions in the manifest.
- Validate the complete manifest set before importing any plugin module. A failed branch must not
  hide independent valid plugins.

Reference tests: `tests/test_manifest.py`, `tests/test_dependency.py`, and
`tests/test_loader_contract.py`.

## Lifecycle and ownership

- Extend the platform base plugin and keep lifecycle hooks async and cancellation-aware.
- Preserve the context after failed initialization until the manager has attempted stop. Stop hooks
  must tolerate partial initialization. Cancellation cleanup shares the remaining operation budget,
  preserves caller cancellation, and always removes the plugin's registrations after the stop attempt.
- Lifecycle state and health are separate. `degraded` is health, never lifecycle state.
- Health is a synchronous, side-effect-free in-memory snapshot. It does not probe or repair external
  dependencies.
- Blocking I/O requires a bounded execution domain and explicit timeout.
- Plugins are trusted in-process extensions, not a hostile-code sandbox.

Reference tests: `tests/test_lifecycle.py`, `tests/test_events.py`, and `tests/test_logging.py`.

## Services and events

- Register only capabilities declared by the provider manifest.
- Consumers declare the provider in their manifest dependencies, then resolve its capabilities
  through caller-owned `@runtime_checkable Protocol` types. Context lookup must enforce this graph.
- Do not import another plugin's implementation package.
- Event delivery is concurrent, deadline-bounded, process-local, and failure-isolating. It is not a
  durable queue or diagnostic store.

Reference source: `reliaforge/services.py`, `reliaforge/events.py`, and
`reliaforge/plugins/context.py`.

## Settings

- Declare fields once in a `PluginSettings` subclass and assign it through `settings_class`.
- Let the manager own `RELIAFORGE_<PLUGIN_ID>_` and the `__` nested delimiter.
- Use `SecretStr` for secret inputs; never provide secret defaults or include values in schemas,
  errors, events, or logs.
- Restart reconstructs settings on the loaded plugin. It does not reload Python source or manifests.

Reference source and tests: `reliaforge/plugins/settings.py`, bundled `settings.py` files, and
`tests/test_settings_contract.py`.

## Avoid

- Importing extension code during manifest discovery.
- Direct cross-plugin implementation imports.
- Handwritten settings schema or client-owned lifecycle rules.
- Unbounded background work, silent exception swallowing, or cleanup that mutates another owner.
- Adding compatibility shims for unpublished private plugin formats.
