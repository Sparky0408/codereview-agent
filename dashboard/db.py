"""Read-only async SQLAlchemy queries for the dashboard.

Reuses the DB models from app/db/models.py and creates its own
engine/session factory so the dashboard process is independent.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import BotComment, Feedback

_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://codereview:codereview@localhost:5432/codereview",
)

_engine = create_async_engine(_DATABASE_URL, echo=False)
_async_session = async_sessionmaker(bind=_engine, expire_on_commit=False)


async def _get_session() -> AsyncSession:
    """Create a new async session."""
    return _async_session()


async def get_overview_metrics() -> dict[str, Any]:
    """Return top-level dashboard metrics.

    Returns:
        Dict with keys: total_prs, total_comments, unique_repos, avg_review_time_ms.
    """
    async with _async_session() as session:
        # Total unique PRs reviewed
        total_prs_q = select(
            func.count(
                func.distinct(
                    func.concat(BotComment.repo_full_name, "/", BotComment.pr_number)
                )
            )
        )
        total_prs = (await session.execute(total_prs_q)).scalar() or 0

        # Total comments posted
        total_comments_q = select(func.count(BotComment.id))
        total_comments = (await session.execute(total_comments_q)).scalar() or 0

        # Unique repos
        unique_repos_q = select(func.count(func.distinct(BotComment.repo_full_name)))
        unique_repos = (await session.execute(unique_repos_q)).scalar() or 0

        # Average review time — approximated by the spread of comment
        # timestamps within each PR (max - min posted_at per PR).
        avg_time_q = text("""
            SELECT COALESCE(
                AVG(EXTRACT(EPOCH FROM (max_ts - min_ts)) * 1000),
                0
            )
            FROM (
                SELECT repo_full_name, pr_number,
                       MIN(posted_at) AS min_ts,
                       MAX(posted_at) AS max_ts
                FROM bot_comments
                GROUP BY repo_full_name, pr_number
            ) sub
        """)
        avg_review_time_ms = (await session.execute(avg_time_q)).scalar() or 0

    return {
        "total_prs": int(total_prs),
        "total_comments": int(total_comments),
        "unique_repos": int(unique_repos),
        "avg_review_time_ms": float(avg_review_time_ms),
    }


async def get_comments_per_day(days: int = 30) -> list[dict[str, Any]]:
    """Return comment counts per day for the last N days.

    Returns:
        List of dicts with keys: date, count.
    """
    cutoff = datetime.now(tz=UTC) - timedelta(days=days)
    async with _async_session() as session:
        q = (
            select(
                func.date_trunc("day", BotComment.posted_at).label("day"),
                func.count(BotComment.id).label("cnt"),
            )
            .where(BotComment.posted_at >= cutoff)
            .group_by(text("1"))
            .order_by(text("1"))
        )
        rows = (await session.execute(q)).all()

    return [{"date": row.day, "count": row.cnt} for row in rows]


async def get_comments_per_severity() -> list[dict[str, Any]]:
    """Return comment counts grouped by severity.

    Returns:
        List of dicts with keys: severity, count.
    """
    async with _async_session() as session:
        q = (
            select(
                BotComment.severity,
                func.count(BotComment.id).label("cnt"),
            )
            .group_by(BotComment.severity)
            .order_by(func.count(BotComment.id).desc())
        )
        rows = (await session.execute(q)).all()

    return [{"severity": row.severity, "count": row.cnt} for row in rows]


async def get_recent_prs(limit: int = 10) -> list[dict[str, Any]]:
    """Return the most recently reviewed PRs.

    Returns:
        List of dicts with keys: repo, pr_number, comment_count, latest_at.
    """
    async with _async_session() as session:
        q = text("""
            SELECT repo_full_name,
                   pr_number,
                   COUNT(*) AS comment_count,
                   MAX(posted_at) AS latest_at
            FROM bot_comments
            GROUP BY repo_full_name, pr_number
            ORDER BY latest_at DESC
            LIMIT :lim
        """)
        rows = (await session.execute(q, {"lim": limit})).all()

    return [
        {
            "repo": row.repo_full_name,
            "pr_number": row.pr_number,
            "comment_count": row.comment_count,
            "latest_at": row.latest_at,
        }
        for row in rows
    ]


async def get_overall_acceptance_rate() -> dict[str, Any]:
    """Return overall acceptance rate (thumbs-up / total reactions).

    Returns:
        Dict with keys: thumbs_up, total, rate.
    """
    async with _async_session() as session:
        total_q = select(func.count(Feedback.id))
        total = (await session.execute(total_q)).scalar() or 0

        thumbs_up_q = select(func.count(Feedback.id)).where(
            Feedback.reaction_type == "+1"
        )
        thumbs_up = (await session.execute(thumbs_up_q)).scalar() or 0

    rate = (thumbs_up / total * 100) if total > 0 else 0.0
    return {"thumbs_up": int(thumbs_up), "total": int(total), "rate": float(rate)}


async def get_per_severity_acceptance() -> list[dict[str, Any]]:
    """Return acceptance rate broken down by comment severity.

    Returns:
        List of dicts with keys: severity, thumbs_up, total, rate.
    """
    async with _async_session() as session:
        q = text("""
            SELECT bc.severity,
                   COUNT(f.id) AS total,
                   COUNT(f.id) FILTER (WHERE f.reaction_type = '+1') AS thumbs_up
            FROM feedback f
            JOIN bot_comments bc ON bc.id = f.bot_comment_id
            GROUP BY bc.severity
            ORDER BY total DESC
        """)
        rows = (await session.execute(q)).all()

    return [
        {
            "severity": row.severity,
            "thumbs_up": row.thumbs_up,
            "total": row.total,
            "rate": (row.thumbs_up / row.total * 100) if row.total > 0 else 0.0,
        }
        for row in rows
    ]


async def get_per_repo_acceptance(limit: int = 10) -> list[dict[str, Any]]:
    """Return acceptance rate broken down by repo (top N by total reactions).

    Returns:
        List of dicts with keys: repo, thumbs_up, total, rate.
    """
    async with _async_session() as session:
        q = text("""
            SELECT bc.repo_full_name,
                   COUNT(f.id) AS total,
                   COUNT(f.id) FILTER (WHERE f.reaction_type = '+1') AS thumbs_up
            FROM feedback f
            JOIN bot_comments bc ON bc.id = f.bot_comment_id
            GROUP BY bc.repo_full_name
            ORDER BY total DESC
            LIMIT :lim
        """)
        rows = (await session.execute(q, {"lim": limit})).all()

    return [
        {
            "repo": row.repo_full_name,
            "thumbs_up": row.thumbs_up,
            "total": row.total,
            "rate": (row.thumbs_up / row.total * 100) if row.total > 0 else 0.0,
        }
        for row in rows
    ]


async def get_flagged_comments(limit: int = 20) -> list[dict[str, Any]]:
    """Return comments with most thumbs-down reactions (auto-mute candidates).

    Returns:
        List of dicts with keys: comment_id, repo, pr_number, file_path,
        severity, snippet, thumbs_down_count.
    """
    async with _async_session() as session:
        q = text("""
            SELECT bc.id AS comment_id,
                   bc.repo_full_name,
                   bc.pr_number,
                   bc.file_path,
                   bc.severity,
                   LEFT(bc.comment_text, 120) AS snippet,
                   COUNT(f.id) AS thumbs_down_count
            FROM feedback f
            JOIN bot_comments bc ON bc.id = f.bot_comment_id
            WHERE f.reaction_type = '-1'
            GROUP BY bc.id, bc.repo_full_name, bc.pr_number,
                     bc.file_path, bc.severity, bc.comment_text
            ORDER BY thumbs_down_count DESC
            LIMIT :lim
        """)
        rows = (await session.execute(q, {"lim": limit})).all()

    return [
        {
            "comment_id": row.comment_id,
            "repo": row.repo_full_name,
            "pr_number": row.pr_number,
            "file_path": row.file_path,
            "severity": row.severity,
            "snippet": row.snippet,
            "thumbs_down_count": row.thumbs_down_count,
        }
        for row in rows
    ]


async def get_acceptance_trend(days: int = 30) -> list[dict[str, Any]]:
    """Return daily acceptance rate for the last N days.

    Returns:
        List of dicts with keys: date, thumbs_up, total, rate.
    """
    cutoff = datetime.now(tz=UTC) - timedelta(days=days)
    async with _async_session() as session:
        q = text("""
            SELECT DATE_TRUNC('day', f.reacted_at) AS day,
                   COUNT(f.id) AS total,
                   COUNT(f.id) FILTER (WHERE f.reaction_type = '+1') AS thumbs_up
            FROM feedback f
            WHERE f.reacted_at >= :cutoff
            GROUP BY 1
            ORDER BY 1
        """)
        rows = (await session.execute(q, {"cutoff": cutoff})).all()

    return [
        {
            "date": row.day,
            "thumbs_up": row.thumbs_up,
            "total": row.total,
            "rate": (row.thumbs_up / row.total * 100) if row.total > 0 else 0.0,
        }
        for row in rows
    ]
