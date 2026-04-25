"""Tests for dashboard.db query functions."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dashboard import db


# ---------------------------------------------------------------------------
# Helpers — lightweight row-like objects returned by session.execute()
# ---------------------------------------------------------------------------
class _Row:
    """Mimics a SQLAlchemy Row with attribute access."""

    def __init__(self, **kwargs: object) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


def _mock_session_factory(execute_side_effects: list[MagicMock]) -> AsyncMock:
    """Build an AsyncMock session whose execute() returns successive results."""
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=execute_side_effects)
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _scalar_result(value: object) -> MagicMock:
    """Result whose .scalar() returns `value`."""
    r = MagicMock()
    r.scalar.return_value = value
    return r


def _rows_result(rows: list[_Row]) -> MagicMock:
    """Result whose .all() returns a list of rows."""
    r = MagicMock()
    r.all.return_value = rows
    return r


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestGetOverviewMetrics:
    @pytest.mark.asyncio
    async def test_returns_expected_shape(self) -> None:
        ctx = _mock_session_factory(
            [
                _scalar_result(42),   # total_prs
                _scalar_result(150),  # total_comments
                _scalar_result(5),    # unique_repos
                _scalar_result(3200.0),  # avg_review_time_ms
            ]
        )
        with patch.object(db, "_async_session", return_value=ctx):
            result = await db.get_overview_metrics()

        assert result == {
            "total_prs": 42,
            "total_comments": 150,
            "unique_repos": 5,
            "avg_review_time_ms": 3200.0,
        }

    @pytest.mark.asyncio
    async def test_handles_empty_db(self) -> None:
        ctx = _mock_session_factory(
            [
                _scalar_result(0),
                _scalar_result(0),
                _scalar_result(0),
                _scalar_result(0),
            ]
        )
        with patch.object(db, "_async_session", return_value=ctx):
            result = await db.get_overview_metrics()

        assert result["total_prs"] == 0
        assert result["total_comments"] == 0
        assert result["unique_repos"] == 0
        assert result["avg_review_time_ms"] == 0.0


class TestGetCommentsPerDay:
    @pytest.mark.asyncio
    async def test_returns_list_of_dicts(self) -> None:
        now = datetime.now(tz=UTC)
        rows = [_Row(day=now, cnt=10), _Row(day=now, cnt=5)]
        ctx = _mock_session_factory([_rows_result(rows)])
        with patch.object(db, "_async_session", return_value=ctx):
            result = await db.get_comments_per_day(30)

        assert len(result) == 2
        assert result[0]["date"] == now
        assert result[0]["count"] == 10

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        ctx = _mock_session_factory([_rows_result([])])
        with patch.object(db, "_async_session", return_value=ctx):
            result = await db.get_comments_per_day(30)

        assert result == []


class TestGetCommentsPerSeverity:
    @pytest.mark.asyncio
    async def test_returns_list(self) -> None:
        rows = [_Row(severity="CRITICAL", cnt=20), _Row(severity="NITPICK", cnt=8)]
        ctx = _mock_session_factory([_rows_result(rows)])
        with patch.object(db, "_async_session", return_value=ctx):
            result = await db.get_comments_per_severity()

        assert len(result) == 2
        assert result[0]["severity"] == "CRITICAL"
        assert result[0]["count"] == 20


class TestGetRecentPrs:
    @pytest.mark.asyncio
    async def test_returns_expected_keys(self) -> None:
        now = datetime.now(tz=UTC)
        rows = [_Row(repo_full_name="org/repo", pr_number=42, comment_count=3, latest_at=now)]
        ctx = _mock_session_factory([_rows_result(rows)])
        with patch.object(db, "_async_session", return_value=ctx):
            result = await db.get_recent_prs(10)

        assert len(result) == 1
        assert result[0]["repo"] == "org/repo"
        assert result[0]["pr_number"] == 42
        assert result[0]["comment_count"] == 3


class TestGetOverallAcceptanceRate:
    @pytest.mark.asyncio
    async def test_calculates_rate(self) -> None:
        ctx = _mock_session_factory([_scalar_result(100), _scalar_result(75)])
        with patch.object(db, "_async_session", return_value=ctx):
            result = await db.get_overall_acceptance_rate()

        assert result["total"] == 100
        assert result["thumbs_up"] == 75
        assert result["rate"] == 75.0

    @pytest.mark.asyncio
    async def test_zero_reactions(self) -> None:
        ctx = _mock_session_factory([_scalar_result(0), _scalar_result(0)])
        with patch.object(db, "_async_session", return_value=ctx):
            result = await db.get_overall_acceptance_rate()

        assert result["rate"] == 0.0


class TestGetPerSeverityAcceptance:
    @pytest.mark.asyncio
    async def test_returns_rate(self) -> None:
        rows = [_Row(severity="CRITICAL", total=10, thumbs_up=7)]
        ctx = _mock_session_factory([_rows_result(rows)])
        with patch.object(db, "_async_session", return_value=ctx):
            result = await db.get_per_severity_acceptance()

        assert len(result) == 1
        assert result[0]["severity"] == "CRITICAL"
        assert result[0]["rate"] == 70.0


class TestGetPerRepoAcceptance:
    @pytest.mark.asyncio
    async def test_returns_rate(self) -> None:
        rows = [_Row(repo_full_name="org/repo", total=20, thumbs_up=15)]
        ctx = _mock_session_factory([_rows_result(rows)])
        with patch.object(db, "_async_session", return_value=ctx):
            result = await db.get_per_repo_acceptance(10)

        assert len(result) == 1
        assert result[0]["repo"] == "org/repo"
        assert result[0]["rate"] == 75.0


class TestGetFlaggedComments:
    @pytest.mark.asyncio
    async def test_returns_expected_keys(self) -> None:
        rows = [
            _Row(
                comment_id=1,
                repo_full_name="org/repo",
                pr_number=5,
                file_path="src/main.py",
                severity="CRITICAL",
                snippet="Bad code here...",
                thumbs_down_count=3,
            )
        ]
        ctx = _mock_session_factory([_rows_result(rows)])
        with patch.object(db, "_async_session", return_value=ctx):
            result = await db.get_flagged_comments(20)

        assert len(result) == 1
        assert result[0]["comment_id"] == 1
        assert result[0]["thumbs_down_count"] == 3


class TestGetAcceptanceTrend:
    @pytest.mark.asyncio
    async def test_returns_trend(self) -> None:
        now = datetime.now(tz=UTC)
        rows = [_Row(day=now, total=10, thumbs_up=8)]
        ctx = _mock_session_factory([_rows_result(rows)])
        with patch.object(db, "_async_session", return_value=ctx):
            result = await db.get_acceptance_trend(30)

        assert len(result) == 1
        assert result[0]["rate"] == 80.0
