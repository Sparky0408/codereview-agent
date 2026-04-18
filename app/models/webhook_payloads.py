"""Pydantic v2 models for GitHub webhook payloads.

Only the subset of fields we actually use are modelled here.
"""

from pydantic import BaseModel


class HeadRepo(BaseModel):
    """Repository info from the head ref of a pull request."""

    full_name: str


class Head(BaseModel):
    """Head ref of a pull request."""

    repo: HeadRepo


class PullRequestInfo(BaseModel):
    """Subset of pull_request object we need from the webhook payload."""

    number: int
    head: Head


class Installation(BaseModel):
    """GitHub App installation that triggered the event."""

    id: int


class PullRequestWebhook(BaseModel):
    """Top-level payload for a pull_request webhook event."""

    action: str
    pull_request: PullRequestInfo
    installation: Installation
