"""Fuzzy-matches bot review comments against human review comments.

Matching criteria:
- Same file
- Line numbers within ±3 of each other
- ≥2 significant words in common (stop words excluded)

Pre-filtering:
- Human comments are classified as "botable" or "non-botable" before matching.
- Only botable comments count toward the recall denominator.
"""

import logging
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field

from app.models.review import ReviewComment
from eval.historical_pr_fetcher import HumanComment

logger = logging.getLogger(__name__)

LINE_TOLERANCE = 3
MIN_SHARED_WORDS = 2

_STOP_WORDS: frozenset[str] = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "must",
    "this", "that", "these", "those", "it", "its",
    "i", "you", "he", "she", "we", "they", "me", "him", "her", "us", "them",
    "my", "your", "his", "our", "their",
    "to", "of", "in", "for", "on", "with", "at", "by", "from", "as",
    "into", "about", "between", "through", "after", "before",
    "and", "or", "but", "nor", "not", "no", "if", "then", "else",
    "so", "than", "too", "very", "just",
})


def _extract_significant_words(text: str) -> set[str]:
    """Extract significant words from text, excluding stop words and short tokens."""
    words = set()
    for token in text.lower().split():
        # Strip common punctuation
        cleaned = token.strip(".,;:!?\"'`()[]{}#*-_/\\@")
        if len(cleaned) >= 3 and cleaned not in _STOP_WORDS:
            words.add(cleaned)
    return words


# ── Botability pre-filter ─────────────────────────────────────────────────

_QUESTION_PREFIXES: tuple[str, ...] = (
    "could ", "should ", "what about ", "why not ",
    "can we ", "how about ", "would it ",
)

_SELF_REFERENCE_PATTERNS: tuple[str, ...] = (
    "i'm going to disagree with my earlier self",
    "change of heart",
    "on reviewing",
    "sorry",
)

_CONVERSATIONAL_MARKERS: tuple[str, ...] = (
    "thoughts?",
    "wdyt",
    "up to you",
    "let me know",
)

_PURE_APPROVAL_RE = re.compile(
    r"^\s*"
    r"(lgtm|nice|👍|✅|🎉|💯|\+1)"
    r"[\s!.]*$",
    re.IGNORECASE,
)

_ABSENT_CODE_RE = re.compile(
    r"\bcould we add\b|\bshould we add\b|\bthis is missing\b"
    r"|\bwe need to add\b|\bplease add\b|\bcan we add\b",
    re.IGNORECASE,
)

# GitHub-style colon-emoji shortcodes (e.g. :bow:, :rocket:)
_COLON_EMOJI_RE = re.compile(r":[a-z0-9_+-]+:")

_CASUAL_REPLY_RE = re.compile(
    r"\b(good point|great catch|nice one|thanks|hehe"
    r"|oops|my bad|true|fair enough|agreed|yeah)\b",
    re.IGNORECASE,
)

_MIN_STRIPPED_LENGTH = 20
_MAX_EMOJI_PUNCT_RATIO = 0.30


def _strip_emoji_and_shortcodes(text: str) -> str:
    """Remove Unicode emoji characters and :shortcode: sequences."""
    # Remove colon shortcodes first
    text = _COLON_EMOJI_RE.sub("", text)
    # Remove Unicode emoji / symbol characters
    return "".join(
        ch for ch in text
        if unicodedata.category(ch) not in ("So", "Sk", "Sc")
    )


def _emoji_punct_ratio(text: str) -> float:
    """Return fraction of characters that are emoji, shortcodes, or punctuation."""
    if not text:
        return 0.0
    total = len(text)
    noise = 0
    # Count colon shortcodes as noise
    for m in _COLON_EMOJI_RE.finditer(text):
        noise += len(m.group())
    # Count remaining emoji / symbol / punctuation chars
    for ch in _COLON_EMOJI_RE.sub("", text):
        cat = unicodedata.category(ch)
        if cat.startswith("P") or cat in ("So", "Sk", "Sc"):
            noise += 1
    return noise / total


