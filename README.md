# ReliaForge backend

[简体中文](README_CN.md)

The ReliaForge backend runs Python operations plugins behind one FastAPI service. It loads plugin
metadata, checks dependencies, starts plugins in order, reports health, and provides authenticated
start, stop, and restart operations.

This repository includes the backend, two safe example plugins, and a command that generates a new
plugin. The optional web console lives in
[`reliaforge-frontend`](https://github.com/SajoLuo/reliaforge-frontend). See the
[project documentation](https://reliaforge.dev/) or open the
[read-only demo](https://demo.reliaforge.dev/).

## Quick start

You need Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
reliaforge
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`. The server listens on
`127.0.0.1:8000` by default.

Check the backend and bundled plugins:

```bash
curl http://127.0.0.1:8000/api/v1/status
curl http://127.0.0.1:8000/api/v1/plugins
curl http://127.0.0.1:8000/api/v1/plugins/demo/greeting
curl http://127.0.0.1:8000/api/v1/plugins/runbook/preview
```

Copy `.env.example` to an untracked `.env` when you need local overrides. The example allows the
frontend development origin at `http://127.0.0.1:5530`.

## Create a plugin

```bash
reliaforge-scaffold sample_tool --destination ./local-plugins
RELIAFORGE_PLUGIN_PATHS=./local-plugins reliaforge
```

The generated plugin includes metadata, settings, lifecycle hooks, a service, an API router, and a
test. Continue with the [plugin development guide](docs/plugin-development.md).

## Main API endpoints

- `GET /api/v1/status` — backend and plugin summary
- `GET /api/v1/live` — process liveness
- `GET /api/v1/ready` — startup readiness
- `GET /api/v1/plugins` — plugin list
- `GET /api/v1/plugins/{plugin_id}` — plugin detail
- `POST /api/v1/plugins/{plugin_id}/start`
- `POST /api/v1/plugins/{plugin_id}/stop`
- `POST /api/v1/plugins/{plugin_id}/restart`

Status and catalog endpoints are read-only. Plugin routes and lifecycle operations use management
authentication. Local development can allow anonymous management only on a loopback address.
Production uses a trusted reverse proxy, operator identity header, shared secret, and trusted peer
network. See [Development](docs/development.md) for configuration and
[Architecture](docs/architecture.md) for state and failure behavior.

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
