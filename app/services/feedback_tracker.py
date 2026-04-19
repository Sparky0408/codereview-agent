"""Feedback tracker for code review comments."""

import datetime
from typing import Any

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotComment, Feedback
from app.models.review import ReviewComment


class FeedbackTracker:
    """Service to track bot comments and their reactions."""

    async def record_bot_comment(
        self,
        session: AsyncSession,
        comment: ReviewComment,
        github_comment_id: int,
        repo: str,
        pr_number: int,
    ) -> None:
        """Record a newly posted bot comment."""
        db_comment = BotComment(
            github_comment_id=github_comment_id,
            repo_full_name=repo,
            pr_number=pr_number,
            file_path=comment.file_path,
            line=comment.line,
            severity=comment.severity.value,
            comment_text=comment.comment,
            posted_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(db_comment)
        await session.commit()

    async def record_feedback(
        self,
        session: AsyncSession,
        github_comment_id: int,
        reaction_type: str,
        user_login: str,
    ) -> None:
        """Record a user's reaction to a bot comment."""
        stmt = select(BotComment).where(BotComment.github_comment_id == github_comment_id)
        result = await session.execute(stmt)
        bot_comment = result.scalar_one_or_none()

        if not bot_comment:
            return  # Not our comment or not found

        feedback = Feedback(
            bot_comment_id=bot_comment.id,
            reaction_type=reaction_type,
            user_login=user_login,
            reacted_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(feedback)
        await session.commit()

    async def get_acceptance_rate_by_severity(self, session: AsyncSession) -> dict[str, float]:
        """Calculate the acceptance rate per severity."""
        stmt = (
            select(
                BotComment.severity,
                func.count(Feedback.id).label("total_feedback"),
                func.sum(
                    cast(Feedback.reaction_type == "thumbs_up", Integer)
                ).label("thumbs_up_count")
            )
            .join(Feedback, Feedback.bot_comment_id == BotComment.id)
            .group_by(BotComment.severity)
        )
        result = await session.execute(stmt)

        rates = {}
        for severity, total, thumbs_up in result:
            if total > 0:
                rates[severity] = float(thumbs_up) / float(total)
            else:
                rates[severity] = 0.0

        return rates

    async def get_per_repo_stats(
        self, session: AsyncSession, repo_full_name: str,
    ) -> dict[str, Any]:
        """Get comment counts and acceptance rates for a specific repo."""
        stmt = (
            select(
                func.count(BotComment.id).label("total_comments"),
                func.count(Feedback.id).label("total_feedback"),
                func.sum(
                    cast(Feedback.reaction_type == "thumbs_up", Integer)
                ).label("thumbs_up_count")
            )
            .outerjoin(Feedback, Feedback.bot_comment_id == BotComment.id)
            .where(BotComment.repo_full_name == repo_full_name)
        )
        result = await session.execute(stmt)
        row = result.first()
        if not row:
            return {"total_comments": 0, "acceptance_rate": 0.0}

        total_comments, total_feedback, thumbs_up_count = row
        rate = 0.0
        if total_feedback and thumbs_up_count is not None and total_feedback > 0:
            rate = float(thumbs_up_count) / float(total_feedback)

        return {
            "total_comments": total_comments or 0,
            "acceptance_rate": rate,
        }
