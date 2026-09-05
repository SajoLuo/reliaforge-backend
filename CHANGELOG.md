# Changelog

All notable changes to ReliaForge Backend are documented here.

## Unreleased

- Clarify the platform's role: developers provide services as plugins; runbooks are one example.
- Run plugin cleanup after partial initialization fails, times out, or is cancelled.
- Require consumers to declare a shared service's provider in their manifest dependencies.
- Simplify the generated plugin's models and remove duplicate lifecycle event examples.
- Document the service publishing path, partial cleanup, and single-process deployment limits.
- Add a complete bilingual tutorial that turns a Python service-owner lookup into a plugin API.

## 0.1.0 - 2026-08-28

- Publish the manifest-first plugin runtime, lifecycle manager, and management API.
- Add typed settings, capability contracts, dependency isolation, and bounded event delivery.
- Add neutral demo and runbook plugins plus a tested plugin scaffold.
- Add strict type, coverage, package, dependency, hygiene, and real-process release gates.
