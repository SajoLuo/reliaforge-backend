"""Typed domain and HTTP models for runbook previews."""

from pydantic import BaseModel, ConfigDict, Field


class RunbookStep(BaseModel):
    """One ordered, descriptive step that is never executed."""

    model_config = ConfigDict(frozen=True)

    order: int = Field(ge=1)
    instruction: str = Field(min_length=1, max_length=300)


class RunbookPreview(BaseModel):
    """Deterministic read-only preview returned by the service and HTTP API."""

    model_config = ConfigDict(frozen=True)

    greeting: str
    title: str
    steps: tuple[RunbookStep, ...]
