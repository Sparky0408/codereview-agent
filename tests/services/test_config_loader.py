from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from github.GithubException import GithubException, UnknownObjectException

from app.models.repo_config import RepoConfig
from app.services.config_loader import ConfigLoader
from app.services.review_pipeline import ReviewPipeline

pytestmark = pytest.mark.asyncio


@pytest.fixture
def loader() -> ConfigLoader:
    return ConfigLoader()


@patch("app.services.config_loader.Github")
async def test_load_valid_config(mock_github: MagicMock, loader: ConfigLoader) -> None:
    mock_repo = MagicMock()
    mock_file = MagicMock()
    mock_file.decoded_content = b"""
enabled: false
ignore_paths:
  - "*.md"
languages:
  - "python"
review_rules:
  max_function_lines: 20
"""
    mock_repo.get_contents.return_value = mock_file
    mock_github.return_value.get_repo.return_value = mock_repo

    config = await loader.load_config("owner/repo", "token", "sha")
    assert config.enabled is False
    assert config.ignore_paths == ["*.md"]
    assert config.languages == ["python"]
    assert config.review_rules.max_function_lines == 20


@patch("app.services.config_loader.Github")
async def test_load_minimal_config(mock_github: MagicMock, loader: ConfigLoader) -> None:
    mock_repo = MagicMock()
    mock_file = MagicMock()
    mock_file.decoded_content = b"review_rules:\n  max_function_lines: 10\n"
    mock_repo.get_contents.return_value = mock_file
    mock_github.return_value.get_repo.return_value = mock_repo

    config = await loader.load_config("owner/repo", "token", "sha")
    assert config.enabled is True
    assert config.review_rules.max_function_lines == 10
    assert config.review_rules.max_cyclomatic_complexity == 10


@patch("app.services.config_loader.Github")
async def test_file_not_found_returns_defaults(
    mock_github: MagicMock, loader: ConfigLoader
) -> None:
    mock_repo = MagicMock()
    mock_repo.get_contents.side_effect = UnknownObjectException(status=404, data="Not Found")
    mock_github.return_value.get_repo.return_value = mock_repo

    config = await loader.load_config("owner/repo", "token", "sha")
    assert config.enabled is True
    assert config.review_rules.max_function_lines == 50


@patch("app.services.config_loader.Github")
async def test_api_404_returns_defaults(mock_github: MagicMock, loader: ConfigLoader) -> None:
    mock_repo = MagicMock()
    mock_repo.get_contents.side_effect = GithubException(status=404, data="Not Found")
    mock_github.return_value.get_repo.return_value = mock_repo

    config = await loader.load_config("owner/repo", "token", "sha")
    assert config.enabled is True


@patch("app.services.config_loader.Github")
async def test_malformed_yaml_returns_defaults(
    mock_github: MagicMock, loader: ConfigLoader
) -> None:
    mock_repo = MagicMock()
    mock_file = MagicMock()
    mock_file.decoded_content = b":::invalid"
    mock_repo.get_contents.return_value = mock_file
    mock_github.return_value.get_repo.return_value = mock_repo

    config = await loader.load_config("owner/repo", "token", "sha")
    assert config.enabled is True
    assert config.review_rules.max_function_lines == 50


@pytest.fixture
def mock_analyzer() -> AsyncMock:
    analyzer = AsyncMock()
    return analyzer


@pytest.fixture
def mock_reviewer() -> AsyncMock:
    reviewer = AsyncMock()
    return reviewer


@pytest.fixture
def mock_poster() -> AsyncMock:
    return AsyncMock()


@patch("app.services.review_pipeline.ConfigLoader")
async def test_ignore_paths_filtering(
    mock_loader_class: MagicMock,
    mock_analyzer: AsyncMock,
    mock_reviewer: AsyncMock,
    mock_poster: AsyncMock,
) -> None:
    mock_config = RepoConfig(ignore_paths=["*.md"], languages=["python"])
    mock_loader = MagicMock()
    mock_loader.load_config = AsyncMock(return_value=mock_config)
    mock_loader_class.return_value = mock_loader

    pipeline = ReviewPipeline(mock_analyzer, mock_reviewer, mock_poster, mock_loader_class())

    pr_files = [("README.md", "patch"), ("app/main.py", "patch"), ("test.js", "patch")]

    # Patch the fetch to always return a mock string
    with patch("app.services.review_pipeline.Github") as mock_github:
        file_mock = MagicMock()
        file_mock.decoded_content = b"content"
        repo_mock = MagicMock()
        repo_mock.get_contents.return_value = file_mock
        mock_github.return_value.get_repo.return_value = repo_mock

        # Run pipeline
        # Avoid the actual review to speed things up
        mock_reviewer.review.return_value = MagicMock(comments=[])
        mock_analyzer.analyze.return_value = MagicMock()

        await pipeline.run("owner/repo", 1, "token", pr_files, "sha")

    mock_reviewer.review.assert_called_once_with(
        [("app/main.py", "patch")],
        [mock_analyzer.analyze.return_value],
        review_rules=ANY,
    )
    filtered_pr_files = mock_reviewer.review.call_args[0][0]
    assert len(filtered_pr_files) == 1
    assert filtered_pr_files[0][0] == "app/main.py"


@patch("app.services.review_pipeline.ConfigLoader")
async def test_disabled_config_skips_review(
    mock_loader_class: MagicMock,
    mock_analyzer: AsyncMock,
    mock_reviewer: AsyncMock,
    mock_poster: AsyncMock,
) -> None:
    mock_config = RepoConfig(enabled=False)
    mock_loader = MagicMock()
    mock_loader.load_config = AsyncMock(return_value=mock_config)
    mock_loader_class.return_value = mock_loader

    pipeline = ReviewPipeline(mock_analyzer, mock_reviewer, mock_poster, mock_loader_class())

    await pipeline.run("owner/repo", 1, "token", [("app/main.py", "patch")], "sha")

    mock_reviewer.review.assert_not_called()
