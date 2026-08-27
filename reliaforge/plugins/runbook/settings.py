"""Bounded, non-secret settings for runbook previews."""

from typing import Annotated

from pydantic import Field

from reliaforge.plugins.settings import PluginSettings


class RunbookSettings(PluginSettings):
    """Text-only preview configuration with deterministic ordering."""

    title: str = Field(default="Routine service check", min_length=1, max_length=100)
    steps: tuple[Annotated[str, Field(min_length=1, max_length=300)], ...] = Field(
        default=(
            "Review the current service health snapshot.",
            "Confirm the intended change and its rollback path.",
            "Record the preview for operator review.",
        ),
        min_length=1,
        max_length=10,
    )
