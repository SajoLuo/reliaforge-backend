# Development

[简体中文](zh/development.md)

## Set up the environment

Use Python 3.11 or newer in a virtual environment:

```bash
python -m pip install -e ".[dev]"
```

ReliaForge uses environment variables with the `RELIAFORGE_` prefix. `.env.example` contains safe
local defaults. The backend does not need a database, queue, object store, or private network.

The application can read an untracked `.env`. Plugin settings read
`RELIAFORGE_<PLUGIN_ID>_` values from the process environment. Export plugin-specific values in the
shell or deployment environment.

## Configure browser access

`RELIAFORGE_CORS_ORIGINS` is a JSON list of exact HTTP origins, each with a protocol, host, and port. `.env.example` allows the local
frontend at `http://127.0.0.1:5530`. An empty list disables cross-origin access, and wildcard origins
are rejected. A browser management request with an `Origin` header must come from the backend origin
or this list.

## Configure production authentication

`RELIAFORGE_PROXY_TRUSTED_NETWORKS` is a JSON list of direct proxy CIDR ranges. ReliaForge checks the
socket peer address, not a forwarded address header. Keep the shared secret in deployment secret
storage and use at least 32 characters. The trusted network cannot be `0.0.0.0/0` or `::/0`.

The packaged `reliaforge` command disables Uvicorn proxy-header parsing. If you start Uvicorn
directly, use:

```bash
uvicorn reliaforge.app:create_app --factory --no-proxy-headers
```

Production disables the interactive API documentation and OpenAPI document.

## Run one instance

Run one backend process for a deployment. Each process owns its plugin instances and management
state; multiple workers do not share start and stop decisions. Configure any process supervisor
to restart the backend when needed. A fresh backend starts all discovered plugins, including the
bundled examples. Stopping a plugin through the API affects the current process only.

## Set lifecycle timeouts

`RELIAFORGE_PLUGIN_OPERATION_TIMEOUT_SECONDS` sets one total limit for a requested start, stop, or
restart, including time waiting behind another operation. Restart shares the same limit across stop,
initialize, start, and cleanup. The console allows 310 seconds for lifecycle requests, covering the
backend's maximum 300-second budget plus response time. Configure the proxy timeout accordingly.
If the connection breaks, read the plugin state before retrying: a lost response does not tell you
whether the operation completed.

## Run the quality gates

Run every command from the repository root:

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

A nonzero result is a failure. Coverage includes statements and branches and must reach 85%. Python
warnings fail the tests, and type checks use mypy's strict mode. `audit-requirements.txt` is generated locally and
must not be committed.

## Check a running backend

Start `reliaforge`, then call the real HTTP endpoints:

```bash
curl --fail http://127.0.0.1:8000/api/v1/status
curl --fail http://127.0.0.1:8000/api/v1/live
curl --fail http://127.0.0.1:8000/api/v1/ready
curl --fail http://127.0.0.1:8000/api/v1/plugins/demo/greeting
curl --fail http://127.0.0.1:8000/api/v1/plugins/runbook/preview
```

Stop the process normally so plugin cleanup also runs.
