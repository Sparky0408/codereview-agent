"""Overview page — bot activity at a glance."""

from __future__ import annotations

import asyncio

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.db import (
    get_comments_per_day,
    get_comments_per_severity,
    get_overview_metrics,
    get_recent_prs,
)

# ---------------------------------------------------------------------------
# Colour palette (matches the premium dark theme)
# ---------------------------------------------------------------------------
_SEVERITY_COLOURS = {
    "CRITICAL": "#EF4444",
    "SUGGESTION": "#F59E0B",
    "NITPICK": "#6366F1",
}
_LINE_COLOUR = "#818CF8"  # indigo-400


def render() -> None:
    """Render the Overview page."""
    st.header("📊 Overview")
    st.caption("High-level metrics about bot activity over all repositories.")

    # -- top metrics ----------------------------------------------------------
    metrics = asyncio.run(get_overview_metrics())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total PRs Reviewed", f"{metrics['total_prs']:,}")
    c2.metric("Total Comments Posted", f"{metrics['total_comments']:,}")
    c3.metric("Unique Repos", f"{metrics['unique_repos']:,}")

    avg_s = metrics["avg_review_time_ms"] / 1000
    c4.metric("Avg Review Time", f"{avg_s:,.1f}s" if avg_s else "—")

    st.divider()

    # -- comments per day line chart ------------------------------------------
    st.subheader("💬 Comments per Day (Last 30 Days)")

    per_day = asyncio.run(get_comments_per_day(30))
    if per_day:
        df_day = pd.DataFrame(per_day)
        df_day["date"] = pd.to_datetime(df_day["date"])
        fig_day = px.area(
            df_day,
            x="date",
            y="count",
            labels={"date": "Date", "count": "Comments"},
            color_discrete_sequence=[_LINE_COLOUR],
        )
        fig_day.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=20, r=20, t=30, b=20),
            xaxis_title=None,
            yaxis_title="Comments",
        )
        st.plotly_chart(fig_day, use_container_width=True)
    else:
        st.info("No comments recorded in the last 30 days.")

    # -- comments per severity bar chart + recent PRs -------------------------
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("🏷️ Comments by Severity")
        per_sev = asyncio.run(get_comments_per_severity())
        if per_sev:
            df_sev = pd.DataFrame(per_sev)
            fig_sev = px.bar(
                df_sev,
                x="severity",
                y="count",
                color="severity",
                color_discrete_map=_SEVERITY_COLOURS,
                labels={"severity": "Severity", "count": "Comments"},
            )
            fig_sev.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
                margin=dict(l=20, r=20, t=30, b=20),
            )
            st.plotly_chart(fig_sev, use_container_width=True)
        else:
            st.info("No severity data yet.")

    with col_right:
        st.subheader("📋 Last 10 PRs Reviewed")
        prs = asyncio.run(get_recent_prs(10))
        if prs:
            df_prs = pd.DataFrame(prs)
            df_prs.rename(
                columns={
                    "repo": "Repository",
                    "pr_number": "PR #",
                    "comment_count": "Comments",
                    "latest_at": "Reviewed At",
                },
                inplace=True,
            )
            st.dataframe(df_prs, use_container_width=True, hide_index=True)
        else:
            st.info("No PRs reviewed yet.")
