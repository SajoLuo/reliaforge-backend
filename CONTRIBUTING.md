# Contributing

Thank you for helping improve ReliaForge.

1. Discuss substantial contract changes in an issue before implementation.
2. Keep plugins isolated and use the service container for cross-plugin capabilities.
3. Put domain logic in services, not FastAPI routers or lifecycle hooks.
4. Add tests for successful behavior, validation failures, and lifecycle cleanup.
5. Run the full verification sequence from `docs/development.md`; warnings, type errors, coverage
   below the configured threshold, dependency advisories, and hygiene findings are failures.
6. Do not include credentials, private infrastructure references, generated reports, or
   organization-specific assets.

By contributing, you agree that your contribution is licensed under the repository's MIT
License and that you have the right to submit it.