def get_non_botable_reason(text: str) -> str | None:
    """Return the filter tag if a comment is non-botable, else None.

    Filter tags: ``[empty]``, ``[approval]``, ``[question]``, ``[self-ref]``,
    ``[conversational]``, ``[absent-code]``, ``[length]``, ``[emoji]``,
    ``[suggestion]``, ``[casual]``.

    Args:
        text: Raw body of the human review comment.

    Returns:
        A short tag string if non-botable, or None if the comment is botable.
    """
    if not text or not text.strip():
        return "[empty]"

    stripped = text.strip()
    normalized = stripped.lower()

    # Pure approval / emoji
    if _PURE_APPROVAL_RE.match(stripped):
        return "[approval]"

    # Suggestion-block: starts with ```suggestion or is purely a code block
    if normalized.startswith("```suggestion") or (
        normalized.startswith("```") and normalized.rstrip("`").endswith("```")
    ):
        return "[suggestion]"

    # Length after stripping whitespace and emoji/shortcodes
    cleaned = _strip_emoji_and_shortcodes(stripped).strip()
    if len(cleaned) < _MIN_STRIPPED_LENGTH:
        return "[length]"

    # Emoji-heavy
    if _emoji_punct_ratio(stripped) > _MAX_EMOJI_PUNCT_RATIO:
        return "[emoji]"

    # Question prefixes
    for prefix in _QUESTION_PREFIXES:
        if normalized.startswith(prefix):
            return "[question]"

    # Self-reference patterns
    for pattern in _SELF_REFERENCE_PATTERNS:
        if pattern in normalized:
            return "[self-ref]"

    # Conversational markers
    for marker in _CONVERSATIONAL_MARKERS:
        if marker in normalized:
            return "[conversational]"

    # Casual reply
    if _CASUAL_REPLY_RE.search(normalized):
        return "[casual]"

    # References to absent code
    if _ABSENT_CODE_RE.search(text):
        return "[absent-code]"

    return None


def is_botable_comment(text: str) -> bool:
    """Classify whether a human review comment is 'botable'.

    A comment is non-botable (returns False) if it falls into any of these
    categories:
    - Is empty or whitespace-only
    - Is pure approval or emoji
    - Starts with a GitHub ``suggestion`` code block
    - Is too short after stripping emoji (<20 chars)
    - Is emoji/punctuation heavy (>30%%)
    - Starts with a question word/phrase
    - Contains self-reference to reviewer's own previous comment
    - Contains conversational markers
    - Contains casual reply phrases ("thanks", "agreed", etc.)
    - References only absent code (things to add, not things to fix)

    Args:
        text: Raw body of the human review comment.

    Returns:
        True if the comment is botable (should count toward recall).
    """
    return get_non_botable_reason(text) is None


@dataclass(frozen=True)
class MatchedPair:
    """A true-positive match between a bot comment and a human comment."""

    bot_comment: ReviewComment
    human_comment: HumanComment
    line_distance: int
    shared_words: list[str]


@dataclass
class MatchResult:
    """Result of matching bot vs human comments for a single PR."""

    true_positives: list[MatchedPair] = field(default_factory=list)
    false_positives: list[ReviewComment] = field(default_factory=list)
    false_negatives: list[HumanComment] = field(default_factory=list)
    total_human_comments: int = 0
    botable_comments: int = 0
    non_botable_comments: int = 0
    non_botable_examples: list[tuple[str, str]] = field(default_factory=list)

    @property
    def tp(self) -> int:
        """Count of true positives."""
        return len(self.true_positives)

    @property
    def fp(self) -> int:
        """Count of false positives."""
        return len(self.false_positives)

    @property
    def fn(self) -> int:
        """Count of false negatives."""
        return len(self.false_negatives)

    @property
    def precision(self) -> float:
        """Precision = TP / (TP + FP).  Returns 0.0 if no bot comments."""
        total = self.tp + self.fp
        return self.tp / total if total > 0 else 0.0

    @property
    def recall(self) -> float:
        """Recall = TP / (TP + FN).  Returns 0.0 if no human comments."""
        total = self.tp + self.fn
        return self.tp / total if total > 0 else 0.0

    @property
    def f1(self) -> float:
        """F1 = harmonic mean of precision and recall."""
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0


