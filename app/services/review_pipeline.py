"""Orchestrates the entire code review pipeline."""

import asyncio
import fnmatch
import logging

from github import Auth, Github
from github.GithubException import UnknownObjectException

from app.models.ast_summary import ASTSummary
from app.models.review_context import PRContext
from app.services.ast_analyzer import ASTAnalyzer
from app.services.config_loader import ConfigLoader
from app.services.context_retriever import ContextRetriever
from app.services.github_poster import GitHubPoster
from app.services.repo_indexer import RepoIndexer
from app.services.reviewer import Reviewer

logger = logging.getLogger(__name__)


class ReviewPipeline:
    """Pipeline tying together fetching, AST analysis, review generation, and posting."""

    def __init__(
        self,
        ast_analyzer: ASTAnalyzer,
        reviewer: Reviewer,
        poster: GitHubPoster,
        config_loader: ConfigLoader | None = None,
        indexer: RepoIndexer | None = None,
        retriever: ContextRetriever | None = None,
    ) -> None:
        """Initialise the pipeline with its required services.

        Args:
            ast_analyzer: Service to extract AST metrics.
            reviewer: Service to generate LLM reviews.
            poster: Service to post comments to GitHub.
            config_loader: Service to load repository configurations.
            indexer: Optional service to index the repository.
            retriever: Optional service to retrieve code context.
        """
        self.ast_analyzer = ast_analyzer
        self.reviewer = reviewer
        self.poster = poster
        self.config_loader = config_loader or ConfigLoader()
        self.indexer = indexer
        self.retriever = retriever

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

            # Stage 0: Configuration Check
            logger.info("Stage: Configuration Check started")
            config = await self.config_loader.load_config(
                repo_full_name, installation_token, head_sha
            )
            if not config.enabled:
                logger.info("Reviews disabled for %s. Skipping pipeline.", repo_full_name)
                return

            def _is_enabled_file(filename: str) -> bool:
                for pattern in config.ignore_paths:
                    if fnmatch.fnmatch(filename, pattern):
                        return False
                ext = filename.split(".")[-1].lower() if "." in filename else ""
                ext_map = {
                    "py": "python",
                    "js": "javascript",
                    "ts": "typescript",
                    "tsx": "typescript",
                    "jsx": "javascript",
                }
                lang = ext_map.get(ext)
                return bool(lang and lang in config.languages)

            filtered_pr_files = [
                (name, patch) for name, patch in pr_files if _is_enabled_file(name)
            ]
            if not filtered_pr_files:
                logger.info("No supported files remaining after applying config filters.")
                return

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

            for filename, _ in filtered_pr_files:
                content = await asyncio.to_thread(_fetch_content, filename)
                if content is not None:
                    summary = await self.ast_analyzer.analyze(filename, content)
                    if summary:
                        ast_summaries.append(summary)

            logger.info(
                "Stage: AST Analysis completed. Extracted %d summaries.",
                len(ast_summaries),
            )

            # Stage: RAG / Indexing
            if self.indexer:
                try:
                    logger.info("Stage: RAG Indexing started for %s", repo_full_name)
                    is_indexed = await self.indexer.is_indexed(repo_full_name)
                    if not is_indexed:
                        await self.indexer.index_repo(repo_full_name, installation_token, head_sha)
                    else:
                        changed_files = [f for f, _ in pr_files]
                        await self.indexer.incremental_update(
                            repo_full_name, changed_files, installation_token, head_sha
                        )
                    logger.info("Stage: RAG Indexing completed")
                except Exception as e:
                    logger.warning("RAG Indexing failed, skipping: %s", e)
            else:
                logger.info("No indexer provided, skipping indexing")

            pr_context: PRContext | None = None
            if self.retriever:
                try:
                    logger.info("Stage: RAG Retrieval started for %s", repo_full_name)
                    patch_by_file = {f: patch for f, patch in filtered_pr_files}
                    pr_context = await self.retriever.retrieve_context(
                        repo_full_name, patch_by_file
                    )
                    logger.info("Stage: RAG Retrieval completed")
                except Exception as e:
                    logger.warning("RAG Retrieval failed, skipping: %s", e)
            else:
                logger.info("No retriever provided, skipping retrieval")

            # Stage 2: Review Generation
            logger.info("Stage: Review Generation started")
            review = await self.reviewer.review(
                filtered_pr_files,
                ast_summaries,
                review_rules=config.review_rules,
                pr_context=pr_context,
            )
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
