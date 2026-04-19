"""Posts inline code review comments to GitHub.

PyGitHub is synchronous — all calls are wrapped with asyncio.to_thread.
"""

import asyncio
import logging

from github import Auth, Github

from app.models.review import ReviewOutput

logger = logging.getLogger(__name__)


class GitHubPoster:
    """Posts review comments to a GitHub pull request."""

    async def post_review(
        self,
        repo_full_name: str,
        pr_number: int,
        installation_token: str,
        review: ReviewOutput,
    ) -> None:
        """Post a structured review to a pull request.

        Args:
            repo_full_name: Owner/repo string.
            pr_number: Pull request number.
            installation_token: GitHub App installation access token.
            review: Structured review output to post.
        """

        from typing import Any
        def _post_sync() -> list[dict[str, Any]]:
            g = Github(auth=Auth.Token(installation_token))
            repo = g.get_repo(repo_full_name)
            pr = repo.get_pull(pr_number)

            if not review.comments:
                # Post simple PR-level comment
                pr.create_issue_comment("No issues found by CodeReview Agent.")
                return []

            comments_list = []
            for c in review.comments:
                formatted_body = f"**[{c.severity.value}]** {c.comment}"
                if c.suggested_code:
                    formatted_body += f"\n\n```suggestion\n{c.suggested_code}\n```"

                comments_list.append(
                    {
                        "path": c.file_path,
                        "line": c.line,
                        "side": "RIGHT",
                        "body": formatted_body,
                    }
                )

            created_review = pr.create_review(
                body=review.summary,
                event="COMMENT",
                comments=comments_list,  # type: ignore[arg-type]  # PyGitHub typings expect internal class, but API takes dict
            )

            review_comments = [
                c for c in pr.get_review_comments()
                if c.pull_request_review_id == created_review.id
            ]

            # Extract created comments to record their IDs for reactions
            return [
                {
                    "id": c.id,
                    "path": c.path,
                    "line": c.original_line or c.line,
                    "body": c.body,
                }
                for c in review_comments
            ]

        posted_comments_data = await asyncio.to_thread(_post_sync)

        if not posted_comments_data:
            return

        from app.db.session import async_session
        from app.services.feedback_tracker import FeedbackTracker

        tracker = FeedbackTracker()
        async with async_session() as session:
            for rc in review.comments:
                expected_prefix = f"**[{rc.severity.value}]**"

                matched_id = None
                for pcd in posted_comments_data:
                    # Match by path, line, and prefix
                    if (
                        pcd["path"] == rc.file_path
                        and pcd["line"] == rc.line
                        and pcd["body"].startswith(expected_prefix)
                    ):
                        matched_id = pcd["id"]
                        break

                if matched_id:
                    await tracker.record_bot_comment(
                        session=session,
                        comment=rc,
                        github_comment_id=matched_id,
                        repo=repo_full_name,
                        pr_number=pr_number,
                    )
