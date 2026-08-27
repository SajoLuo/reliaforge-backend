# {{plugin_name}}

This plugin was generated from the ReliaForge public template.

- Customize `manifest.json` without changing its ID.
- Keep domain behavior in `service.py`.
- Keep the router limited to validation, delegation, and HTTP error mapping.
- Define non-secret fields once in the `PluginSettings` subclass in `settings.py`.
- Declare plugin dependencies as `{ "id": "provider", "version": "^1.0.0" }` objects.
- Inject secrets through deployment configuration; never add them to the manifest.

Run the starter behavior test with `pytest` and `pytest-asyncio` installed. The explicit asyncio
marker also works when pytest-asyncio uses strict mode:

```console
python -m pytest tests/test_plugin.py
```
