"""Webhook route for receiving GitHub pull_request events.

Verifies HMAC-SHA256 signature, parses the payload, fetches the PR diff,
and logs file count + patch size.
"""

import hashlib
import hmac
import logging

from fastapi import APIRouter, HTTPException, Request

from app.config import get_settings
from app.github_auth import get_app_auth
from app.models.webhook_payloads import PullRequestWebhook
from app.services import pr_fetcher

logger = logging.getLogger(__name__)

router = APIRouter()

_ALLOWED_ACTIONS = frozenset({"opened", "synchronize"})


def _verify_signature(body: bytes, signature: str | None, secret: str) -> None:
    """Verify HMAC-SHA256 signature from GitHub webhook.

    Args:
        body: Raw request body bytes.
        signature: Value of X-Hub-Signature-256 header.
        secret: Webhook secret from configuration.

    Raises:
        HTTPException: 401 if signature is missing or invalid.
    """
    if not signature:
        raise HTTPException(status_code=401, detail="Missing signature")
    expected = "sha256=" + hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")


@router.post("/webhook")
async def webhook(request: Request) -> dict[str, str | int]:
    """Receive and process GitHub webhook events.

    Verifies signature, parses pull_request events, fetches the diff,
    and logs the result.
    """
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    settings = get_settings()

    _verify_signature(body, signature, settings.github_webhook_secret)

    # Check event type
    event = request.headers.get("X-GitHub-Event", "")
    if event != "pull_request":
        return {"skipped": "event"}

    # Parse and validate payload
    payload = PullRequestWebhook.model_validate_json(body)

    if payload.action not in _ALLOWED_ACTIONS:
        return {"skipped": "action"}

    # Fetch installation token and PR diff
    auth = get_app_auth()
    token = await auth.get_installation_token(payload.installation.id)

    repo = payload.pull_request.head.repo.full_name
    pr_number = payload.pull_request.number

    files = await pr_fetcher.fetch_pr_diff(repo, pr_number, token)

    total_patch_chars = sum(len(patch) for _, patch in files)
    logger.info(
        "PR #%d in %s: %d files, %d chars",
        pr_number,
        repo,
        len(files),
        total_patch_chars,
    )

    return {"status": "queued", "files": len(files)}
