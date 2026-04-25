"""CLI entrypoint for the evaluation harness.

Usage:
    python -m eval.run --repo owner/name --prs 20 --output eval_report.md
"""

import argparse
import asyncio
import logging
import os
import sys
import time

from app.models.review import ReviewComment, ReviewOutput
from app.services.ast_analyzer import ASTAnalyzer
from app.services.reviewer import Reviewer
from eval.comment_matcher import MatchResult, match
from eval.historical_pr_fetcher import HistoricalPR, fetch_merged_prs
from eval.report_generator import EvalConfig, PRResult, generate

logger = logging.getLogger(__name__)


class DryRunPoster:
    """Drop-in replacement for GitHubPoster that collects comments without posting.

    This ensures evaluation never writes to GitHub.
    """

    def __init__(self) -> None:
        self.collected_comments: list[ReviewComment] = []

    async def post_review(
        self,
        repo_full_name: str,
        pr_number: int,
        installation_token: str,
        review: ReviewOutput,
        changed_lines_map: dict[str, set[int]] | None = None,
    ) -> None:
        """Collect comments after filtering them to changed lines (diff-aware).

        Args:
            repo_full_name: Repository owner/name (unused in dry run).
            pr_number: PR number (unused in dry run).
            installation_token: Token (unused in dry run).
            review: The review output to collect.
            changed_lines_map: Optional mapping of filename to changed lines.
        """
        if changed_lines_map is not None:
            original_count = len(review.comments)
            filtered = [
                c for c in review.comments
                if c.line in changed_lines_map.get(c.file_path, set())
            ]
            dropped = original_count - len(filtered)
            if dropped:
                logger.info(
                    "Filtered %d comments outside the diff, collecting %d comments",
                    dropped,
                    len(filtered),
                )
            self.collected_comments.extend(filtered)
        else:
            self.collected_comments.extend(review.comments)


async def _run_eval_for_pr(
    pr: HistoricalPR,
    repo_full_name: str,
    gemini_api_key: str,
    gemini_model: str,
    installation_token: str,
) -> PRResult:
    """Run the review pipeline on a single historical PR in dry-run mode.

    Args:
        pr: Historical PR data including changed files and human comments.
        repo_full_name: Real owner/repo for fetching file contents.
        gemini_api_key: API key for Gemini.
        gemini_model: Gemini model name to use.
        installation_token: GitHub token for file content fetching.

    Returns:
        PRResult with match result and timing.
    """
    from app.services.review_pipeline import ReviewPipeline

    poster = DryRunPoster()
    analyzer = ASTAnalyzer()
    reviewer = Reviewer(api_key=gemini_api_key, model=gemini_model)

    pipeline = ReviewPipeline(
        ast_analyzer=analyzer,
        reviewer=reviewer,
        poster=poster,  # type: ignore[arg-type]  # DryRunPoster duck-types GitHubPoster
    )

    start = time.perf_counter()

    await pipeline.run(
        repo_full_name=repo_full_name,
        pr_number=pr.number,
        installation_token=installation_token,
        pr_files=pr.changed_files,
        head_sha=pr.pre_merge_sha,
    )

    elapsed_ms = int((time.perf_counter() - start) * 1000)

    # Match bot output against human comments
    match_result: MatchResult = match(
        bot_comments=poster.collected_comments,
        human_comments=pr.human_comments,
    )

    return PRResult(
        pr_number=pr.number,
        pr_title=pr.title,
        match_result=match_result,
        elapsed_ms=elapsed_ms,
        bot_comment_count=len(poster.collected_comments),
        human_comment_count=len(pr.human_comments),
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the eval harness."""
    parser = argparse.ArgumentParser(
        description="CodeReview Agent — Evaluation Harness",
        prog="python -m eval.run",
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="Target repository (owner/name, e.g. encode/starlette)",
    )
    parser.add_argument(
        "--prs",
        type=int,
        default=20,
        help="Number of merged PRs to evaluate (default: 20)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path for the report (default: stdout)",
    )
    parser.add_argument(
        "--gemini-model",
        default="gemini-2.5-flash",
        help="Gemini model to use (default: gemini-2.5-flash to save costs)",
    )
    return parser.parse_args(argv)


async def main(argv: list[str] | None = None) -> None:
    """Main async entrypoint for the eval harness."""
    args = _parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Read tokens from environment
    pat_token = os.environ.get("GITHUB_EVAL_PAT", "")
    gemini_api_key = os.environ.get("GEMINI_API_KEY", "")

    if not pat_token:
        logger.error("GITHUB_EVAL_PAT environment variable is required")
        sys.exit(1)
    if not gemini_api_key:
        logger.error("GEMINI_API_KEY environment variable is required")
        sys.exit(1)

    logger.info("Starting eval: repo=%s, prs=%d, model=%s", args.repo, args.prs, args.gemini_model)

    # Stage 1: Fetch historical PRs
    logger.info("Fetching merged PRs with review comments from %s...", args.repo)
    historical_prs = await fetch_merged_prs(
        repo_full_name=args.repo,
        pat_token=pat_token,
        limit=args.prs,
    )

    if not historical_prs:
        logger.error(
            "No usable PRs found in %s (need PRs with line-level review comments)",
            args.repo,
        )
        sys.exit(1)

    logger.info("Found %d PRs to evaluate", len(historical_prs))

    # Stage 2: Run pipeline on each PR
    pr_results: list[PRResult] = []
    for i, pr in enumerate(historical_prs, 1):
        logger.info(
            "[%d/%d] Evaluating PR #%d: %s (%d files, %d human comments)",
            i, len(historical_prs), pr.number, pr.title,
            len(pr.changed_files), len(pr.human_comments),
        )
        result = await _run_eval_for_pr(
            pr=pr,
            repo_full_name=args.repo,
            gemini_api_key=gemini_api_key,
            gemini_model=args.gemini_model,
            installation_token=pat_token,  # PAT works for public repo content
        )
        pr_results.append(result)
        logger.info(
            "  → TP=%d FP=%d FN=%d (bot=%d, human=%d) in %dms",
            result.match_result.tp, result.match_result.fp, result.match_result.fn,
            result.bot_comment_count, result.human_comment_count,
            result.elapsed_ms,
        )

    # Stage 3: Generate report
    config = EvalConfig(
        repo=args.repo,
        pr_count=args.prs,
        gemini_model=args.gemini_model,
    )
    report = generate(repo=args.repo, pr_results=pr_results, config=config)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)
        logger.info("Report written to %s", args.output)
    else:
        sys.stdout.write(report)

    # Final summary
    total_tp = sum(r.match_result.tp for r in pr_results)
    total_fp = sum(r.match_result.fp for r in pr_results)
    total_fn = sum(r.match_result.fn for r in pr_results)
    p = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
    r = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
    f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0
    logger.info("Final: P=%.1f%% R=%.1f%% F1=%.1f%%", p * 100, r * 100, f1 * 100)


if __name__ == "__main__":
    asyncio.run(main())
