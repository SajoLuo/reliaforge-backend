# Testing

## Trusted test layers

- Focused unit and contract tests under `tests/` prove manifests, graph behavior, lifecycle, settings,
  auth, events, logging, scaffolding, and hygiene.
- `tests/test_api.py` uses FastAPI `TestClient` to prove exact public HTTP shapes and real neutral
  plugin behavior.
- `tests/test_lifecycle.py` is the reference for dependency order, cleanup, concurrent operations,
  deadlines, health, and available actions.
- Distribution checks prove the wheel and source archive contain typed markers, templates, and
  bundled manifests.

## Rules

- Add a regression test at the narrowest layer that proves observable behavior, not implementation
  call counts alone.
- Use explicit `AppSettings` test fixtures and loopback development boundaries; do not read a
  contributor's environment or local `.env`.
- Keep tests deterministic and free of real network, database, filesystem outside temporary paths,
  or command side effects.
- Test both success and failure cleanup for lifecycle or context ownership changes.
- For API changes, assert exact response fields and update the frontend contract proof.
- Do not weaken branch coverage, strict warnings, ruff complexity, or mypy to land a change.

## Focused commands

```bash
uv run pytest tests/test_manifest.py tests/test_loader_contract.py
uv run pytest tests/test_lifecycle.py
uv run pytest tests/test_api.py tests/test_config_auth.py
uv run pytest tests/test_settings_contract.py
```

Use focused commands while iterating, then run every command under `README.md#verification` before
completion.

## Public hygiene

`scripts/check_open_source_hygiene.py` scans all repository material rather than only tracked source.
Keep its fixtures neutral, never print matched secret values, and extend its tests when a new file
class or risk pattern enters the repository.

Substantive repository documentation keeps English source files under `docs/` and complete
Simplified Chinese counterparts under `docs/zh/`. Root and scaffold entry points use `README.md`
plus `README_CN.md`. Preserve reciprocal language links and the one-to-one file set enforced by
`tests/test_docs_locales.py`; identifiers, routes, configuration keys, commands, and code remain
canonical across both languages.

Write public documentation for an SRE using the current release. Lead with the task or result, use
plain operational language, and explain project-specific terms on first use. Omit design history,
rejected alternatives, internal predecessors, and irrelevant compatibility claims. Keep a negative
boundary only when it prevents a likely mistake, unsafe deployment, false success, or unsupported
operation.

Plugin onboarding must name the files to create or replace, include complete runnable code, and
show the request, expected response, and relevant failure cases. Do not skip the main task with
instructions such as "replace the business logic." When changing tutorial code, copy the published
examples into a freshly scaffolded plugin and run them, including behavior after stop and restart.
Keep executable examples identical in both languages.
