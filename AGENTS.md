# Contributor guidance

Before changing this repository, read `.trellis/spec/backend/runtime/index.md` and the topic files it
routes to.

This repository owns the Python runtime, management API, neutral example plugins, scaffold, and
backend-local contracts. Cross-project documentation belongs in `SajoLuo/reliaforge`; console
behavior belongs in `SajoLuo/reliaforge-frontend`.

Use the bundled `demo` and `runbook` plugins plus focused tests as the primary examples. Preserve the
manifest-first import boundary, server-owned lifecycle policy, side-effect-free health contract, and
fail-closed production authentication. Run the complete verification commands in `README.md` before
proposing a change.
