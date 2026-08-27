# Development

[简体中文](zh/development.md)

## Environment

Use Python 3.11 or newer and a virtual environment. Install only from a public Python package
index:

```bash
python -m pip install -e ".[dev]"
```

Configuration uses the `RELIAFORGE_` prefix. `.env.example` documents safe local defaults. The
runtime does not require a database, queue, object store, or private network.

The platform `AppSettings` may read an untracked `.env`. Plugin `PluginSettings` classes read their
canonical `RELIAFORGE_<PLUGIN_ID>_` values from the process environment and do not independently
parse that shared file. Export plugin overrides in the shell or deployment environment.

`RELIAFORGE_CORS_ORIGINS` is a JSON list of exact HTTP origins. The example permits the local
frontend at `http://127.0.0.1:5530`. The default list is empty, wildcard origins are rejected, and
browser credentials or proxy-authentication headers are not enabled through CORS.
Development management requests that carry an `Origin` header must come from the backend's own
origin or this configured list, preventing an unrelated website from issuing loopback writes.

Proxy authentication also requires `RELIAFORGE_PROXY_TRUSTED_NETWORKS`, a JSON list of direct-peer
CIDR ranges. ReliaForge checks the socket peer address and never trusts a forwarded-address header
for this boundary. Keep the shared secret in deployment secret storage and use at least 32
characters. The `reliaforge` command disables Uvicorn proxy-header parsing. If you launch Uvicorn
directly, preserve that boundary with
`uvicorn reliaforge.app:create_app --factory --no-proxy-headers`.
All-address networks such as `0.0.0.0/0` and `::/0` are rejected because they remove the independent
direct-peer trust factor.

Interactive API docs and the OpenAPI document are available in development and test environments.
Production disables both endpoints to keep the management surface minimal.

`RELIAFORGE_PLUGIN_OPERATION_TIMEOUT_SECONDS` is one end-to-end deadline for a requested lifecycle
action, including time queued behind another lifecycle action. A restart shares that budget across
stop, initialization, start, and timeout cleanup; it does not receive a fresh deadline for each
phase. Shutdown similarly includes operation-lock wait in its total budget and never bypasses that
lock to mutate an in-flight plugin.

## Quality gates

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

A nonzero result is a failure. Coverage enforces at least 85% branch-aware source coverage, pytest
treats warnings as errors, and mypy checks runtime, tests, and hygiene scripts in strict mode. The
same sequence runs in GitHub Actions on Python 3.11 and 3.13. Do not mark an unavailable command as
passed. `audit-requirements.txt` is a local generated file and must not be committed.

## HTTP smoke

Start `reliaforge`, then verify the real data path:

```bash
curl --fail http://127.0.0.1:8000/api/v1/status
curl --fail http://127.0.0.1:8000/api/v1/live
curl --fail http://127.0.0.1:8000/api/v1/ready
curl --fail http://127.0.0.1:8000/api/v1/plugins/demo/greeting
curl --fail http://127.0.0.1:8000/api/v1/plugins/runbook/preview
```

Stop the process normally so the plugin shutdown lifecycle is exercised.
