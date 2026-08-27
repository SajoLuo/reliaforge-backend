"""Side-effect-free domain behavior for the demo plugin."""

from __future__ import annotations

from .models import Greeting
from .settings import DemoSettings


class GreetingUnavailableError(RuntimeError):
    """Raised when a greeting is requested while the demo is stopped."""


class GreetingService:
    """Produce an in-memory greeting without external dependencies."""

    def __init__(self, settings: DemoSettings) -> None:
        self._settings = settings
        self._running = False

    @property
    def is_running(self) -> bool:
        """Return the current in-memory service state."""

        return self._running

    def start(self) -> None:
        """Mark the service ready."""

        self._running = True

    def stop(self) -> None:
        """Mark the service stopped."""

        self._running = False

    def greet(self) -> Greeting:
        """Build a greeting while the service is running."""

        if not self._running:
            raise GreetingUnavailableError("greeting service is stopped")
        return Greeting(message=self.message(), plugin_id="demo")

    def message(self) -> str:
        """Return the structural capability used by other plugins."""

        if not self._running:
            raise GreetingUnavailableError("greeting service is stopped")
        return f"{self._settings.greeting}, {self._settings.audience}!"
