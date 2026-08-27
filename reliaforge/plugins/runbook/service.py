"""Pure in-memory runbook preview behavior."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import RunbookPreview, RunbookStep
from .settings import RunbookSettings


@runtime_checkable
class GreetingCapability(Protocol):
    """Caller-owned structural contract for the demo greeting capability."""

    def message(self) -> str: ...


class RunbookUnavailableError(RuntimeError):
    """Raised when a preview is requested while the service is stopped."""


class RunbookService:
    """Build deterministic previews without I/O, execution, or repair actions."""

    def __init__(
        self,
        settings: RunbookSettings,
        greeting: GreetingCapability,
    ) -> None:
        self._settings = settings
        self._greeting = greeting
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def preview(self, title: str | None = None) -> RunbookPreview:
        """Return text that describes possible steps but performs none of them."""

        if not self._running:
            raise RunbookUnavailableError("runbook preview service is stopped")
        selected_title = title.strip() if title is not None else self._settings.title
        if not selected_title:
            raise ValueError("runbook title must not be blank")
        if len(selected_title) > 100:
            raise ValueError("runbook title is too long")
        steps = tuple(
            RunbookStep(order=index, instruction=instruction)
            for index, instruction in enumerate(self._settings.steps, start=1)
        )
        return RunbookPreview(
            greeting=self._greeting.message(),
            title=selected_title,
            steps=steps,
        )
