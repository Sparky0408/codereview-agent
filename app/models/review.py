"""Pydantic models for code review output structure."""

from enum import StrEnum

from pydantic import BaseModel


class Severity(StrEnum):
    """Tiered severity levels for review comments."""

    CRITICAL = "CRITICAL"
    SUGGESTION = "SUGGESTION"
    NITPICK = "NITPICK"


class ReviewComment(BaseModel):
    """An individual line-specific code review comment."""

    file_path: str
    line: int
    severity: Severity
    comment: str
    suggested_code: str | None = None


class ReviewOutput(BaseModel):
    """Top-level output strictly enforcing the response format from Gemini."""

    summary: str
    comments: list[ReviewComment]
