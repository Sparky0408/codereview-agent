from typing import Literal

from pydantic import BaseModel


class StaticFinding(BaseModel):
    """Represents a single issue found by a static analysis tool."""
    tool: Literal['ruff', 'bandit', 'semgrep']
    file_path: str
    line: int
    rule_id: str  # e.g., F401, B105
    severity: str  # tool-reported
    message: str

class StaticAnalysisResult(BaseModel):
    """Summary of all static analysis findings."""
    findings: list[StaticFinding]
    tools_run: list[str]  # which tools actually executed
    timing_ms: dict[str, int]  # per-tool timing
