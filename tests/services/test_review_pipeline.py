"""Tests for the ReviewPipeline orchestrator."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from github.GithubException import UnknownObjectException

from app.models.ast_summary import ASTSummary
from app.models.review import ReviewOutput
from app.services.review_pipeline import ReviewPipeline


@pytest.fixture
def mock_analyzer() -> AsyncMock:
    """Mock AST analyzer."""
    analyzer = AsyncMock()
    analyzer.analyze.return_value = ASTSummary(
        file_path="test.py",
        language="python",
        total_lines=10,
        functions=[],
        classes=[],
        imports=[],
    )
    return analyzer


@pytest.fixture
def mock_reviewer() -> AsyncMock:
    """Mock Gemini reviewer."""
    reviewer = AsyncMock()
    reviewer.review.return_value = ReviewOutput(
        summary="Test review",
        comments=[],
    )
    return reviewer


@pytest.fixture
def mock_poster() -> AsyncMock:
    """Mock GitHub poster."""
    poster = AsyncMock()
    return poster


@pytest.mark.asyncio
@patch("app.services.review_pipeline.Github")
async def test_pipeline_happy_path(
    mock_github_class: MagicMock,
    mock_analyzer: AsyncMock,
    mock_reviewer: AsyncMock,
    mock_poster: AsyncMock,
) -> None:
    """Test full pipeline runs successfully."""
    mock_github = mock_github_class.return_value
    mock_repo = mock_github.get_repo.return_value
    mock_content = MagicMock()
    mock_content.decoded_content.decode.return_value = "print('hello')"
    # To avoid returning a list (which indicates a directory)
    mock_repo.get_contents.return_value = mock_content

    pipeline = ReviewPipeline(mock_analyzer, mock_reviewer, mock_poster)

    pr_files = [("main.py", "+print('hello')")]

    await pipeline.run("owner/repo", 1, "token", pr_files, "sha")

    # Analyzer called
    mock_analyzer.analyze.assert_called_once_with("main.py", "print('hello')")

    # Reviewer called
    mock_reviewer.review.assert_called_once()

    # Poster called
    mock_poster.post_review.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.review_pipeline.Github")
async def test_pipeline_swallows_reviewer_exception(
    mock_github_class: MagicMock,
    mock_analyzer: AsyncMock,
    mock_reviewer: AsyncMock,
    mock_poster: AsyncMock,
) -> None:
    """Test pipeline catches exceptions and doesn't crash."""
    mock_github = mock_github_class.return_value
    mock_repo = mock_github.get_repo.return_value
    mock_content = MagicMock()
    mock_content.decoded_content.decode.return_value = "content"
    mock_repo.get_contents.return_value = mock_content

    mock_reviewer.review.side_effect = Exception("API Error")

    pipeline = ReviewPipeline(mock_analyzer, mock_reviewer, mock_poster)

    # Should not raise
    await pipeline.run("owner/repo", 1, "token", [("main.py", "patch")], "sha")

    mock_poster.post_review.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.review_pipeline.Github")
async def test_pipeline_skips_unsupported_file(
    mock_github_class: MagicMock,
    mock_analyzer: AsyncMock,
    mock_reviewer: AsyncMock,
    mock_poster: AsyncMock,
) -> None:
    """Test pipeline skips file if analyzer returns None."""
    mock_github = mock_github_class.return_value
    mock_repo = mock_github.get_repo.return_value
    mock_content = MagicMock()
    mock_content.decoded_content.decode.return_value = "content"
    mock_repo.get_contents.return_value = mock_content

    mock_analyzer.analyze.return_value = None

    pipeline = ReviewPipeline(mock_analyzer, mock_reviewer, mock_poster)

    await pipeline.run("owner/repo", 1, "token", [("unknown.txt", "patch")], "sha")

    # Reviewer still called, but with empty AST summaries
    mock_reviewer.review.assert_called_once_with([("unknown.txt", "patch")], [])


@pytest.mark.asyncio
@patch("app.services.review_pipeline.Github")
async def test_pipeline_handles_github_fetch_error(
    mock_github_class: MagicMock,
    mock_analyzer: AsyncMock,
    mock_reviewer: AsyncMock,
    mock_poster: AsyncMock,
) -> None:
    """Test pipeline continues if GitHub fetch fails."""
    mock_github = mock_github_class.return_value
    mock_repo = mock_github.get_repo.return_value
    mock_repo.get_contents.side_effect = UnknownObjectException(404, "Not Found", {})

    pipeline = ReviewPipeline(mock_analyzer, mock_reviewer, mock_poster)

    await pipeline.run("owner/repo", 1, "token", [("deleted.py", "patch")], "sha")

    mock_analyzer.analyze.assert_not_called()
    mock_reviewer.review.assert_called_once_with([("deleted.py", "patch")], [])
