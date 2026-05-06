"""Feedback page — reaction metrics and acceptance rates."""

from __future__ import annotations

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
from dashboard.ui import (
    ACCENT_COLOUR,
    SEVERITY_COLOURS,
    apply_chart_layout,
    empty_state,
    render_page_header,
    run_query,
    section_title,
)


def render() -> None:
    """Render the Feedback page."""
    render_page_header(
        "Feedback Quality",
        "Feedback",
        "Track reviewer reactions, acceptance rate, and comment patterns that may need tuning.",
    )

    # -- overall acceptance rate ----------------------------------------------
    overall = run_query(
        get_overall_acceptance_rate(),
        {"thumbs_up": 0, "total": 0, "rate": 0.0},
        "overall acceptance",
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Acceptance Rate", f"{overall['rate']:.1f}%")
    c2.metric("Thumbs Up", f"{overall['thumbs_up']:,}")
    c3.metric("Total Reactions", f"{overall['total']:,}")

    # -- per-severity & per-repo acceptance -----------------------------------
    col_left, col_right = st.columns(2)

    with col_left:
        section_title("Acceptance by severity")
        sev_data = run_query(get_per_severity_acceptance(), [], "severity acceptance")
        if sev_data:
            df_sev = pd.DataFrame(sev_data)
            fig_sev = px.bar(
                df_sev,
                x="severity",
                y="rate",
                color="severity",
                color_discrete_map=SEVERITY_COLOURS,
                labels={"severity": "Severity", "rate": "Acceptance %"},
                text=df_sev["rate"].apply(lambda v: f"{v:.1f}%"),
            )
            fig_sev.update_traces(
                marker_line_width=0,
                textposition="outside",
                hovertemplate="%{x}<br>%{y:.1f}% accepted<extra></extra>",
            )
            apply_chart_layout(fig_sev, yaxis_title="Acceptance %")
            fig_sev.update_layout(showlegend=False, yaxis_range=[0, 100])
            st.plotly_chart(fig_sev, use_container_width=True)
        else:
            empty_state("No feedback data per severity yet.")

    with col_right:
        section_title("Acceptance by repository")
        repo_data = run_query(get_per_repo_acceptance(10), [], "repo acceptance")
        if repo_data:
            df_repo = pd.DataFrame(repo_data)
            fig_repo = px.bar(
                df_repo,
                x="rate",
                y="repo",
                orientation="h",
                labels={"repo": "Repository", "rate": "Acceptance %"},
                color_discrete_sequence=[ACCENT_COLOUR],
                text=df_repo["rate"].apply(lambda v: f"{v:.1f}%"),
            )
            fig_repo.update_traces(
                marker_line_width=0,
                textposition="outside",
                hovertemplate="%{y}<br>%{x:.1f}% accepted<extra></extra>",
            )
            apply_chart_layout(fig_repo, yaxis_title=None)
            fig_repo.update_layout(yaxis=dict(autorange="reversed"), xaxis_range=[0, 100])
            st.plotly_chart(fig_repo, use_container_width=True)
        else:
            empty_state("No feedback data per repo yet.")

    # -- acceptance trend -----------------------------------------------------
    section_title("Acceptance trend")
    trend = run_query(get_acceptance_trend(30), [], "acceptance trend")
    if trend:
        df_trend = pd.DataFrame(trend)
        df_trend["date"] = pd.to_datetime(df_trend["date"])
        fig_trend = px.line(
            df_trend,
            x="date",
            y="rate",
            labels={"date": "Date", "rate": "Acceptance %"},
            color_discrete_sequence=[ACCENT_COLOUR],
            markers=True,
        )
        fig_trend.update_traces(
            line=dict(width=3),
            marker=dict(size=8),
            hovertemplate="%{x|%d %b}<br>%{y:.1f}% accepted<extra></extra>",
        )
        apply_chart_layout(fig_trend, yaxis_title="Acceptance %")
        fig_trend.update_layout(yaxis_range=[0, 100])
        st.plotly_chart(fig_trend, use_container_width=True)
    else:
        empty_state("No reaction data in the last 30 days.")

    # -- flagged comments table -----------------------------------------------
    section_title("Thumbs-down candidates")
    flagged = run_query(get_flagged_comments(20), [], "flagged comments")
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
                "thumbs_down_count": "Downvotes",
            },
            inplace=True,
        )
        st.dataframe(
            df_flagged,
            use_container_width=True,
            hide_index=True,
            column_config={
                "ID": st.column_config.NumberColumn("ID", width="small"),
                "Repository": st.column_config.TextColumn("Repository", width="medium"),
                "PR #": st.column_config.NumberColumn("PR #", width="small"),
                "File": st.column_config.TextColumn("File", width="medium"),
                "Severity": st.column_config.TextColumn("Severity", width="small"),
                "Comment (truncated)": st.column_config.TextColumn(
                    "Comment",
                    width="large",
                ),
                "Downvotes": st.column_config.NumberColumn("Downvotes", width="small"),
            },
        )
    else:
        empty_state("No thumbs-down reactions recorded yet.")


if __name__ == "__main__":
    st.set_page_config(page_title="Feedback | CodeReview Agent", page_icon="CR", layout="wide")
    from dashboard.ui import apply_theme

    apply_theme()
    render()
