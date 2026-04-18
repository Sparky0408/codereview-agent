"""Tests for the GitHubPoster service."""

from unittest.mock import MagicMock, patch

import pytest

from app.models.review import ReviewComment, ReviewOutput, Severity
from app.services.github_poster import GitHubPoster


@pytest.mark.asyncio
@patch("app.services.github_poster.Github")
async def test_post_review_with_comments(mock_github_class: MagicMock) -> None:
    """Test posting a review with inline comments."""
    mock_github = mock_github_class.return_value
    mock_repo = mock_github.get_repo.return_value
    mock_pr = mock_repo.get_pull.return_value

    poster = GitHubPoster()
    review = ReviewOutput(
        summary="Found some issues.",
        comments=[
            ReviewComment(
                file_path="main.py",
                line=10,
                severity=Severity.CRITICAL,
                comment="Fix this bug.",
                suggested_code="return True",
            ),
            ReviewComment(
                file_path="utils.py",
                line=20,
                severity=Severity.NITPICK,
                comment="Rename variable.",
                suggested_code=None,
            ),
        ],
    )

    await poster.post_review("owner/repo", 123, "fake_token", review)

    mock_github_class.assert_called_once()
    mock_github.get_repo.assert_called_once_with("owner/repo")
    mock_repo.get_pull.assert_called_once_with(123)

    mock_pr.create_review.assert_called_once()
    kwargs = mock_pr.create_review.call_args.kwargs
    assert kwargs["body"] == "Found some issues."
    assert kwargs["event"] == "COMMENT"

    comments = kwargs["comments"]
    assert len(comments) == 2

    # First comment has suggestion
    assert comments[0]["path"] == "main.py"
    assert comments[0]["line"] == 10
    assert comments[0]["side"] == "RIGHT"
    assert "**[CRITICAL]** Fix this bug." in comments[0]["body"]
    assert "```suggestion\nreturn True\n```" in comments[0]["body"]

    # Second comment has no suggestion
    assert comments[1]["path"] == "utils.py"
    assert comments[1]["line"] == 20
    assert "**[NITPICK]** Rename variable." in comments[1]["body"]
    assert "```suggestion" not in comments[1]["body"]


@pytest.mark.asyncio
@patch("app.services.github_poster.Github")
async def test_post_review_empty_comments(mock_github_class: MagicMock) -> None:
    """Test that an empty review posts a regular issue comment."""
    mock_github = mock_github_class.return_value
    mock_repo = mock_github.get_repo.return_value
    mock_pr = mock_repo.get_pull.return_value

    poster = GitHubPoster()
    review = ReviewOutput(summary="Looked good.", comments=[])

    await poster.post_review("owner/repo", 123, "fake_token", review)

    mock_pr.create_issue_comment.assert_called_once_with(
        "No issues found by CodeReview Agent."
    )
    mock_pr.create_review.assert_not_called()
