import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from app.models.static_findings import StaticAnalysisResult
from app.services.static_analyzer import StaticAnalyzer


@pytest.mark.asyncio
async def test_static_analyzer_python():
    analyzer = StaticAnalyzer()

    ruff_output = json.dumps([
        {
            "filename": "test.py",
            "location": {"row": 10},
            "code": "F401",
            "severity": "ERROR",
            "message": "Unused import"
        }
    ])

    bandit_output = json.dumps({
        "results": [
            {
                "filename": "test.py",
                "line_number": 5,
                "test_id": "B101",
                "issue_severity": "HIGH",
                "issue_text": "Use of assert"
            }
        ]
    })

    def mock_run(cmd, **kwargs):
        mock = MagicMock()
        mock.text = True
        if "ruff" in cmd:
            mock.stdout = ruff_output
        elif "bandit" in cmd:
            mock.stdout = bandit_output
        else:
            mock.stdout = "{}"
        return mock

    with patch("subprocess.run", side_effect=mock_run):
        result = await analyzer.analyze_files([("test.py", "import os\nassert True")])

        assert len(result.findings) == 2
        findings_tools = [f.tool for f in result.findings]
        assert "ruff" in findings_tools
        assert "bandit" in findings_tools

        ruff_finding = next(f for f in result.findings if f.tool == "ruff")
        assert ruff_finding.rule_id == "F401"
        assert ruff_finding.line == 10

@pytest.mark.asyncio
async def test_static_analyzer_js():
    analyzer = StaticAnalyzer()

    semgrep_output = json.dumps({
        "results": [
            {
                "path": "test.js",
                "start": {"line": 12},
                "check_id": (
                    "javascript.lang.security.audit.eval-with-expression."
                    "eval-with-expression"
                ),
                "extra": {
                    "severity": "ERROR",
                    "message": "Detected eval()"
                }
            }
        ]
    })

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = semgrep_output
        result = await analyzer.analyze_files([("test.js", "eval('1+1')")])

        assert len(result.findings) == 1
        assert result.findings[0].tool == "semgrep"
        assert result.findings[0].line == 12
        assert "semgrep" in result.tools_run

@pytest.mark.asyncio
async def test_tool_missing_gracefully_skipped():
    analyzer = StaticAnalyzer()

    with patch("subprocess.run", side_effect=FileNotFoundError):
        result = await analyzer.analyze_files([("test.py", "print('hello')")])

        assert len(result.findings) == 0
        assert len(result.tools_run) == 0

@pytest.mark.asyncio
async def test_tool_timeout_skipped():
    analyzer = StaticAnalyzer(timeout=1)

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["ruff"], timeout=1)):
        result = await analyzer.analyze_files([("test.py", "print('hello')")])

        assert len(result.findings) == 0
        assert len(result.tools_run) == 0

@pytest.mark.asyncio
async def test_reviewer_includes_findings_in_prompt():
    from app.models.static_findings import StaticFinding
    from app.services.reviewer import Reviewer

    with patch("google.genai.Client"):
        reviewer = Reviewer(api_key="fake")

        findings = StaticAnalysisResult(
            findings=[
                StaticFinding(
                    tool="ruff",
                    file_path="test.py",
                    line=1,
                    rule_id="F401",
                    severity="error",
                    message="Unused import"
                )
            ],
            tools_run=["ruff"],
            timing_ms={"ruff": 100}
        )

        with patch.object(reviewer, "client") as mock_client:
            mock_client.models.generate_content.return_value.text = json.dumps({
                "summary": "Test", "comments": []
            })
            mock_client.models.generate_content.return_value.usage_metadata = None

            await reviewer.review(
                pr_files=[("test.py", "import os")],
                ast_summaries=[],
                static_findings=findings
            )

            # Verify the call to Gemini included the findings
            call_args = mock_client.models.generate_content.call_args
            prompt = call_args[1]["contents"]
            assert "Static analysis findings" in prompt
            assert "test.py:1 [ruff/F401] (error): Unused import" in prompt
