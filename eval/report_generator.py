"""Generates a markdown evaluation report from match results."""

import logging
from dataclasses import dataclass

from eval.comment_matcher import MatchResult

logger = logging.getLogger(__name__)


@dataclass
class PRResult:
    """Evaluation result for a single PR."""

    pr_number: int
    pr_title: str
    match_result: MatchResult
    elapsed_ms: int
    bot_comment_count: int
    human_comment_count: int


@dataclass
class EvalConfig:
    """Configuration used during this evaluation run."""

    repo: str
    pr_count: int
    gemini_model: str


def _safe_div(num: float, den: float) -> float:
    """Division that returns 0.0 on zero denominator."""
    return num / den if den > 0 else 0.0


def _format_pct(value: float) -> str:
    """Format a float as a percentage string."""
    return f"{value * 100:.1f}%"


def generate(
    repo: str,
    pr_results: list[PRResult],
    config: EvalConfig,
) -> str:
    """Generate a markdown evaluation report.

    Args:
        repo: Repository full name (owner/name).
        pr_results: Per-PR evaluation results.
        config: Eval run configuration.

    Returns:
        Complete markdown report as a string.
    """
    # Aggregate totals
    total_tp = sum(r.match_result.tp for r in pr_results)
    total_fp = sum(r.match_result.fp for r in pr_results)
    total_fn = sum(r.match_result.fn for r in pr_results)

    precision = _safe_div(total_tp, total_tp + total_fp)
    recall = _safe_div(total_tp, total_tp + total_fn)
    f1 = _safe_div(2 * precision * recall, precision + recall)

    total_time_ms = sum(r.elapsed_ms for r in pr_results)
    avg_time_ms = _safe_div(total_time_ms, len(pr_results))

    lines: list[str] = []

    # Header
    lines.append(f"# Evaluation Report: `{repo}`\n")
    lines.append(f"**Model:** {config.gemini_model} | "
                 f"**PRs evaluated:** {len(pr_results)} | "
                 f"**Total time:** {total_time_ms / 1000:.1f}s\n")

    # ── Summary ──
    lines.append("## Summary\n")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| True Positives | {total_tp} |")
    lines.append(f"| False Positives | {total_fp} |")
    lines.append(f"| False Negatives | {total_fn} |")
    lines.append(f"| **Precision** | **{_format_pct(precision)}** |")
    lines.append(f"| **Recall** | **{_format_pct(recall)}** |")
    lines.append(f"| **F1 Score** | **{_format_pct(f1)}** |")
    lines.append("")

    # ── Per-PR Breakdown ──
    lines.append("## Per-PR Breakdown\n")
    lines.append("| PR# | Title | TP | FP | FN | Precision | Recall | Time |")
    lines.append("|-----|-------|----|----|----|-----------|--------|------|")
    for r in pr_results:
        pr_p = _format_pct(r.match_result.precision)
        pr_r = _format_pct(r.match_result.recall)
        title = r.pr_title[:50] + "…" if len(r.pr_title) > 50 else r.pr_title
        lines.append(
            f"| #{r.pr_number} | {title} "
            f"| {r.match_result.tp} | {r.match_result.fp} | {r.match_result.fn} "
            f"| {pr_p} | {pr_r} | {r.elapsed_ms}ms |"
        )
    lines.append("")

    # ── Per-Severity Breakdown ──
    lines.append("## Per-Severity Breakdown\n")
    severity_tp: dict[str, int] = {}
    severity_fp: dict[str, int] = {}
    for r in pr_results:
        for mp in r.match_result.true_positives:
            sev = mp.bot_comment.severity.value
            severity_tp[sev] = severity_tp.get(sev, 0) + 1
        for bc in r.match_result.false_positives:
            sev = bc.severity.value
            severity_fp[sev] = severity_fp.get(sev, 0) + 1

    all_sevs = sorted(set(severity_tp.keys()) | set(severity_fp.keys()))
    if all_sevs:
        lines.append("| Severity | TP | FP |")
        lines.append("|----------|----|----|")
        for sev in all_sevs:
            lines.append(f"| {sev} | {severity_tp.get(sev, 0)} | {severity_fp.get(sev, 0)} |")
        lines.append("")
    else:
        lines.append("_No severity data available._\n")

    # ── Sample Matches ──
    lines.append("## Sample Matches\n")

    # Collect all TPs, FPs, FNs
    all_tps = [mp for r in pr_results for mp in r.match_result.true_positives]
    all_fps = [bc for r in pr_results for bc in r.match_result.false_positives]
    all_fns = [hc for r in pr_results for hc in r.match_result.false_negatives]

    # True Positives (show up to 5)
    lines.append("### True Positives (bot matched human)\n")
    if all_tps:
        for mp in all_tps[:5]:
            lines.append(f"**{mp.bot_comment.file_path}:{mp.bot_comment.line}** "
                         f"(Δ{mp.line_distance} lines, "
                         f"shared: {', '.join(mp.shared_words[:5])})")
            lines.append(f"- 🤖 Bot: {mp.bot_comment.comment[:120]}")
            lines.append(f"- 👤 Human: {mp.human_comment.body[:120]}")
            lines.append("")
    else:
        lines.append("_No true positives._\n")

    # False Positives (show up to 3)
    lines.append("### False Positives (bot flagged, human didn't)\n")
    if all_fps:
        for bc in all_fps[:3]:
            lines.append(f"**{bc.file_path}:{bc.line}** [{bc.severity.value}]")
            lines.append(f"- 🤖 Bot: {bc.comment[:150]}")
            lines.append("")
    else:
        lines.append("_No false positives._\n")

    # False Negatives (show up to 3)
    lines.append("### False Negatives (human flagged, bot missed)\n")
    if all_fns:
        for hc in all_fns[:3]:
            lines.append(f"**{hc.file_path}:{hc.line}**")
            lines.append(f"- 👤 Human: {hc.body[:150]}")
            lines.append("")
    else:
        lines.append("_No false negatives._\n")

    # ── Performance ──
    lines.append("## Performance\n")
    if pr_results:
        times = [r.elapsed_ms for r in pr_results]
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Avg time/PR | {avg_time_ms:.0f}ms |")
        lines.append(f"| Min time/PR | {min(times)}ms |")
        lines.append(f"| Max time/PR | {max(times)}ms |")
        lines.append(f"| Total eval time | {total_time_ms / 1000:.1f}s |")
    else:
        lines.append("_No PRs evaluated._")
    lines.append("")

    # ── Configuration ──
    lines.append("## Configuration\n")
    lines.append("| Setting | Value |")
    lines.append("|---------|-------|")
    lines.append(f"| Repository | `{config.repo}` |")
    lines.append(f"| PRs requested | {config.pr_count} |")
    lines.append(f"| PRs evaluated | {len(pr_results)} |")
    lines.append(f"| Gemini model | `{config.gemini_model}` |")
    lines.append("")

    return "\n".join(lines) + "\n"
