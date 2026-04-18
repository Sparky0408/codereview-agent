"""Orchestrates the entire code review pipeline."""

import asyncio
import logging

from github import Auth, Github
from github.GithubException import UnknownObjectException

from app.models.ast_summary import ASTSummary
from app.services.ast_analyzer import ASTAnalyzer
from app.services.github_poster import GitHubPoster
from app.services.reviewer import Reviewer

logger = logging.getLogger(__name__)


class ReviewPipeline:
    """Pipeline tying together fetching, AST analysis, review generation, and posting."""

    def __init__(
        self,
        ast_analyzer: ASTAnalyzer,
        reviewer: Reviewer,
        poster: GitHubPoster,
    ) -> None:
        """Initialise the pipeline with its required services.

        Args:
            ast_analyzer: Service to extract AST metrics.
            reviewer: Service to generate LLM reviews.
            poster: Service to post comments to GitHub.
        """
        self.ast_analyzer = ast_analyzer
        self.reviewer = reviewer
        self.poster = poster

    async def run(
        self,
        repo_full_name: str,
        pr_number: int,
        installation_token: str,
        pr_files: list[tuple[str, str]],
        head_sha: str,
    ) -> None:
        """Run the full review pipeline.

        Catches all exceptions to prevent crashing the webhook or worker.

        Args:
            repo_full_name: Repository owner/name.
            pr_number: PR number.
            installation_token: Access token for GitHub API.
            pr_files: List of (filename, patch) tuples.
            head_sha: Commit SHA of the PR head to fetch file contents from.
        """
        try:
            logger.info("Starting pipeline for PR #%d in %s", pr_number, repo_full_name)

            # Stage 1: AST Analysis
            logger.info("Stage: AST Analysis started")
            ast_summaries: list[ASTSummary] = []

            def _fetch_content(filename: str) -> str | None:
                try:
                    g = Github(auth=Auth.Token(installation_token))
                    repo = g.get_repo(repo_full_name)
                    content_file = repo.get_contents(filename, ref=head_sha)
                    if isinstance(content_file, list):
                        return None
                    return content_file.decoded_content.decode("utf-8")
                except UnknownObjectException:
                    logger.warning("File %s not found at %s", filename, head_sha)
                    return None
                except Exception as e:
                    logger.warning("Failed to fetch %s: %s", filename, e)
                    return None

            for filename, _ in pr_files:
                content = await asyncio.to_thread(_fetch_content, filename)
                if content is not None:
                    summary = await self.ast_analyzer.analyze(filename, content)
                    if summary:
                        ast_summaries.append(summary)

            logger.info(
                "Stage: AST Analysis completed. Extracted %d summaries.",
                len(ast_summaries),
            )

            # Stage 2: Review Generation
            logger.info("Stage: Review Generation started")
            review = await self.reviewer.review(pr_files, ast_summaries)
            logger.info(
                "Stage: Review Generation completed. Generated %d comments.",
                len(review.comments),
            )

            # Stage 3: GitHub Posting
            logger.info("Stage: GitHub Posting started")
            await self.poster.post_review(
                repo_full_name=repo_full_name,
                pr_number=pr_number,
                installation_token=installation_token,
                review=review,
            )
            logger.info("Stage: GitHub Posting completed")

            logger.info(
                "Pipeline completed successfully for PR #%d in %s",
                pr_number,
                repo_full_name,
            )

        except Exception as e:
            logger.exception(
                "Pipeline failed for PR #%d in %s: %s",
                pr_number,
                repo_full_name,
                e,
            )
