"""Typed domain and HTTP response models for the demo plugin."""

from pydantic import BaseModel, ConfigDict


class Greeting(BaseModel):
    """Service-layer greeting value."""

    model_config = ConfigDict(frozen=True)

    message: str
    plugin_id: str


class GreetingResponse(BaseModel):
    """Public greeting API response."""

    message: str
    plugin_id: str
