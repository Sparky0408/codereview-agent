"""Tests for feedback loops and reactions."""

import hashlib
import hmac
import json
from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Base, BotComment, Feedback
from app.models.review import ReviewComment, Severity
from app.services.feedback_tracker import FeedbackTracker


@pytest.fixture
async def setup_db() -> AsyncGenerator[None, None]:
    """Test database setup that drops and creates tables."""
    from app.db.session import engine as app_engine

    async with app_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with app_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await app_engine.dispose()


@pytest.fixture
async def db_session(setup_db: None) -> AsyncGenerator[AsyncSession, None]:
    """Test database session."""
    from app.db.session import async_session

    async with async_session() as session:
        yield session


@pytest.mark.asyncio
async def test_record_bot_comment_persists(db_session: AsyncSession) -> None:
    tracker = FeedbackTracker()
    rc = ReviewComment(
        file_path="foo.py",
        line=10,
        severity=Severity.CRITICAL,
        comment="test comment",
    )
    await tracker.record_bot_comment(db_session, rc, 1234, "repo/name", 1)

    result = await db_session.execute(
        select(BotComment).where(BotComment.github_comment_id == 1234)
    )
    bc = result.scalar_one_or_none()
    assert bc is not None
    assert bc.repo_full_name == "repo/name"
    assert bc.pr_number == 1
    assert bc.file_path == "foo.py"
    assert bc.line == 10
    assert bc.severity == "CRITICAL"
    assert bc.comment_text == "test comment"


@pytest.mark.asyncio
async def test_record_feedback_links_to_comment(db_session: AsyncSession) -> None:
    tracker = FeedbackTracker()
    rc = ReviewComment(
        file_path="foo.py",
        line=10,
        severity=Severity.SUGGESTION,
        comment="test",
    )
    await tracker.record_bot_comment(db_session, rc, 5678, "repo/test", 2)

    await tracker.record_feedback(db_session, 5678, "thumbs_up", "userxyz")

    result = await db_session.execute(
        select(Feedback)
        .join(BotComment)
        .where(BotComment.github_comment_id == 5678)
    )
    fb = result.scalar_one_or_none()
    assert fb is not None
    assert fb.reaction_type == "thumbs_up"
    assert fb.user_login == "userxyz"
    assert fb.bot_comment_id is not None


@pytest.mark.asyncio
async def test_get_acceptance_rate_by_severity(db_session: AsyncSession) -> None:
    tracker = FeedbackTracker()
    # Insert 10 comments: 5 CRITICAL, 5 SUGGESTION
    for i in range(5):
        rc = ReviewComment(
            file_path="foo.py",
            line=i,
            severity=Severity.CRITICAL,
            comment="c",
        )
        await tracker.record_bot_comment(db_session, rc, 100 + i, "rep", 1)
        await tracker.record_feedback(
            db_session, 100 + i, "thumbs_up" if i < 4 else "thumbs_down", "u"
        )

    for i in range(5):
        rc = ReviewComment(
            file_path="foo.py",
            line=i + 5,
            severity=Severity.SUGGESTION,
            comment="s",
        )
        await tracker.record_bot_comment(db_session, rc, 200 + i, "rep", 1)
        await tracker.record_feedback(
            db_session, 200 + i, "thumbs_up" if i < 1 else "thumbs_down", "u"
        )

    rates = await tracker.get_acceptance_rate_by_severity(db_session)
    assert rates["CRITICAL"] == 0.8  # 4/5
    assert rates["SUGGESTION"] == 0.2  # 1/5


@pytest.mark.asyncio
async def test_webhook_reaction_on_bot_comment(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tracker = FeedbackTracker()
    rc = ReviewComment(
        file_path="a.py", line=1, severity=Severity.NITPICK, comment="nit"
    )
    await tracker.record_bot_comment(db_session, rc, 9999, "r/n", 1)

    payload = {
        "action": "created",
        "comment": {"id": 9999},
        "reaction": {"content": "+1", "user": {"login": "testuser"}},
    }

    settings = get_settings()
    body_bytes = json.dumps(payload).encode()
    signature = (
        "sha256="
        + hmac.new(
            settings.github_webhook_secret.encode(), body_bytes, hashlib.sha256
        ).hexdigest()
    )

    response = await client.post(
        "/webhook",
        content=body_bytes,
        headers={
            "X-Hub-Signature-256": signature,
            "X-GitHub-Event": "pull_request_review_comment",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"status": "feedback_recorded"}

    fb = (
        await db_session.execute(
            select(Feedback)
            .join(BotComment)
            .where(BotComment.github_comment_id == 9999)
        )
    ).scalar_one_or_none()
    assert fb is not None
    assert fb.reaction_type == "thumbs_up"


@pytest.mark.asyncio
async def test_webhook_reaction_on_non_bot_comment(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    payload = {
        "action": "created",
        "comment": {"id": 8888},
        "reaction": {"content": "-1", "user": {"login": "testuser"}},
    }
    settings = get_settings()
    body_bytes = json.dumps(payload).encode()
    signature = (
        "sha256="
        + hmac.new(
            settings.github_webhook_secret.encode(), body_bytes, hashlib.sha256
        ).hexdigest()
    )

    response = await client.post(
        "/webhook",
        content=body_bytes,
        headers={
            "X-Hub-Signature-256": signature,
            "X-GitHub-Event": "pull_request_review_comment",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"status": "feedback_recorded"}

    fb = (await db_session.execute(select(Feedback))).scalar_one_or_none()
    assert fb is None
