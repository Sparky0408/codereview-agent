"""Unit tests for the LLM Reviewer engine."""

from unittest.mock import MagicMock, patch

import pytest
from google.genai import types

from app.models.review import Severity
from app.services.reviewer import Reviewer


@pytest.fixture
def fake_reviewer() -> Reviewer:
    """Returns a Reviewer instance configured with a fake API key."""
    # Mocking out genai.Client at the class level so __init__ doesn't hit network
    with patch("app.services.reviewer.genai.Client"):
        return Reviewer(api_key="fake-key")


def test_prompts_load_on_init(fake_reviewer: Reviewer) -> None:
    """Verify that system and user prompts load correctly."""
    assert "You are a Senior Software Engineer reviewing code" in fake_reviewer._system_prompt
    assert "{ast_summaries}" in fake_reviewer._user_template
    assert "{diffs}" in fake_reviewer._user_template


@pytest.mark.asyncio
@patch("app.services.reviewer.genai.Client")
async def test_review_happy_path(mock_client_class: MagicMock) -> None:
    """Verify standard happy path returning parsed JSON comments."""
    # Setup mock chain
    mock_instance = MagicMock()
    mock_client_class.return_value = mock_instance
    mock_response = MagicMock()
    mock_response.text = (
        '{"summary": "Looks ok.", "comments": '
        '[{"file_path": "main.py", "line": 42, "severity": "NITPICK", "comment": "Nice."}]}'
    )
    mock_response.usage_metadata = types.GenerateContentResponseUsageMetadata(
        total_token_count=100, prompt_token_count=50, candidates_token_count=50
    )
    mock_instance.models.generate_content.return_value = mock_response

    reviewer = Reviewer(api_key="fake")
    output = await reviewer.review([("main.py", "+42 patch")], [])

    assert output.summary == "Looks ok."
    assert len(output.comments) == 1
    assert output.comments[0].severity == Severity.NITPICK
    assert output.comments[0].line == 42
    # Should only be called once
    mock_instance.models.generate_content.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.reviewer.genai.Client")
async def test_review_invalid_json_retries_once(mock_client_class: MagicMock) -> None:
    """Verify it retries once upon receiving bad JSON, then succeeds."""
    mock_instance = MagicMock()
    mock_client_class.return_value = mock_instance

    # First response bad, second response good
    bad_response = MagicMock(text="```json oops\nnot json")
    good_response = MagicMock(text='{"summary": "Fixed", "comments": []}')
    mock_instance.models.generate_content.side_effect = [bad_response, good_response]

    reviewer = Reviewer(api_key="fake")
    output = await reviewer.review([], [])

    assert output.summary == "Fixed"
    assert len(output.comments) == 0
    assert mock_instance.models.generate_content.call_count == 2

    # Verify the second call prompt includes the retry phrase
    second_call_args = mock_instance.models.generate_content.call_args_list[1]
    assert (
        "CRITICAL REMINDER: You MUST return strictly valid JSON"
        in second_call_args.kwargs["contents"]
    )


@pytest.mark.asyncio
@patch("app.services.reviewer.genai.Client")
async def test_review_both_fail_returns_empty(mock_client_class: MagicMock) -> None:
    """Verify it returns empty default ReviewOutput if both tries fail."""
    mock_instance = MagicMock()
    mock_client_class.return_value = mock_instance

    # Both responses are invalid JSON
    bad_response = MagicMock(text="completely bad")
    mock_instance.models.generate_content.side_effect = [bad_response, bad_response]

    reviewer = Reviewer(api_key="fake")
    output = await reviewer.review([], [])

    assert output.summary == "Review failed"
    assert len(output.comments) == 0
    assert mock_instance.models.generate_content.call_count == 2
