"""Typed non-secret settings for {{plugin_name}}."""

from pydantic import Field

from reliaforge.plugins.settings import PluginSettings


class GeneratedPluginSettings(PluginSettings):
    """Configuration for the generated plugin."""

    message: str = Field(default="Generated plugin is running", min_length=1, max_length=200)
