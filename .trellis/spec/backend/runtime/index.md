# Backend runtime development

This layer owns the Python plugin runtime, FastAPI management boundary, plugin scaffold, and bundled
neutral examples.

## Read order

1. [Plugin contract](./plugin-contract.md) for manifests, lifecycle, capabilities, settings, and
   failure isolation.
2. [API and security](./api-security.md) for routes, public reads, management authentication, and
   response ownership.
3. [Testing](./testing.md) for focused and complete verification.

Also read `docs/architecture.md`, `docs/plugin-development.md`, and the source files named by the
topic spec you are changing.

## Pre-development checklist

- Identify the owning layer: plugin lifecycle, service, router, settings, platform API, or tooling.
- Search `reliaforge/` and `templates/plugin/` before creating an abstraction.
- Define failure, cancellation, deadline, cleanup, and secret-handling behavior before adding I/O.
- Check whether a change alters the public API models consumed by the frontend.
- Add a focused behavior test that fails without the change.

## Quality check

Run the complete gate from `README.md`. At minimum, every code change requires format, lint, strict
typing, compile, branch coverage, distribution validation, dependency audit, and public-hygiene
checks. Documentation-only changes still require Markdown diff checks and the hygiene scanner.
