"""Tests for the ASTAnalyzer service."""

from pathlib import Path

import pytest

from app.services.ast_analyzer import ASTAnalyzer

SAMPLE_DIR = Path(__file__).parent.parent / "fixtures" / "sample_code"


@pytest.fixture
def analyzer() -> ASTAnalyzer:
    """Fixture to provide a loaded ASTAnalyzer instance."""
    return ASTAnalyzer()


def test_detect_language_python(analyzer: ASTAnalyzer) -> None:
    """Detect python file extensions correctly."""
    assert analyzer.detect_language("test.py") == "python"


def test_detect_language_js(analyzer: ASTAnalyzer) -> None:
    """Detect javascript file extensions correctly."""
    assert analyzer.detect_language("component.jsx") == "javascript"
    assert analyzer.detect_language("utils.js") == "javascript"


def test_detect_language_ts(analyzer: ASTAnalyzer) -> None:
    """Detect typescript file extensions correctly."""
    assert analyzer.detect_language("types.ts") == "typescript"
    assert analyzer.detect_language("App.tsx") == "typescript"


def test_detect_language_unknown(analyzer: ASTAnalyzer) -> None:
    """Detect unknown file extensions correctly."""
    assert analyzer.detect_language("main.go") == "unknown"


@pytest.mark.asyncio
async def test_analyze_python_sample(analyzer: ASTAnalyzer) -> None:
    """Extract metrics correctly from a python file."""
    file_path = SAMPLE_DIR / "sample.py"
    content = file_path.read_text("utf-8")

    summary = await analyzer.analyze("sample.py", content)

    assert summary is not None
    assert summary.language == "python"
    assert summary.total_lines > 0

    assert "Calculator" in summary.classes
    assert any("import math" in imp or "import" in imp for imp in summary.imports)

    func_names = [f.name for f in summary.functions]
    assert "__init__" in func_names
    assert "add" in func_names
    assert "complex_function" in func_names

    complex_func = next(f for f in summary.functions if f.name == "complex_function")
    assert complex_func.cyclomatic_complexity > 3
    assert complex_func.arg_count == 1


@pytest.mark.asyncio
async def test_analyze_js_sample(analyzer: ASTAnalyzer) -> None:
    """Extract metrics correctly from a javascript file."""
    file_path = SAMPLE_DIR / "sample.js"
    content = file_path.read_text("utf-8")

    summary = await analyzer.analyze("sample.js", content)

    assert summary is not None
    assert summary.language == "javascript"
    assert "Greeter" in summary.classes

    func_names = [f.name for f in summary.functions]
    assert "constructor" in func_names
    assert "simpleGreet" in func_names
    assert "complexGreet" in func_names

    complex_func = next(f for f in summary.functions if f.name == "complexGreet")
    assert complex_func.cyclomatic_complexity > 3


@pytest.mark.asyncio
async def test_analyze_ts_sample(analyzer: ASTAnalyzer) -> None:
    """Extract metrics correctly from a typescript file."""
    file_path = SAMPLE_DIR / "sample.ts"
    content = file_path.read_text("utf-8")

    summary = await analyzer.analyze("sample.ts", content)

    assert summary is not None
    assert summary.language == "typescript"

    assert "UserManager" in summary.classes
    assert "User" not in summary.classes

    func_names = [f.name for f in summary.functions]
    assert "processUser" in func_names
    assert "complexProcess" in func_names

    process_func = next(f for f in summary.functions if f.name == "processUser")
    assert process_func.arg_count == 2

    complex_func = next(f for f in summary.functions if f.name == "complexProcess")
    assert complex_func.cyclomatic_complexity > 3


@pytest.mark.asyncio
async def test_analyze_unknown_returns_none(analyzer: ASTAnalyzer) -> None:
    """Return None for unknown language extensions."""
    summary = await analyzer.analyze("main.rs", "fn main() {}")
    assert summary is None
