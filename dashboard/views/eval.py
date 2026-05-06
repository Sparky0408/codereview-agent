"""Eval page — view and compare evaluation report results."""

from __future__ import annotations

import re
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from dashboard.ui import apply_chart_layout, empty_state, render_page_header, section_title

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_EVAL_DIR = Path("eval_reports")
_METRIC_PATTERN = re.compile(
    r"\*\*(?P<label>Precision|Recall|F1 Score)[^*]*\*\*\s*\|\s*\*\*(?P<value>[\d.]+)%\*\*",
)


def _find_reports() -> list[Path]:
    """Discover markdown reports in the eval_reports directory."""
    if not _EVAL_DIR.exists():
        return []
    return sorted(_EVAL_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)


def _extract_metrics(content: str) -> dict[str, float]:
    """Extract Precision / Recall / F1 from a report markdown string.

    Returns:
        Dict with keys 'Precision', 'Recall', 'F1 Score' mapped to floats.
    """
    metrics: dict[str, float] = {}
    for match in _METRIC_PATTERN.finditer(content):
        metrics[match.group("label")] = float(match.group("value"))
    return metrics


def render() -> None:
    """Render the Eval page."""
    render_page_header(
        "Evaluation Reports",
        "Eval",
        "Browse offline benchmark reports and compare precision, recall, and F1 over time.",
    )

    reports = _find_reports()
    if not reports:
        empty_state("No evaluation reports found in `eval_reports/`.")
        return

    # -- file selector --------------------------------------------------------
    report_names = [p.name for p in reports]
    selected = st.selectbox(
        "Select a report",
        options=report_names,
        index=0,
        key="eval_report_selector",
    )

    selected_path = _EVAL_DIR / selected
    content = selected_path.read_text(encoding="utf-8")

    # -- prominent metrics ----------------------------------------------------
    metrics = _extract_metrics(content)
    if metrics:
        cols = st.columns(len(metrics))
        for col, (label, value) in zip(cols, metrics.items(), strict=False):
            col.metric(label, f"{value:.1f}%")

    # -- render full markdown -------------------------------------------------
    section_title(selected)
    st.markdown(content, unsafe_allow_html=False)

    # -- historical comparison ------------------------------------------------
    if len(reports) >= 2:
        section_title("Historical comparison")

        history: list[dict[str, float | str]] = []
        for rp in reversed(reports):  # oldest first
            rc = rp.read_text(encoding="utf-8")
            m = _extract_metrics(rc)
            if m:
                history.append({"report": rp.stem, **m})

        if len(history) >= 2:
            labels = [h["report"] for h in history]
            precision_vals = [h.get("Precision", 0.0) for h in history]
            recall_vals = [h.get("Recall", 0.0) for h in history]
            f1_vals = [h.get("F1 Score", 0.0) for h in history]

            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=labels,
                    y=precision_vals,
                    mode="lines+markers",
                    name="Precision",
                    line=dict(color="#60A5FA", width=3),
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=labels,
                    y=recall_vals,
                    mode="lines+markers",
                    name="Recall",
                    line=dict(color="#34D399", width=3),
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=labels,
                    y=f1_vals,
                    mode="lines+markers",
                    name="F1",
                    line=dict(color="#FBBF24", width=3),
                )
            )
            apply_chart_layout(fig, yaxis_title="Score %")
            fig.update_layout(yaxis_range=[0, 100])
            st.plotly_chart(fig, use_container_width=True)
        else:
            empty_state("Need at least 2 reports with metrics for a comparison chart.")

    # -- file uploader --------------------------------------------------------
    section_title("Upload a new report")
    uploaded = st.file_uploader(
        "Upload an eval_report_*.md file",
        type=["md"],
        key="eval_upload",
    )
    if uploaded is not None:
        dest = _EVAL_DIR / uploaded.name
        dest.write_bytes(uploaded.getvalue())
        st.success(f"Saved **{uploaded.name}** to `eval_reports/`. Refresh to see it.")
        st.rerun()


if __name__ == "__main__":
    st.set_page_config(page_title="Eval | CodeReview Agent", page_icon="CR", layout="wide")
    from dashboard.ui import apply_theme

    apply_theme()
    render()
