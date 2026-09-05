# {{plugin_name}}

[简体中文](README_CN.md)

This plugin returns a configurable message through HTTP.

## Run it and call the API

From the backend directory, set `RELIAFORGE_PLUGIN_PATHS` to the parent containing this plugin,
then restart the backend. In local development, call:

```bash
curl --fail http://127.0.0.1:8000/api/v1/plugins/{{plugin_id}}/message
```

With the generated settings, the response is:

```json
{"message": "Generated plugin is running", "plugin_id": "{{plugin_id}}"}
```

A stopped plugin returns HTTP `503`. In production, authenticate through the deployment's proxy
before calling the API.

## Add your own function

The [plugin tutorial](https://github.com/SajoLuo/reliaforge-backend/blob/main/docs/plugin-development.md)
shows how to add a Python lookup function and an API that calls it, with complete files and requests.
For this plugin:

- Keep the directory name and manifest ID as `{{plugin_id}}`.
- Put the tool's code in `service.py` or another Python module. Add its API in `router.py`.
- Define settings in `settings.py` and set their environment variables before starting the backend.
- If you create clients or background tasks, release them in `_on_stop()`, even after partial startup.
- List another plugin in `dependencies` before using its shared Python services.
- Keep secrets in deployment configuration and out of code, default values, and logs.
- Replace this README's example with your URL, parameters, results, and failure cases.

## Test the plugin

With `pytest` and `pytest-asyncio` installed, run this from the plugin directory:

```bash
python -m pytest tests/test_plugin.py
```
