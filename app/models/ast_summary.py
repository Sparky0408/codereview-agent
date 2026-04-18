"""Pydantic models for AST analysis summaries."""

from typing import Literal

from pydantic import BaseModel


class FunctionMetrics(BaseModel):
    """Metrics extracted for a single function or method."""

    name: str
    start_line: int
    end_line: int
    line_count: int
    arg_count: int
    cyclomatic_complexity: int


class ASTSummary(BaseModel):
    """Top-level summary of a source file's abstract syntax tree."""

    file_path: str
    language: Literal["python", "javascript", "typescript", "unknown"]
    total_lines: int
    functions: list[FunctionMetrics]
    classes: list[str]
    imports: list[str]
