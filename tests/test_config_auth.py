"""Configuration and management-auth fail-closed behavior."""

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from reliaforge.app import create_app
from reliaforge.config import AppSettings


def test_production_development_auth_is_rejected() -> None:
    with pytest.raises(ValidationError, match="production requires proxy"):
        AppSettings(
            environment="production",
            host="127.0.0.1",
            auth_mode="development",
        )


def test_development_auth_non_loopback_host_is_rejected() -> None:
    with pytest.raises(ValidationError, match="loopback"):
        AppSettings(
            environment="development",
            host="0.0.0.0",
            auth_mode="development",
        )


def test_wildcard_cors_origin_is_rejected() -> None:
    with pytest.raises(ValidationError, match="wildcard CORS"):
        AppSettings(
            environment="test",
            host="127.0.0.1",
            auth_mode="development",
            cors_origins=["*"],
        )

    with pytest.raises(ValidationError, match="explicit HTTP origins"):
        AppSettings(
            environment="test",
            host="127.0.0.1",
            auth_mode="development",
            cors_origins=["http://127.0.0.1:5530/"],
        )


def test_cors_is_absent_by_default_and_exact_when_configured() -> None:
    origin = "http://127.0.0.1:5530"
    default_settings = AppSettings(
        environment="test",
        host="127.0.0.1",
        auth_mode="development",
    )
    with TestClient(create_app(default_settings)) as client:
        response = client.get("/api/v1/status", headers={"Origin": origin})
        assert "access-control-allow-origin" not in response.headers

    configured_settings = AppSettings(
        environment="test",
        host="127.0.0.1",
        auth_mode="development",
        cors_origins=[origin],
    )
    with TestClient(create_app(configured_settings)) as client:
        response = client.get("/api/v1/status", headers={"Origin": origin})
        assert response.headers["access-control-allow-origin"] == origin
        assert "access-control-allow-credentials" not in response.headers
        preflight = client.options(
            "/api/v1/plugins/demo/restart",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": configured_settings.proxy_secret_header,
            },
        )
        assert preflight.status_code == 400


def test_proxy_auth_rejects_weak_secret_and_missing_trusted_network() -> None:
    with pytest.raises(ValidationError, match="strong injected shared secret"):
        AppSettings(
            environment="production",
            host="0.0.0.0",
            auth_mode="proxy",
            proxy_shared_secret=SecretStr("replace-with-a-random-value"),
            proxy_trusted_networks=["127.0.0.0/8"],
        )
    with pytest.raises(ValidationError, match="trusted network"):
        AppSettings(
            environment="production",
            host="0.0.0.0",
            auth_mode="proxy",
            proxy_shared_secret=SecretStr("a" * 32),
        )
    with pytest.raises(ValidationError, match="printable ASCII"):
        AppSettings(
            environment="production",
            host="0.0.0.0",
            auth_mode="proxy",
            proxy_shared_secret=SecretStr("密" * 32),
            proxy_trusted_networks=["127.0.0.0/8"],
        )
    with pytest.raises(ValidationError, match="must not trust every address"):
        AppSettings(
            environment="production",
            host="0.0.0.0",
            auth_mode="proxy",
            proxy_shared_secret=SecretStr("a" * 32),
            proxy_trusted_networks=["0.0.0.0/0"],
        )


def test_development_management_rejects_cross_origin_writes() -> None:
    allowed_origin = "http://127.0.0.1:5530"
    settings = AppSettings(
        environment="test",
        host="127.0.0.1",
        port=8000,
        auth_mode="development",
        cors_origins=[allowed_origin],
    )
    with TestClient(create_app(settings), client=("127.0.0.1", 50000)) as client:
        rejected = client.post(
            "/api/v1/plugins/runbook/restart",
            headers={"Origin": "https://untrusted.example"},
        )
        assert rejected.status_code == 403
        assert rejected.json() == {"detail": "Development management origin is not allowed"}

        assert (
            client.post(
                "/api/v1/plugins/runbook/restart",
                headers={"Origin": allowed_origin},
            ).status_code
            == 200
        )
        assert client.post("/api/v1/plugins/runbook/restart").status_code == 200


def test_proxy_auth_requires_headers_and_accepts_valid_identity() -> None:
    shared_value = "test-proxy-value-with-at-least-32-chars"
    settings = AppSettings(
        environment="production",
        host="0.0.0.0",
        auth_mode="proxy",
        proxy_shared_secret=SecretStr(shared_value),
        proxy_trusted_networks=["127.0.0.0/8"],
    )
    with TestClient(create_app(settings), client=("127.0.0.1", 50000)) as client:
        assert client.get("/api/v1/plugins").status_code == 200
        assert client.get("/api/v1/plugins/demo/greeting").status_code == 401
        assert client.post("/api/v1/plugins/demo/restart").status_code == 401
        assert (
            client.post(
                "/api/v1/plugins/demo/restart",
                headers={
                    settings.proxy_identity_header: "test-user",
                    settings.proxy_secret_header: "wrong-value",
                },
            ).status_code
            == 403
        )
        accepted = client.get(
            "/api/v1/plugins/demo/greeting",
            headers={
                settings.proxy_identity_header: "test-user",
                settings.proxy_secret_header: shared_value,
            },
        )
        assert accepted.status_code == 200
        restarted = client.post(
            "/api/v1/plugins/runbook/restart",
            headers={
                settings.proxy_identity_header: "test-user",
                settings.proxy_secret_header: shared_value,
            },
        )
        assert restarted.status_code == 200
        assert restarted.json()["state"] == "running"


def test_proxy_auth_rejects_valid_headers_from_untrusted_peer() -> None:
    shared_value = "test-proxy-value-with-at-least-32-chars"
    settings = AppSettings(
        environment="production",
        host="0.0.0.0",
        auth_mode="proxy",
        proxy_shared_secret=SecretStr(shared_value),
        proxy_trusted_networks=["127.0.0.0/8"],
    )
    with TestClient(create_app(settings), client=("203.0.113.10", 50000)) as client:
        response = client.post(
            "/api/v1/plugins/demo/restart",
            headers={
                settings.proxy_identity_header: "test-user",
                settings.proxy_secret_header: shared_value,
                "X-Forwarded-For": "127.0.0.1",
                "X-Real-IP": "127.0.0.1",
            },
        )
        assert response.status_code == 403
        assert response.json() == {"detail": "Management proxy is not trusted"}


def test_production_disables_api_documentation_endpoints() -> None:
    settings = AppSettings(
        environment="production",
        host="0.0.0.0",
        auth_mode="proxy",
        proxy_shared_secret=SecretStr("test-proxy-value-with-at-least-32-chars"),
        proxy_trusted_networks=["127.0.0.0/8"],
    )
    with TestClient(create_app(settings), client=("127.0.0.1", 50000)) as client:
        assert client.get("/api/v1/docs").status_code == 404
        assert client.get("/api/v1/openapi.json").status_code == 404
