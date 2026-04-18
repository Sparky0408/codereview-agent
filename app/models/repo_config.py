"""Pydantic models for repository configuration `.codereview.yml`."""

from typing import Literal

from pydantic import BaseModel, Field


class ReviewRules(BaseModel):
    """Rules defining boundaries for code review constraints."""

    max_function_lines: int = 50
    max_cyclomatic_complexity: int = 10
    max_function_args: int = 5
    banned_patterns: list[str] = Field(default_factory=list)
    severity_threshold: Literal["CRITICAL", "SUGGESTION", "NITPICK"] = "NITPICK"
    max_comments_per_file: int = 10
    max_total_comments: int = 25


class RepoConfig(BaseModel):
    """Overall configuration map from .codereview.yml."""

    enabled: bool = True
    review_rules: ReviewRules = Field(default_factory=ReviewRules)
    ignore_paths: list[str] = Field(default_factory=list)
    languages: list[str] = Field(
        default_factory=lambda: ["python", "javascript", "typescript"]
    )
