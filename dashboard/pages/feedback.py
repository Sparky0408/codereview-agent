"""Feedback page — reaction metrics and acceptance rates."""

from __future__ import annotations

import asyncio

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.db import (
    get_acceptance_trend,
    get_flagged_comments,
    get_overall_acceptance_rate,
    get_per_repo_acceptance,
    get_per_severity_acceptance,
)

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
_SEVERITY_COLOURS = {
    "CRITICAL": "#EF4444",
    "SUGGESTION": "#F59E0B",
    "NITPICK": "#6366F1",
}
_TREND_COLOUR = "#34D399"  # emerald-400


def render() -> None:
    """Render the Feedback page."""
    st.header("👍 Feedback & Acceptance")
    st.caption("How reviewers react to bot-generated comments.")

    # -- overall acceptance rate ----------------------------------------------
    overall = asyncio.run(get_overall_acceptance_rate())
    c1, c2, c3 = st.columns(3)
    c1.metric("Acceptance Rate", f"{overall['rate']:.1f}%")
    c2.metric("👍 Thumbs Up", f"{overall['thumbs_up']:,}")
    c3.metric("Total Reactions", f"{overall['total']:,}")

    st.divider()

    # -- per-severity & per-repo acceptance -----------------------------------
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("🏷️ Acceptance by Severity")
        sev_data = asyncio.run(get_per_severity_acceptance())
        if sev_data:
            df_sev = pd.DataFrame(sev_data)
            fig_sev = px.bar(
                df_sev,
                x="severity",
                y="rate",
                color="severity",
                color_discrete_map=_SEVERITY_COLOURS,
                labels={"severity": "Severity", "rate": "Acceptance %"},
                text=df_sev["rate"].apply(lambda v: f"{v:.1f}%"),
            )
            fig_sev.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
                margin=dict(l=20, r=20, t=30, b=20),
                yaxis_range=[0, 100],
            )
            st.plotly_chart(fig_sev, use_container_width=True)
        else:
            st.info("No feedback data per severity yet.")

    with col_right:
        st.subheader("📦 Acceptance by Repository (Top 10)")
        repo_data = asyncio.run(get_per_repo_acceptance(10))
        if repo_data:
            df_repo = pd.DataFrame(repo_data)
            fig_repo = px.bar(
                df_repo,
                x="rate",
                y="repo",
                orientation="h",
                labels={"repo": "Repository", "rate": "Acceptance %"},
                color_discrete_sequence=["#818CF8"],
                text=df_repo["rate"].apply(lambda v: f"{v:.1f}%"),
            )
            fig_repo.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=20, r=20, t=30, b=20),
                yaxis=dict(autorange="reversed"),
                xaxis_range=[0, 100],
            )
            st.plotly_chart(fig_repo, use_container_width=True)
        else:
            st.info("No feedback data per repo yet.")

    st.divider()

    # -- acceptance trend -----------------------------------------------------
    st.subheader("📈 Acceptance Rate Trend (Last 30 Days)")
    trend = asyncio.run(get_acceptance_trend(30))
    if trend:
        df_trend = pd.DataFrame(trend)
        df_trend["date"] = pd.to_datetime(df_trend["date"])
        fig_trend = px.line(
            df_trend,
            x="date",
            y="rate",
            labels={"date": "Date", "rate": "Acceptance %"},
            color_discrete_sequence=[_TREND_COLOUR],
            markers=True,
        )
        fig_trend.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=20, r=20, t=30, b=20),
            yaxis_range=[0, 100],
            xaxis_title=None,
        )
        st.plotly_chart(fig_trend, use_container_width=True)
    else:
        st.info("No reaction data in the last 30 days.")

    # -- flagged comments table -----------------------------------------------
    st.subheader("🚩 Most Thumbs-Down Comments (Auto-Mute Candidates)")
    flagged = asyncio.run(get_flagged_comments(20))
    if flagged:
        df_flagged = pd.DataFrame(flagged)
        df_flagged.rename(
            columns={
                "comment_id": "ID",
                "repo": "Repository",
                "pr_number": "PR #",
                "file_path": "File",
                "severity": "Severity",
                "snippet": "Comment (truncated)",
                "thumbs_down_count": "👎 Count",
            },
            inplace=True,
        )
        st.dataframe(df_flagged, use_container_width=True, hide_index=True)
    else:
        st.info("No thumbs-down reactions recorded yet.")
