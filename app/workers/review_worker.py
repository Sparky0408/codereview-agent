"""Worker background tasks for CodeReview Agent."""

import logging
from typing import Any

from app.config import get_settings
from app.services.ast_analyzer import ASTAnalyzer
from app.services.context_retriever import ContextRetriever
from app.services.github_poster import GitHubPoster
from app.services.repo_indexer import RepoIndexer
from app.services.review_pipeline import ReviewPipeline
from app.services.reviewer import get_reviewer

logger = logging.getLogger(__name__)


async def run_review_job(
    ctx: dict[str, Any],
    repo_full_name: str,
    pr_number: int,
    installation_token: str,
    pr_files: list[tuple[str, str]],
    head_sha: str,
) -> None:
    """Run the code review pipeline as a background job."""
    settings = get_settings()

    # The prompt explicitly asks to initialize from config.
    # While chroma_persist_dir may not be formally typed in Settings,
    # we can try pulling it or default to a safe standard.
    chroma_dir = getattr(settings, "chroma_persist_dir", "./chroma_db")

    indexer = RepoIndexer(chroma_persist_dir=chroma_dir)
    retriever = ContextRetriever(chroma_persist_dir=chroma_dir)

    pipeline = ReviewPipeline(
        ast_analyzer=ASTAnalyzer(),
        reviewer=get_reviewer(),
        poster=GitHubPoster(),
        indexer=indexer,
        retriever=retriever,
    )

    await pipeline.run(
        repo_full_name=repo_full_name,
        pr_number=pr_number,
        installation_token=installation_token,
        pr_files=pr_files,
        head_sha=head_sha,
    )
