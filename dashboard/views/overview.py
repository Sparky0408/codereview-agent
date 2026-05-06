"""Overview page — bot activity at a glance."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.db import (
    get_comments_per_day,
    get_comments_per_severity,
    get_overview_metrics,
    get_recent_prs,
)
from dashboard.ui import (
    LINE_COLOUR,
    SEVERITY_COLOURS,
    apply_chart_layout,
    empty_state,
    render_page_header,
    run_query,
    section_title,
)


def render() -> None:
    """Render the Overview page."""
    render_page_header(
        "Review Operations Overview",
        "Overview",
        "Monitor pull request coverage, comment volume, severity mix, and recent bot activity.",
    )

    # -- top metrics ----------------------------------------------------------
    metrics = run_query(
        get_overview_metrics(),
        {
            "total_prs": 0,
            "total_comments": 0,
            "unique_repos": 0,
            "avg_review_time_ms": 0.0,
        },
        "overview metrics",
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total PRs Reviewed", f"{metrics['total_prs']:,}")
    c2.metric("Total Comments Posted", f"{metrics['total_comments']:,}")
    c3.metric("Unique Repos", f"{metrics['unique_repos']:,}")

    avg_s = metrics["avg_review_time_ms"] / 1000
    c4.metric("Avg Review Time", f"{avg_s:,.1f}s" if avg_s else "—")

    # -- comments per day line chart ------------------------------------------
    section_title("Comments per day")

    per_day = run_query(get_comments_per_day(30), [], "comments per day")
    if per_day:
        df_day = pd.DataFrame(per_day)
        df_day["date"] = pd.to_datetime(df_day["date"])
        fig_day = px.area(
            df_day,
            x="date",
            y="count",
            labels={"date": "Date", "count": "Comments"},
            color_discrete_sequence=[LINE_COLOUR],
        )
        fig_day.update_traces(
            line=dict(width=3),
            fillcolor="rgba(56, 189, 248, 0.18)",
            hovertemplate="%{x|%d %b}<br>%{y} comments<extra></extra>",
        )
        apply_chart_layout(fig_day, yaxis_title="Comments")
        st.plotly_chart(fig_day, use_container_width=True)
    else:
        empty_state("No comments recorded in the last 30 days.")

    # -- comments per severity bar chart + recent PRs -------------------------
    col_left, col_right = st.columns(2)

    with col_left:
        section_title("Severity mix")
        per_sev = run_query(get_comments_per_severity(), [], "comments per severity")
        if per_sev:
            df_sev = pd.DataFrame(per_sev)
            fig_sev = px.bar(
                df_sev,
                x="severity",
                y="count",
                color="severity",
                color_discrete_map=SEVERITY_COLOURS,
                labels={"severity": "Severity", "count": "Comments"},
            )
            fig_sev.update_traces(
                marker_line_width=0,
                hovertemplate="%{x}<br>%{y} comments<extra></extra>",
            )
            apply_chart_layout(fig_sev, yaxis_title="Comments")
            fig_sev.update_layout(showlegend=False)
            st.plotly_chart(fig_sev, use_container_width=True)
        else:
            empty_state("No severity data yet.")

    with col_right:
        section_title("Recent PRs")
        prs = run_query(get_recent_prs(10), [], "recent PRs")
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
            st.dataframe(
                df_prs,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Repository": st.column_config.TextColumn("Repository", width="medium"),
                    "PR #": st.column_config.NumberColumn("PR #", width="small"),
                    "Comments": st.column_config.NumberColumn("Comments", width="small"),
                    "Reviewed At": st.column_config.DatetimeColumn("Reviewed At", width="medium"),
                },
            )
        else:
            empty_state("No PRs reviewed yet.")


if __name__ == "__main__":
    st.set_page_config(page_title="Overview | CodeReview Agent", page_icon="CR", layout="wide")
    from dashboard.ui import apply_theme

    apply_theme()
    render()
