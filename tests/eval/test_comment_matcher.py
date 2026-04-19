"""Tests for eval.comment_matcher."""

import json
from pathlib import Path

from app.models.review import ReviewComment, Severity
from eval.comment_matcher import MatchResult, match
from eval.historical_pr_fetcher import HumanComment

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture() -> dict:  # type: ignore[type-arg]
    """Load the mock PR fixture data."""
    with open(FIXTURES_DIR / "mock_pr.json", encoding="utf-8") as f:
        return json.load(f)


def _make_bot_comment(
    file_path: str,
    line: int,
    severity: str,
    comment: str,
) -> ReviewComment:
    """Create a ReviewComment for testing."""
    return ReviewComment(
        file_path=file_path,
        line=line,
        severity=Severity(severity),
        comment=comment,
    )


def _make_human_comment(body: str, file_path: str, line: int) -> HumanComment:
    """Create a HumanComment for testing."""
    return HumanComment(body=body, file_path=file_path, line=line)


class TestCommentMatcherExactMatch:
    """Bot comment on exact same line with shared significant words → TP."""

    def test_exact_line_match(self) -> None:
        data = _load_fixture()

        bot_comments = [
            _make_bot_comment(**data["bot_comments"][0]),
        ]
        human_comments = [
            _make_human_comment(**data["human_comments"][0]),
        ]

        result = match(bot_comments, human_comments)

        assert result.tp == 1
        assert result.fp == 0
        assert result.fn == 0
        assert result.true_positives[0].line_distance == 0
        assert len(result.true_positives[0].shared_words) >= 2


class TestCommentMatcherWithinTolerance:
    """Bot comment 2 lines off from human comment → still TP."""

    def test_two_lines_off_still_matches(self) -> None:
        # Human on line 78, bot on line 80 → distance 2, within tolerance
        bot_comments = [
            _make_bot_comment(
                file_path="src/middleware.py",
                line=80,
                severity="SUGGESTION",
                comment=(
                    "This magic number timeout value should be"
                    " extracted to a named constant for clarity"
                ),
            ),
        ]
        human_comments = [
            _make_human_comment(
                body="Consider using a constant for this timeout value instead of a magic number",
                file_path="src/middleware.py",
                line=78,
            ),
        ]

        result = match(bot_comments, human_comments)

        assert result.tp == 1
        assert result.fp == 0
        assert result.fn == 0
        assert result.true_positives[0].line_distance == 2


class TestCommentMatcherDifferentFile:
    """Bot and human on different files → FP for bot, FN for human."""

    def test_different_files_no_match(self) -> None:
        bot_comments = [
            _make_bot_comment(
                file_path="src/middleware.py",
                line=95,
                severity="NITPICK",
                comment=(
                    "Consider adding a docstring to this helper"
                    " function for better documentation"
                ),
            ),
        ]
        human_comments = [
            _make_human_comment(
                body="The error handling here should log the exception details for debugging",
                file_path="src/handlers/auth.py",
                line=15,
            ),
        ]

        result = match(bot_comments, human_comments)

        assert result.tp == 0
        assert result.fp == 1  # bot comment unmatched
        assert result.fn == 1  # human comment unmatched
        assert result.false_positives[0].file_path == "src/middleware.py"
        assert result.false_negatives[0].file_path == "src/handlers/auth.py"


class TestReportNumbersCorrect:
    """Known TP/FP/FN counts → assert P/R/F1 computed correctly."""

    def test_precision_recall_f1(self) -> None:
        # Build a MatchResult with known counts: 3 TP, 2 FP, 1 FN
        from eval.comment_matcher import MatchedPair

        tps = [
            MatchedPair(
                bot_comment=_make_bot_comment("a.py", i, "SUGGESTION", f"comment {i}"),
                human_comment=_make_human_comment(f"human comment {i}", "a.py", i),
                line_distance=0,
                shared_words=["comment"],
            )
            for i in range(3)
        ]
        fps = [
            _make_bot_comment("b.py", i, "NITPICK", f"bot only {i}")
            for i in range(2)
        ]
        fns = [
            _make_human_comment(f"human only {i}", "c.py", i)
            for i in range(1)
        ]

        result = MatchResult(
            true_positives=tps,
            false_positives=fps,
            false_negatives=fns,
        )

        assert result.tp == 3
        assert result.fp == 2
        assert result.fn == 1

        # Precision = 3 / (3 + 2) = 0.6
        assert abs(result.precision - 0.6) < 1e-6

        # Recall = 3 / (3 + 1) = 0.75
        assert abs(result.recall - 0.75) < 1e-6

        # F1 = 2 * 0.6 * 0.75 / (0.6 + 0.75) = 0.9 / 1.35 ≈ 0.6667
        expected_f1 = 2 * 0.6 * 0.75 / (0.6 + 0.75)
        assert abs(result.f1 - expected_f1) < 1e-6

    def test_edge_case_no_comments(self) -> None:
        """Empty inputs → all metrics are 0."""
        result = match([], [])
        assert result.tp == 0
        assert result.fp == 0
        assert result.fn == 0
        assert result.precision == 0.0
        assert result.recall == 0.0
        assert result.f1 == 0.0

    def test_edge_case_only_false_positives(self) -> None:
        """Bot comments but no human comments → precision=0, recall=0."""
        bot_comments = [
            _make_bot_comment("x.py", 10, "CRITICAL", "some issue found here"),
        ]
        result = match(bot_comments, [])
        assert result.tp == 0
        assert result.fp == 1
        assert result.fn == 0
        assert result.precision == 0.0
        assert result.recall == 0.0
