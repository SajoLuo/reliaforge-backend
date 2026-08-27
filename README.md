# ReliaForge backend

ReliaForge is a lightweight platform for assembling operations tools as isolated,
lifecycle-managed Python plugins. This repository contains the public backend runtime, two
neutral example plugins, and a plugin scaffold. It does not ship monitoring storage, an alerting
suite, or organization-specific integrations.

The optional React management interface lives in
[`reliaforge-frontend`](https://github.com/SajoLuo/reliaforge-frontend).

## What is included

- Typed plugin manifests and API models.
- SemVer dependency validation and deterministic startup ordering.
- Separate lifecycle state and side-effect-free health snapshots.
- A provider-owned service container and deadline-bounded, failure-isolating in-memory event bus.
- Python Settings classes as the only source of plugin fields and public JSON schema.
- Read-only catalog and health APIs plus authorized plugin routes and lifecycle operations.
- A neutral demo at `GET /api/v1/plugins/demo/greeting`.
- A read-only cross-plugin runbook preview at `GET /api/v1/plugins/runbook/preview`.
- A copyable plugin scaffold and deterministic repository hygiene check.

## Quick start

Python 3.11 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
reliaforge
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`. The development command
binds to `127.0.0.1` by default. Open `http://127.0.0.1:8000/api/v1/status`, then request:

```bash
curl http://127.0.0.1:8000/api/v1/plugins
curl http://127.0.0.1:8000/api/v1/plugins/demo/greeting
curl http://127.0.0.1:8000/api/v1/plugins/runbook/preview
```

Copy `.env.example` to an untracked `.env` only when you need local overrides. Never commit
the resulting file. The example explicitly allows the public frontend development origin at
`http://127.0.0.1:5530`; an empty `RELIAFORGE_CORS_ORIGINS` list emits no cross-origin headers.
Wildcard origins are rejected.

## Create a plugin

```bash
reliaforge-scaffold sample_tool --destination ./local-plugins
RELIAFORGE_PLUGIN_PATHS=./local-plugins reliaforge
```

The scaffold uses the same manifest and lifecycle contract as the demo. See
[`docs/plugin-development.md`](docs/plugin-development.md) for the contract and
[`docs/development.md`](docs/development.md) for validation commands.

## API contract

- `GET /api/v1/status`
- `GET /api/v1/live`
- `GET /api/v1/ready`
- `GET /api/v1/plugins`
- `GET /api/v1/plugins/{plugin_id}`
- `POST /api/v1/plugins/{plugin_id}/start`
- `POST /api/v1/plugins/{plugin_id}/stop`
- `POST /api/v1/plugins/{plugin_id}/restart`

`/live` is process liveness, `/ready` reports whether critical startup completed for this process,
and `/status` summarizes plugin state for operators and the UI. All three read in-memory state and
perform no dependency probes or repair writes. Restart stops, reinitializes, and starts the existing
plugin instance; it does not reload code from disk.

Catalog reads are public. Every plugin-owned route and lifecycle write uses the configured
management-auth boundary; a plugin manifest cannot opt out.
Development anonymous mode is accepted only with an explicit development/test environment
and loopback binding. Production requires proxy mode with an identity header, a strong shared
secret, and at least one trusted direct-peer network. Identity headers are accepted only from
those configured networks; invalid production configuration prevents startup.
The packaged `reliaforge` command disables forwarded-header address rewriting so this check uses
the direct TCP peer, and all-address trusted networks are rejected. Production also disables the
interactive API docs and OpenAPI endpoints. In development, browser management writes accept only
the backend origin or an origin explicitly listed in `RELIAFORGE_CORS_ORIGINS`.

Every catalog/detail record includes `available_actions`, computed by the backend from the loaded
instance, lifecycle state, dependency availability, and active dependents. Failed load records and
providers protected by a running dependent expose no actions. Clients should render this field
instead of duplicating lifecycle policy; the server still authorizes and validates every request.

Plugin fields are declared once in a `PluginSettings` subclass. The manager reads them from
`RELIAFORGE_<PLUGIN_ID>_` process environment variables (nested fields use `__`), injects one
validated instance into the plugin context, and derives the catalog JSON schema from that class.
Restart reconstructs the settings instance. Plugin settings do not parse the platform `.env`
file independently, so unrelated application or plugin keys cannot cross-contaminate validation.

## Verification

```bash
uv sync --all-extras --frozen --default-index https://pypi.org/simple
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run python -m compileall -q reliaforge scripts
uv run coverage erase
uv run coverage run -m pytest
uv run coverage report
uv build
uv run twine check dist/*
uv export --quiet --all-extras --frozen --no-emit-project --no-hashes --output-file audit-requirements.txt
uv run pip-audit --strict --requirement audit-requirements.txt
uv run python scripts/check_open_source_hygiene.py .
```

ReliaForge is licensed under the [MIT License](LICENSE).
