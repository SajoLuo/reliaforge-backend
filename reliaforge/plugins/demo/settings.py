"""Non-secret demo configuration."""

from pydantic import Field

from reliaforge.plugins.settings import PluginSettings


class DemoSettings(PluginSettings):
    """Typed settings loaded only from the public demo prefix."""

    greeting: str = Field(default="Hello from ReliaForge", min_length=1, max_length=120)
    audience: str = Field(default="operator", min_length=1, max_length=80)
