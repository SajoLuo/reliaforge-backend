"""In-memory event delivery for lifecycle observation and loose coupling."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from reliaforge.logging import get_platform_logger

logger = get_platform_logger()


class PluginEvent(BaseModel):
    """A typed event emitted by the platform or a plugin."""

    model_config = ConfigDict(frozen=True)

    topic: str = Field(min_length=1, max_length=100)
    plugin_id: str = Field(min_length=1, max_length=64)
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


EventHandler = Callable[[PluginEvent], Awaitable[None]]


class EventDeliveryFailure(BaseModel):
    """Secret-safe metadata for one isolated handler failure."""

    model_config = ConfigDict(frozen=True)

    owner: str
    reason: Literal["handler_error", "handler_timeout"]


class EventDeliveryReport(BaseModel):
    """Observable result of dispatching one event to its current subscribers."""

    model_config = ConfigDict(frozen=True)

    event: PluginEvent
    delivered: int = Field(ge=0)
    failures: tuple[EventDeliveryFailure, ...] = ()


class EventBus:
    """A process-local event bus with isolated handlers and deadlines."""

    def __init__(self, handler_timeout_seconds: float) -> None:
        if handler_timeout_seconds <= 0:
            raise ValueError("handler timeout must be positive")
        self._handler_timeout_seconds = handler_timeout_seconds
        self._handlers: dict[str, list[tuple[str, EventHandler]]] = defaultdict(list)

    def subscribe(self, topic: str, owner: str, handler: EventHandler) -> None:
        """Register one async handler owned by a plugin."""

        self._handlers[topic].append((owner, handler))

    def unsubscribe_owner(self, owner: str) -> None:
        """Remove every subscription registered by an owner."""

        for topic in tuple(self._handlers):
            self._handlers[topic] = [item for item in self._handlers[topic] if item[0] != owner]
            if not self._handlers[topic]:
                del self._handlers[topic]

    async def publish(self, event: PluginEvent) -> EventDeliveryReport:
        """Dispatch concurrently while isolating and reporting handler failures."""

        handlers = tuple(self._handlers.get(event.topic, ()))
        if not handlers:
            return EventDeliveryReport(event=event, delivered=0)

        outcomes = await asyncio.gather(
            *(self._deliver(owner, handler, event) for owner, handler in handlers)
        )
        failures = tuple(failure for failure in outcomes if failure is not None)
        return EventDeliveryReport(
            event=event,
            delivered=len(handlers) - len(failures),
            failures=failures,
        )

    async def _deliver(
        self,
        owner: str,
        handler: EventHandler,
        event: PluginEvent,
    ) -> EventDeliveryFailure | None:
        try:
            async with asyncio.timeout(self._handler_timeout_seconds):
                await handler(event)
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            logger.warning(
                "event handler timed out (topic=%s owner=%s)",
                event.topic,
                owner,
            )
            return EventDeliveryFailure(owner=owner, reason="handler_timeout")
        except Exception as exc:
            logger.warning(
                "event handler failed (topic=%s owner=%s error=%s)",
                event.topic,
                owner,
                type(exc).__name__,
            )
            return EventDeliveryFailure(owner=owner, reason="handler_error")
        return None
