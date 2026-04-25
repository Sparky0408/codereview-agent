"""Tests for eval.comment_matcher."""

import json
from pathlib import Path

from app.models.review import ReviewComment, Severity
from eval.comment_matcher import (
    MatchResult,
    get_non_botable_reason,
    is_botable_comment,
    match,
)
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


# ── is_botable_comment tests ──────────────────────────────────────────────


class TestIsBotableComment:
    """Tests for the botability pre-filter."""

    # ── Botable (should return True) ──

    def test_actionable_bug_report_is_botable(self) -> None:
        assert is_botable_comment("This variable is never used after assignment") is True

    def test_concrete_fix_suggestion_is_botable(self) -> None:
        assert is_botable_comment(
            "Use `with open(...)` instead of manual file handle management"
        ) is True

    def test_missing_error_handling_is_botable(self) -> None:
        assert is_botable_comment(
            "Missing null check here — this will crash on empty input"
        ) is True

    # ── Non-botable: question prefixes ──

    def test_could_question(self) -> None:
        assert is_botable_comment("Could we use a dataclass here instead?") is False

    def test_should_question(self) -> None:
        assert is_botable_comment("Should this be an async function?") is False

    def test_what_about_question(self) -> None:
        assert is_botable_comment("What about using a set for dedup?") is False

    def test_why_not_question(self) -> None:
        assert is_botable_comment("Why not use pathlib here?") is False

    def test_can_we_question(self) -> None:
        assert is_botable_comment("Can we move this to a util module?") is False

    def test_how_about_question(self) -> None:
        assert is_botable_comment("How about adding a retry here?") is False

    def test_would_it_question(self) -> None:
        assert is_botable_comment("Would it make sense to cache this?") is False

    # ── Non-botable: self-reference / change of heart ──

    def test_change_of_heart(self) -> None:
        assert is_botable_comment("Sorry, change of heart — let's keep it") is False

    def test_disagree_with_earlier_self(self) -> None:
        assert is_botable_comment(
            "I'm going to disagree with my earlier self on this one"
        ) is False

    def test_on_reviewing(self) -> None:
        assert is_botable_comment(
            "On reviewing this again, I think it's fine"
        ) is False

    def test_sorry_standalone(self) -> None:
        assert is_botable_comment("Sorry, ignore my last comment") is False

    # ── Non-botable: conversational markers ──

    def test_thoughts_question(self) -> None:
        assert is_botable_comment("We could refactor this. Thoughts?") is False

    def test_wdyt(self) -> None:
        assert is_botable_comment("Maybe use a factory pattern here, WDYT") is False

    def test_up_to_you(self) -> None:
        assert is_botable_comment("This is fine either way, up to you") is False

    def test_let_me_know(self) -> None:
        assert is_botable_comment("Not sure about this approach — let me know") is False

    # ── Non-botable: pure approval / emoji ──

    def test_lgtm(self) -> None:
        assert is_botable_comment("LGTM") is False

    def test_lgtm_with_punctuation(self) -> None:
        assert is_botable_comment("lgtm!") is False

    def test_nice(self) -> None:
        assert is_botable_comment("nice") is False

    def test_thumbs_up_emoji(self) -> None:
        assert is_botable_comment("\U0001f44d") is False

    def test_check_emoji(self) -> None:
        assert is_botable_comment("\u2705") is False

    def test_plus_one(self) -> None:
        assert is_botable_comment("+1") is False

    # ── Non-botable: absent code references ──

    def test_could_we_add(self) -> None:
        assert is_botable_comment("Could we add a docstring to this class?") is False

    def test_this_is_missing(self) -> None:
        assert is_botable_comment("This is missing error handling for timeouts") is False

    def test_please_add(self) -> None:
        assert is_botable_comment("Please add a unit test for this path") is False

    # ── Edge cases ──

    def test_empty_string(self) -> None:
        assert is_botable_comment("") is False

    def test_whitespace_only(self) -> None:
        assert is_botable_comment("   ") is False

    def test_case_insensitive_question(self) -> None:
        """Question prefix matching is case-insensitive."""
        assert is_botable_comment("COULD we use a different approach?") is False

    def test_case_insensitive_lgtm(self) -> None:
        assert is_botable_comment("Lgtm") is False


