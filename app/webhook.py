"""Webhook route for receiving GitHub pull_request events.

Verifies HMAC-SHA256 signature, parses the payload, fetches the PR diff,
and logs file count + patch size.
"""

import asyncio
import hashlib
import hmac
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.config import get_settings
from app.github_auth import get_app_auth
from app.models.webhook_payloads import PullRequestWebhook
from app.services import pr_fetcher
from app.services.ast_analyzer import ASTAnalyzer
from app.services.github_poster import GitHubPoster
from app.services.review_pipeline import ReviewPipeline
from app.services.reviewer import get_reviewer

logger = logging.getLogger(__name__)

router = APIRouter()

_ALLOWED_ACTIONS = frozenset({"opened", "synchronize"})
_webhook_tasks: set[asyncio.Task[Any]] = set()




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
    head_sha = payload.pull_request.head.sha

    total_patch_chars = sum(len(patch) for _, patch in files)
    logger.info(
        "PR #%d in %s: %d files, %d chars",
        pr_number,
        repo,
        len(files),
        total_patch_chars,
    )

    # TODO(W3): move to ARQ job queue

    pipeline = ReviewPipeline(
        ast_analyzer=ASTAnalyzer(),
        reviewer=get_reviewer(),
        poster=GitHubPoster(),
    )

    task = asyncio.create_task(
        pipeline.run(
            repo_full_name=repo,
            pr_number=pr_number,
            installation_token=token,
            pr_files=files,
            head_sha=head_sha,
        )
    )
    _webhook_tasks.add(task)
    task.add_done_callback(_webhook_tasks.discard)

    return {"status": "queued", "files": len(files)}
