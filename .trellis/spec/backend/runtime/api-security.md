# API and security

## Layer ownership

`reliaforge/api/models.py` defines the stable management response models.
`reliaforge/api/router.py` translates manager behavior into HTTP. Plugin routers remain thin and
delegate domain behavior to their service modules. `reliaforge/auth.py` owns management
authentication; manifests cannot override it.

## Route rules

- Keep public read-only probes, status, catalog, and detail free of repair writes or dependency
  probes.
- Mount plugin-owned routes and lifecycle writes behind the same management authentication
  dependency.
- Reserve plugin-root `/start`, `/stop`, and `/restart` paths for the platform manager.
- Use Pydantic v2 models with `extra="forbid"` for stable public response shapes.
- Return secret-safe stable errors. Do not expose raw import, validation, configuration, or plugin
  exception text.
- Keep domain behavior out of FastAPI routers and `HTTPException` out of services.

Reference source and tests: `reliaforge/app.py`, `reliaforge/api/`, bundled plugin routers/services,
`tests/test_api.py`, and `tests/test_config_auth.py`.

## Lifecycle actions

`PluginView.available_actions` is computed by `PluginManager` from the loaded instance, lifecycle
state, running dependencies, and active dependents. Neither plugins nor clients declare it. Every
write is still authenticated and revalidated; the list is an affordance, not authorization.

Any API model change that affects `PluginView`, `PluginListResponse`, or `PlatformStatusResponse`
must update the frontend types, runtime parsers, contract checker, and cross-repository smoke in the
same reviewed change.

## Environment boundaries

- Anonymous management is valid only for explicit development/test environments on loopback.
- Production proxy mode requires a trusted direct peer, operator identity header, and strong shared
  secret. Invalid configuration prevents startup.
- Reject wildcard CORS origins and all-address trusted networks.
- Preserve direct-peer validation by disabling forwarded-address rewriting in the packaged command.
- Do not expose interactive API documentation or OpenAPI in production.

Reference source and tests: `reliaforge/config.py`, `reliaforge/auth.py`, `reliaforge/cli.py`,
`tests/test_config_auth.py`, and `tests/test_cli.py`.

## Avoid

- Client-side management secrets or manifest-level auth opt-outs.
- Treating `available_actions` as permission.
- Broad CORS or trusted-network defaults.
- Adding external I/O to liveness, readiness, status, catalog, or detail reads.