def match(
    bot_comments: list[ReviewComment],
    human_comments: list[HumanComment],
) -> MatchResult:
    """Match bot-generated comments against human review comments.

    Uses greedy matching: for each file, pairs are ranked by
    (line_distance ASC, shared_word_count DESC) and assigned 1:1.

    Human comments are pre-filtered through ``is_botable_comment``; only
    botable comments participate in matching and count toward recall.

    Args:
        bot_comments: Comments generated by the bot in dry-run mode.
        human_comments: Comments left by human reviewers on the real PR.

    Returns:
        MatchResult with TP, FP, FN breakdowns and botability stats.
    """
    total_human = len(human_comments)

    # Pre-filter: only botable comments count toward recall
    botable: list[HumanComment] = []
    non_botable_examples: list[tuple[str, str]] = []
    for hc in human_comments:
        reason = get_non_botable_reason(hc.body)
        if reason is None:
            botable.append(hc)
        else:
            # Keep first 5 examples for the report (with reason tag)
            if len(non_botable_examples) < 5:
                non_botable_examples.append((reason, hc.body[:150]))

    non_botable_count = total_human - len(botable)
    logger.info(
        "Botability filter: %d/%d human comments are botable (%d filtered)",
        len(botable), total_human, non_botable_count,
    )

    # Group by file path
    bot_by_file: dict[str, list[ReviewComment]] = defaultdict(list)
    human_by_file: dict[str, list[HumanComment]] = defaultdict(list)

    for bc in bot_comments:
        bot_by_file[bc.file_path].append(bc)
    for hc in botable:
        human_by_file[hc.file_path].append(hc)

    result = MatchResult(
        total_human_comments=total_human,
        botable_comments=len(botable),
        non_botable_comments=non_botable_count,
        non_botable_examples=non_botable_examples,
    )

    all_files = set(bot_by_file.keys()) | set(human_by_file.keys())

    for file_path in all_files:
        file_bots = list(bot_by_file.get(file_path, []))
        file_humans = list(human_by_file.get(file_path, []))

        # Build candidate pairs
        candidates: list[tuple[int, int, int, list[str]]] = []
        for bi, bc in enumerate(file_bots):
            bot_words = _extract_significant_words(bc.comment)
            for hi, hc in enumerate(file_humans):
                line_dist = abs(bc.line - hc.line)
                if line_dist > LINE_TOLERANCE:
                    continue
                human_words = _extract_significant_words(hc.body)
                shared = sorted(bot_words & human_words)
                if len(shared) < MIN_SHARED_WORDS:
                    continue
                candidates.append((bi, hi, line_dist, shared))

        # Greedy 1:1 assignment: sort by (line_distance ASC, shared DESC)
        candidates.sort(key=lambda c: (c[2], -len(c[3])))

        matched_bots: set[int] = set()
        matched_humans: set[int] = set()

        for bi, hi, line_dist, shared in candidates:
            if bi in matched_bots or hi in matched_humans:
                continue
            result.true_positives.append(
                MatchedPair(
                    bot_comment=file_bots[bi],
                    human_comment=file_humans[hi],
                    line_distance=line_dist,
                    shared_words=shared,
                )
            )
            matched_bots.add(bi)
            matched_humans.add(hi)

        # Unmatched bot comments → false positives
        for bi, bc in enumerate(file_bots):
            if bi not in matched_bots:
                result.false_positives.append(bc)

        # Unmatched human comments → false negatives
        for hi, hc in enumerate(file_humans):
            if hi not in matched_humans:
                result.false_negatives.append(hc)

    return result
