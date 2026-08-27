"""Command-line application entry point."""

from __future__ import annotations

import uvicorn

from reliaforge.app import create_app
from reliaforge.config import AppSettings


def main() -> None:
    """Run the application with the validated bind address and port."""

    settings = AppSettings()
    app = create_app(settings)
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level="info",
        proxy_headers=False,
    )


if __name__ == "__main__":
    main()
