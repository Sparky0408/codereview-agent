"""Tests for the POST /webhook route."""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

TEST_SECRET = "test-webhook-secret"

VALID_PR_PAYLOAD = {
    "action": "opened",
    "pull_request": {
        "number": 1,
        "head": {
            "sha": "fake-sha",
            "repo": {
                "full_name": "testuser/testrepo",
            },
        },
    },
    "installation": {
        "id": 42,
    },
}


def _sign(body: bytes) -> str:
    """Compute HMAC-SHA256 signature matching GitHub's format."""
    return "sha256=" + hmac.new(
        TEST_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_settings() -> None:
    """Inject a known webhook secret for all tests in this module."""
    mock = MagicMock()
    mock.github_webhook_secret = TEST_SECRET
    with patch("app.webhook.get_settings", return_value=mock):
        yield  # type: ignore[misc]


@pytest.fixture
def mock_auth() -> AsyncMock:
    """Mock GitHubAppAuth so no real JWT/token exchange happens."""
    auth = AsyncMock()
    auth.get_installation_token = AsyncMock(return_value="fake-token")
    with patch("app.webhook.get_app_auth", return_value=auth):
        yield auth  # type: ignore[misc]


@pytest.fixture
def mock_fetch() -> AsyncMock:
    """Mock pr_fetcher.fetch_pr_diff to return a canned file list."""
    with patch(
        "app.services.pr_fetcher.fetch_pr_diff",
        new_callable=AsyncMock,
        return_value=[("file1.py", "+hello world")],
    ) as mock:
        yield mock  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_signature_opened_pr(
    client: AsyncClient,
    mock_auth: AsyncMock,
    mock_fetch: AsyncMock,
) -> None:
    """Signed pull_request/opened → 200, pr_fetcher called with correct args."""
    body = json.dumps(VALID_PR_PAYLOAD).encode()
    response = await client.post(
        "/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": _sign(body),
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "queued", "files": 1}
    mock_fetch.assert_awaited_once_with("testuser/testrepo", 1, "fake-token")


@pytest.mark.asyncio
async def test_invalid_signature(client: AsyncClient) -> None:
    """Tampered signature → 401."""
    body = json.dumps(VALID_PR_PAYLOAD).encode()
    response = await client.post(
        "/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": "sha256=bad",
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_non_pr_event(
    client: AsyncClient,
    mock_fetch: AsyncMock,
) -> None:
    """X-GitHub-Event=push → 200 skipped, pr_fetcher NOT called."""
    body = b'{"action":"completed"}'
    response = await client.post(
        "/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": _sign(body),
            "X-GitHub-Event": "push",
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"skipped": "event"}
    mock_fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_action_closed(
    client: AsyncClient,
    mock_fetch: AsyncMock,
) -> None:
    """action=closed → 200 skipped, pr_fetcher NOT called."""
    payload = {**VALID_PR_PAYLOAD, "action": "closed"}
    body = json.dumps(payload).encode()
    response = await client.post(
        "/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": _sign(body),
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"skipped": "action"}
    mock_fetch.assert_not_awaited()
