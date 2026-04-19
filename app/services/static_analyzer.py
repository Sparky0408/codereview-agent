"""Service to run static analysis tools (ruff, bandit, semgrep) on code."""

import asyncio
import json
import logging
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from app.models.static_findings import StaticAnalysisResult, StaticFinding

logger = logging.getLogger(__name__)

class StaticAnalyzer:
    """Runs static analysis tools via subprocess and parses their output."""

    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout

    async def analyze_files(self, files: list[tuple[str, str]]) -> StaticAnalysisResult:
        """Run ruff, bandit, and semgrep on the provided file contents.

        Args:
            files: List of (file_path, content) tuples.

        Returns:
            StaticAnalysisResult containing findings and metrics.
        """
        findings: list[StaticFinding] = []
        tools_run: list[str] = []
        timing_ms: dict[str, int] = {}

        if not files:
            return StaticAnalysisResult(findings=[], tools_run=[], timing_ms={})

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Write files to temp directory
            python_files: list[str] = []
            js_ts_files: list[str] = []

            for file_path, content in files:
                target_path = tmp_path / file_path
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(content, encoding="utf-8")

                ext = file_path.split(".")[-1].lower() if "." in file_path else ""
                if ext == "py":
                    python_files.append(file_path)
                elif ext in ["js", "ts", "jsx", "tsx"]:
                    js_ts_files.append(file_path)

            # Define tool runner
            async def run_tool(name: str, cmd: list[str]) -> tuple[str, int, str | None]:
                start_time = time.perf_counter()
                try:
                    result = await asyncio.to_thread(
                        subprocess.run,
                        cmd,
                        capture_output=True,
                        text=True,
                        cwd=tmp_dir,
                        timeout=self.timeout,
                    )
                    elapsed = int((time.perf_counter() - start_time) * 1000)
                    return name, elapsed, result.stdout
                except FileNotFoundError:
                    logger.warning(f"Tool {name} not found on PATH.")
                    return name, 0, None
                except subprocess.TimeoutExpired:
                    logger.warning(f"Tool {name} timed out after {self.timeout}s.")
                    return name, int(self.timeout * 1000), None
                except Exception as e:
                    logger.error(f"Unexpected error running {name}: {e}")
                    return name, 0, None

            tasks = []
            if python_files:
                tasks.append(run_tool("ruff", ["ruff", "check", "--format", "json", "."]))
                tasks.append(run_tool("bandit", ["bandit", "-f", "json", "-r", "."]))

            if js_ts_files:
                # Using --config auto for semgrep to detect rules
                tasks.append(run_tool(
                    "semgrep",
                    ["semgrep", "scan", "--json", "--config", "auto", "."],
                ))

            results = await asyncio.gather(*tasks)

            for name, elapsed, stdout in results:
                if stdout is None:
                    continue

                tools_run.append(name)
                timing_ms[name] = elapsed

                try:
                    raw_data = json.loads(stdout)
                    if name == "ruff":
                        self._parse_ruff(raw_data, findings)
                    elif name == "bandit":
                        self._parse_bandit(raw_data, findings)
                    elif name == "semgrep":
                        self._parse_semgrep(raw_data, findings)
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse JSON output from {name}")

        return StaticAnalysisResult(
            findings=findings,
            tools_run=tools_run,
            timing_ms=timing_ms
        )

    def _parse_ruff(self, data: list[dict[str, Any]], findings: list[StaticFinding]) -> None:
        for issue in data:
            findings.append(StaticFinding(
                tool="ruff",
                file_path=issue.get("filename", ""),
                line=issue.get("location", {}).get("row", 0),
                rule_id=issue.get("code", ""),
                severity="error" if issue.get("severity") == "ERROR" else "warning",
                message=issue.get("message", "")
            ))

    def _parse_bandit(self, data: dict[str, Any], findings: list[StaticFinding]) -> None:
        for issue in data.get("results", []):
            findings.append(StaticFinding(
                tool="bandit",
                file_path=issue.get("filename", ""),
                line=issue.get("line_number", 0),
                rule_id=issue.get("test_id", ""),
                severity=issue.get("issue_severity", "low").lower(),
                message=issue.get("issue_text", "")
            ))

    def _parse_semgrep(self, data: dict[str, Any], findings: list[StaticFinding]) -> None:
        for issue in data.get("results", []):
            findings.append(StaticFinding(
                tool="semgrep",
                file_path=issue.get("path", ""),
                line=issue.get("start", {}).get("line", 0),
                rule_id=issue.get("check_id", ""),
                severity=issue.get("extra", {}).get("severity", "info").lower(),
                message=issue.get("extra", {}).get("message", "")
            ))
