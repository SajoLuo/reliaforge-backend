"""Typed models for {{plugin_name}}."""

from pydantic import BaseModel, ConfigDict


class Message(BaseModel):
    """Service result returned by the generated plugin."""

    model_config = ConfigDict(frozen=True)

    message: str
    plugin_id: str
