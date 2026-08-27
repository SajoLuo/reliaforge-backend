"""Domain behavior for {{plugin_name}}."""

from .models import Message
from .settings import GeneratedPluginSettings


class MessageUnavailableError(RuntimeError):
    """Raised when the generated service is stopped."""


class MessageService:
    """Return one configured in-memory message."""

    def __init__(self, settings: GeneratedPluginSettings) -> None:
        self._settings = settings
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def get_message(self) -> Message:
        if not self._running:
            raise MessageUnavailableError("message service is stopped")
        return Message(message=self._settings.message, plugin_id="{{plugin_id}}")
