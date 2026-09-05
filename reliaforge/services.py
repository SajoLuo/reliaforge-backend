"""Provider-owned service registration for cross-plugin capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock


class ServiceNotFoundError(LookupError):
    """Raised when a requested public service is unavailable."""


class ServiceAlreadyRegisteredError(RuntimeError):
    """Raised when two providers attempt to own the same service name."""


@dataclass(frozen=True)
class ServiceRecord:
    """Ownership metadata for a service instance."""

    name: str
    provider: str
    instance: object


class ServiceContainer:
    """A small thread-safe container that never overwrites an existing service."""

    def __init__(self) -> None:
        self._records: dict[str, ServiceRecord] = {}
        self._lock = RLock()

    def register(self, name: str, provider: str, instance: object) -> None:
        """Register an instance under an explicit provider identity."""

        with self._lock:
            if name in self._records:
                raise ServiceAlreadyRegisteredError(f"service already registered: {name}")
            self._records[name] = ServiceRecord(name, provider, instance)

    def get(self, name: str) -> object:
        """Return a public service or raise a stable lookup error."""

        return self.get_record(name).instance

    def get_record(self, name: str) -> ServiceRecord:
        """Resolve an instance and its provider together."""

        with self._lock:
            try:
                return self._records[name]
            except KeyError as exc:
                raise ServiceNotFoundError(f"service not found: {name}") from exc

    def unregister_provider(self, provider: str) -> int:
        """Remove only services owned by one provider."""

        with self._lock:
            names = [name for name, record in self._records.items() if record.provider == provider]
            for name in names:
                del self._records[name]
            return len(names)

    def list_records(self) -> tuple[ServiceRecord, ...]:
        """Return an immutable ownership snapshot."""

        with self._lock:
            return tuple(self._records[name] for name in sorted(self._records))
