"""Tests for CodeChunker service."""

from unittest.mock import AsyncMock

import pytest

from app.models.ast_summary import ASTSummary, FunctionMetrics
from app.services.code_chunker import CodeChunker

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_analyzer() -> AsyncMock:
    """Mock ASTAnalyzer."""
    analyzer = AsyncMock()
    # default mock summary
    analyzer.analyze.return_value = ASTSummary(
        file_path="test.py",
        language="python",
        total_lines=10,
        functions=[
            FunctionMetrics(
                name="test_func",
                start_line=2,
                end_line=5,
                line_count=4,
                arg_count=1,
                cyclomatic_complexity=1
            )
        ],
        classes=[],
        imports=[]
    )
    return analyzer


async def test_chunk_file_skips_large(mock_analyzer: AsyncMock) -> None:
    chunker = CodeChunker(mock_analyzer)
    content = "\n" * 501
    chunks = await chunker.chunk_file("test.py", content, "owner/repo")
    assert chunks == []
    mock_analyzer.analyze.assert_not_called()


async def test_chunk_file_skips_ignored_exts(mock_analyzer: AsyncMock) -> None:
    chunker = CodeChunker(mock_analyzer)
    content = "a = 1"
    chunks = await chunker.chunk_file("test.min.js", content, "owner/repo")
    assert chunks == []


async def test_chunk_file_skips_ignored_dirs(mock_analyzer: AsyncMock) -> None:
    chunker = CodeChunker(mock_analyzer)
    content = "a = 1"
    chunks = await chunker.chunk_file("node_modules/test.js", content, "owner/repo")
    assert chunks == []


async def test_chunk_file_unknown_language(mock_analyzer: AsyncMock) -> None:
    mock_analyzer.analyze.return_value = ASTSummary(
        file_path="Makefile",
        language="unknown",
        total_lines=2,
        functions=[],
        classes=[],
        imports=[]
    )
    chunker = CodeChunker(mock_analyzer)
    content = "all:\n\techo 'hello'"
    chunks = await chunker.chunk_file("Makefile", content, "owner/repo")
    assert len(chunks) == 1
    assert chunks[0].language == "unknown"


async def test_chunk_file_splits_functions_and_module(mock_analyzer: AsyncMock) -> None:
    chunker = CodeChunker(mock_analyzer)
    content = "import os\ndef test_func(x):\n    print(x)\n    return x\n\nprint('module')"
    chunks = await chunker.chunk_file("test.py", content, "owner/repo")

    assert len(chunks) == 2

    func_chunk = next(c for c in chunks if c.function_name == "test_func")
    module_chunk = next(c for c in chunks if c.function_name is None)

    assert "def test_func" in func_chunk.content
    assert "import os" in module_chunk.content
