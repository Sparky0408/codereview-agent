"""Tests for the diff_parser utility."""

from app.services.diff_parser import parse_changed_lines


def test_parse_single_hunk() -> None:
    """Single hunk with additions and context lines."""
    patch = (
        "@@ -10,4 +10,6 @@\n"
        " context line\n"
        "+added line 1\n"
        "+added line 2\n"
        " context line\n"
        "-removed line\n"
        "+replaced line\n"
    )
    result = parse_changed_lines(patch)
    # Line 11: first +, line 12: second +, line 14: replaced line
    # context@10, +@11, +@12, context@13, -@(no advance), +@14
    assert result == {11, 12, 14}


def test_parse_multi_hunk() -> None:
    """Multiple hunks produce the union of changed lines."""
    patch = (
        "@@ -1,3 +1,4 @@\n"
        " line1\n"
        "+new_line2\n"
        " line2\n"
        " line3\n"
        "@@ -20,3 +21,4 @@\n"
        " existing\n"
        "+inserted\n"
        " existing2\n"
        " existing3\n"
    )
    result = parse_changed_lines(patch)
    # Hunk 1: context@1, +@2, context@3, context@4
    # Hunk 2: context@21, +@22, context@23, context@24
    assert result == {2, 22}


def test_parse_deletions_only() -> None:
    """Patch with only deletions produces an empty set."""
    patch = (
        "@@ -5,4 +5,2 @@\n"
        " context\n"
        "-deleted1\n"
        "-deleted2\n"
        " context\n"
    )
    result = parse_changed_lines(patch)
    assert result == set()


def test_parse_empty_patch() -> None:
    """Empty patch string returns empty set."""
    assert parse_changed_lines("") == set()


def test_parse_no_newline_marker() -> None:
    r"""Lines starting with '\\' (no newline at EOF) are ignored."""
    patch = (
        "@@ -1,2 +1,3 @@\n"
        " existing\n"
        "+added\n"
        "\\ No newline at end of file\n"
    )
    result = parse_changed_lines(patch)
    assert result == {2}


def test_parse_hunk_header_without_count() -> None:
    """Hunk header with implicit count of 1 (no comma)."""
    patch = (
        "@@ -1 +1 @@\n"
        "+replaced\n"
    )
    result = parse_changed_lines(patch)
    assert result == {1}
