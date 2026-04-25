"""Parses unified diff patches to extract changed line numbers.

Used to filter review comments to only lines actually modified in a PR.
"""

import re

logger_name = __name__

# Regex to match unified diff hunk headers: @@ -old_start,old_count +new_start,new_count @@
_HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def parse_changed_lines(patch: str) -> set[int]:
    """Parse a unified diff patch and return the set of added/modified line numbers.

    Only lines starting with '+' (excluding the '+++' file header) are counted.
    Line numbers refer to the NEW file (right side of the diff).

    Args:
        patch: Unified diff patch string (e.g. from PyGitHub file.patch).

    Returns:
        Set of 1-indexed line numbers in the new file that were added or modified.
    """
    changed_lines: set[int] = set()
    current_line = 0

    for raw_line in patch.splitlines():
        hunk_match = _HUNK_HEADER_RE.match(raw_line)
        if hunk_match:
            current_line = int(hunk_match.group(1))
            continue

        if current_line == 0:
            # Haven't hit a hunk header yet (file header lines)
            continue

        if raw_line.startswith("+"):
            changed_lines.add(current_line)
            current_line += 1
        elif raw_line.startswith("-"):
            # Deleted lines don't advance the new-file line counter
            pass
        else:
            # Context line (or "\ No newline at end of file")
            if not raw_line.startswith("\\"):
                current_line += 1

    return changed_lines
