"""Real TestClient coverage for management and demo API contracts."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from reliaforge.app import create_app
from reliaforge.config import AppSettings


def test_probes_status_and_catalog_return_exact_public_shapes(test_settings: AppSettings) -> None:
    app = create_app(test_settings)
    with TestClient(app) as client:
        assert client.get("/api/v1/live").json() == {
            "status": "alive",
            "version": "0.1.0",
        }
        assert client.get("/api/v1/ready").json() == {
            "status": "ready",
            "version": "0.1.0",
            "phase": "ready",
        }
        platform_status = client.get("/api/v1/status")
        assert platform_status.status_code == 200
        assert platform_status.json() == {
            "status": "healthy",
            "version": "0.1.0",
            "plugins": {
                "total": 2,
                "running": 2,
                "degraded": 0,
                "stopped": 0,
                "error": 0,
            },
        }

        catalog = client.get("/api/v1/plugins")
        assert catalog.status_code == 200
        plugins = {item["id"]: item for item in catalog.json()["plugins"]}
        plugin = plugins["demo"]
        assert set(plugin) == {
            "id",
            "name",
            "version",
            "description",
            "api_version",
            "state",
            "available_actions",
            "dependencies",
            "capabilities",
            "settings_schema",
            "frontend",
            "health",
        }
        assert plugin["id"] == "demo"
        assert plugin["state"] == "running"
        assert plugin["available_actions"] == []
        assert plugins["runbook"]["dependencies"] == [{"id": "demo", "version": "^1.0.0"}]
        assert plugins["runbook"]["capabilities"] == ["runbook.preview"]
        assert plugins["runbook"]["available_actions"] == ["stop", "restart"]
        assert plugins["runbook"]["settings_schema"]["properties"]["steps"]["maxItems"] == 10

        with patch.object(
            app.state.plugin_manager,
            "platform_status",
            side_effect=AssertionError("probes must not inspect plugin health"),
        ):
            assert client.get("/api/v1/live").status_code == 200
            assert client.get("/api/v1/ready").status_code == 200


def test_readiness_is_withdrawn_before_lifespan_start(test_settings: AppSettings) -> None:
    client = TestClient(create_app(test_settings))
    try:
        response = client.get("/api/v1/ready")
    finally:
        client.close()
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "version": "0.1.0",
        "phase": "starting",
    }


def test_unpublished_probe_and_action_aliases_do_not_exist(
    test_settings: AppSettings,
) -> None:
    with TestClient(create_app(test_settings)) as client:
        assert client.get("/api/v1/health").status_code == 404
        assert client.post("/api/v1/plugins/demo/reload").status_code == 404


def test_demo_greeting_and_lifecycle_operations_use_real_state(test_settings: AppSettings) -> None:
    with TestClient(create_app(test_settings)) as client:
        greeting = client.get("/api/v1/plugins/demo/greeting")
        assert greeting.status_code == 200
        assert greeting.json() == {
            "message": "Hello from ReliaForge, operator!",
            "plugin_id": "demo",
        }

        protected = client.post("/api/v1/plugins/demo/stop")
        assert protected.status_code == 409
        assert protected.json() == {"detail": "active dependents prevent stop: runbook"}

        preview = client.get("/api/v1/plugins/runbook/preview")
        assert preview.status_code == 200
        assert preview.json() == {
            "greeting": "Hello from ReliaForge, operator!",
            "title": "Routine service check",
            "steps": [
                {"order": 1, "instruction": "Review the current service health snapshot."},
                {
                    "order": 2,
                    "instruction": "Confirm the intended change and its rollback path.",
                },
                {"order": 3, "instruction": "Record the preview for operator review."},
            ],
        }

        runbook_stopped = client.post("/api/v1/plugins/runbook/stop")
        assert runbook_stopped.status_code == 200
        assert runbook_stopped.json()["available_actions"] == ["start"]
        assert client.get("/api/v1/plugins/runbook/preview").status_code == 503

        stopped = client.post("/api/v1/plugins/demo/stop")
        assert stopped.status_code == 200
        assert stopped.json()["state"] == "stopped"
        assert stopped.json()["available_actions"] == ["start"]
        assert client.get("/api/v1/plugins/demo/greeting").status_code == 503

        started = client.post("/api/v1/plugins/demo/start")
        assert started.status_code == 200
        assert started.json()["state"] == "running"
        assert started.json()["available_actions"] == ["stop", "restart"]

        runbook_started = client.post("/api/v1/plugins/runbook/start")
        assert runbook_started.status_code == 200
        assert client.get("/api/v1/plugins/demo").json()["available_actions"] == []

        restarted = client.post("/api/v1/plugins/runbook/restart")
        assert restarted.status_code == 200
        assert restarted.json()["health"]["status"] == "healthy"


def test_unknown_plugin_returns_404_without_internal_details(test_settings: AppSettings) -> None:
    with TestClient(create_app(test_settings)) as client:
        response = client.get("/api/v1/plugins/not_present")
        assert response.status_code == 404
        assert response.json() == {"detail": "plugin not found: not_present"}


def test_runbook_unexpected_error_maps_to_generic_500(test_settings: AppSettings) -> None:
    app = create_app(test_settings)
    with TestClient(app) as client:
        plugin = app.state.plugin_manager._records["runbook"].instance
        assert plugin is not None and plugin.service is not None
        private_value = "private-preview-fixture"
        with patch.object(plugin.service, "preview", side_effect=RuntimeError(private_value)):
            response = client.get("/api/v1/plugins/runbook/preview")
        assert response.status_code == 500
        assert response.json() == {"detail": "Internal server error"}
        assert private_value not in response.text
