"""Command-line server boundary regression tests."""

from unittest.mock import patch

from reliaforge.cli import main
from reliaforge.config import AppSettings


def test_cli_disables_forwarded_header_client_rewrite() -> None:
    settings = AppSettings(
        environment="test",
        host="127.0.0.1",
        port=8123,
        auth_mode="development",
    )

    with (
        patch("reliaforge.cli.AppSettings", return_value=settings),
        patch("reliaforge.cli.create_app", return_value="asgi-app") as create_application,
        patch("reliaforge.cli.uvicorn.run") as run_server,
    ):
        main()

    create_application.assert_called_once_with(settings)
    run_server.assert_called_once_with(
        "asgi-app",
        host="127.0.0.1",
        port=8123,
        log_level="info",
        proxy_headers=False,
    )