class TestMatchBotabilityIntegration:
    """match() filters non-botable human comments before computing P/R."""

    def test_non_botable_excluded_from_fn(self) -> None:
        """Non-botable human comments should not appear as false negatives."""
        bot_comments: list[ReviewComment] = []
        human_comments = [
            # Botable — real issue
            _make_human_comment(
                "This variable is shadowed in the inner scope",
                "src/app.py",
                10,
            ),
            # Non-botable — conversational
            _make_human_comment(
                "Could we use a dataclass here instead? Thoughts?",
                "src/app.py",
                20,
            ),
            # Non-botable — approval
            _make_human_comment("LGTM", "src/app.py", 30),
        ]

        result = match(bot_comments, human_comments)

        # Only the botable comment counts as FN
        assert result.fn == 1
        assert result.total_human_comments == 3
        assert result.botable_comments == 1
        assert result.non_botable_comments == 2
        assert len(result.non_botable_examples) == 2
        # Verify tuple format: (reason_tag, snippet)
        for reason, snippet in result.non_botable_examples:
            assert reason.startswith("[")
            assert isinstance(snippet, str)

    def test_stats_all_botable(self) -> None:
        """When all human comments are botable, stats reflect that."""
        human_comments = [
            _make_human_comment(
                "Unused import detected here",
                "src/utils.py",
                5,
            ),
        ]
        result = match([], human_comments)

        assert result.total_human_comments == 1
        assert result.botable_comments == 1
        assert result.non_botable_comments == 0
        assert result.fn == 1

    def test_stats_all_non_botable(self) -> None:
        """When all human comments are non-botable, FN is zero."""
        human_comments = [
            _make_human_comment("LGTM", "src/a.py", 1),
            _make_human_comment("Could we rethink this?", "src/b.py", 2),
        ]
        result = match([], human_comments)

        assert result.total_human_comments == 2
        assert result.botable_comments == 0
        assert result.non_botable_comments == 2
        assert result.fn == 0
        assert result.recall == 0.0

    def test_non_botable_examples_capped_at_five(self) -> None:
        """At most 5 non-botable examples are stored."""
        human_comments = [
            _make_human_comment("LGTM", "a.py", 1),
            _make_human_comment("nice", "b.py", 2),
            _make_human_comment("+1", "c.py", 3),
            _make_human_comment("\u2705", "d.py", 4),
            _make_human_comment("\U0001f44d", "e.py", 5),
            _make_human_comment("\U0001f389", "f.py", 6),
        ]
        result = match([], human_comments)

        assert result.non_botable_comments == 6
        assert len(result.non_botable_examples) == 5


# ── New filter tests ──────────────────────────────────────────────────────


class TestNewBotabilityFilters:
    """Tests for the 4 new filters added to is_botable_comment."""

    def test_is_botable_short_comment(self) -> None:
        """Short comment below 20 chars after stripping → non-botable."""
        assert is_botable_comment("Thanks!") is False
        assert get_non_botable_reason("Thanks!") == "[length]"

    def test_is_botable_emoji_heavy(self) -> None:
        """Emoji-heavy comment → non-botable."""
        assert is_botable_comment("Hehe :bow: :rocket:") is False

    def test_is_botable_suggestion_block(self) -> None:
        """GitHub suggestion code block → non-botable."""
        text = "```suggestion\nfoo\n```"
        assert is_botable_comment(text) is False
        assert get_non_botable_reason(text) == "[suggestion]"

    def test_is_botable_casual_reply(self) -> None:
        """Casual reply phrases → non-botable."""
        assert is_botable_comment("Good point! Thanks!") is False
        reason = get_non_botable_reason("Good point! Thanks!")
        assert reason in ("[casual]", "[length]")

    def test_is_botable_substantive(self) -> None:
        """Substantive technical comment → botable."""
        text = (
            "This function has a race condition when called "
            "concurrently because shared_state is not locked"
        )
        assert is_botable_comment(text) is True
        assert get_non_botable_reason(text) is None

    def test_agreed_casual(self) -> None:
        """'Agreed' standalone is caught by casual filter."""
        assert is_botable_comment(
            "Agreed, let's go with that approach"
        ) is False

    def test_yeah_casual(self) -> None:
        """'Yeah' in a reply is caught by casual filter."""
        assert is_botable_comment(
            "Yeah that makes sense to me now"
        ) is False
