"""Process-local lifecycle phase used by side-effect-free probes."""

from __future__ import annotations

from enum import StrEnum


class RuntimePhase(StrEnum):
    """Current process lifecycle phase."""

    STARTING = "starting"
    READY = "ready"
    STOPPING = "stopping"


class RuntimeState:
    """Small in-memory state machine for local readiness."""

    def __init__(self) -> None:
        self._phase = RuntimePhase.STARTING

    @property
    def phase(self) -> RuntimePhase:
        """Return the current process-local phase."""

        return self._phase

    def mark_ready(self) -> None:
        """Publish readiness after critical startup has completed."""

        if self._phase is not RuntimePhase.STARTING:
            raise RuntimeError("only a starting runtime can become ready")
        self._phase = RuntimePhase.READY

    def mark_stopping(self) -> None:
        """Withdraw readiness before plugin shutdown begins."""

        self._phase = RuntimePhase.STOPPING
