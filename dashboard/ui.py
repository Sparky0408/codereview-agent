"""Shared presentation helpers for the Streamlit dashboard."""

from __future__ import annotations

import logging
from collections.abc import Awaitable

import plotly.graph_objects as go
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

SEVERITY_COLOURS = {
    "CRITICAL": "#F97373",
    "SUGGESTION": "#FBBF24",
    "NITPICK": "#60A5FA",
}
LINE_COLOUR = "#38BDF8"
ACCENT_COLOUR = "#2DD4BF"
TEXT_MUTED = "#94A3B8"


def apply_theme() -> None:
    """Apply the dashboard visual theme."""
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

        :root {
            --bg: #0B1120;
            --panel: rgba(15, 23, 42, 0.82);
            --panel-strong: rgba(17, 24, 39, 0.96);
            --border: rgba(148, 163, 184, 0.18);
            --border-strong: rgba(56, 189, 248, 0.34);
            --text: #E5E7EB;
            --muted: #94A3B8;
            --accent: #38BDF8;
            --accent-2: #2DD4BF;
        }

        html, body, [class*="css"] {
            font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
            letter-spacing: 0;
        }

        .stApp {
            background:
                radial-gradient(circle at 18% 12%, rgba(45, 212, 191, 0.12), transparent 26%),
                radial-gradient(circle at 82% 0%, rgba(56, 189, 248, 0.10), transparent 30%),
                linear-gradient(180deg, #0B1120 0%, #111827 46%, #0B1120 100%);
            color: var(--text);
        }

        .block-container {
            padding-top: 2.25rem;
            padding-bottom: 3rem;
            max-width: 1440px;
        }

        header[data-testid="stHeader"] {
            background: rgba(11, 17, 32, 0.72);
            backdrop-filter: blur(14px);
            border-bottom: 1px solid rgba(148, 163, 184, 0.10);
        }

        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0F172A 0%, #111827 100%);
            border-right: 1px solid var(--border);
        }

        section[data-testid="stSidebar"] > div {
            padding-top: 1.4rem;
        }

        .sidebar-brand {
            border: 1px solid var(--border);
            background: rgba(15, 23, 42, 0.86);
            border-radius: 8px;
            padding: 18px 16px;
            margin-bottom: 18px;
        }

        .brand-mark {
            width: 42px;
            height: 42px;
            border-radius: 8px;
            display: inline-grid;
            place-items: center;
            color: #08111F;
            background: linear-gradient(135deg, var(--accent), var(--accent-2));
            font-weight: 800;
            margin-bottom: 12px;
        }

        .sidebar-brand h2 {
            margin: 0;
            font-size: 1.12rem;
            color: var(--text);
            line-height: 1.2;
        }

        .sidebar-brand p {
            margin: 7px 0 0 0;
            color: var(--muted);
            font-size: 0.82rem;
        }

        section[data-testid="stSidebar"] [role="radiogroup"] label {
            border: 1px solid transparent;
            border-radius: 8px;
            padding: 9px 10px;
            margin: 3px 0;
            color: #CBD5E1;
            transition: all 140ms ease;
        }

        section[data-testid="stSidebar"] [role="radiogroup"] label:hover {
            background: rgba(56, 189, 248, 0.08);
            border-color: rgba(56, 189, 248, 0.18);
        }

        .sidebar-footer {
            margin-top: 28px;
            padding: 12px 4px;
            color: var(--muted);
            font-size: 0.82rem;
            display: flex;
            align-items: center;
            gap: 8px;
            border-top: 1px solid var(--border);
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 999px;
            background: #22C55E;
            box-shadow: 0 0 0 4px rgba(34, 197, 94, 0.12);
        }

        .page-hero {
            border: 1px solid var(--border);
            background: linear-gradient(135deg, rgba(15, 23, 42, 0.94), rgba(30, 41, 59, 0.70));
            border-radius: 8px;
            padding: 26px 28px;
            margin-bottom: 22px;
        }

        .eyebrow {
            margin: 0 0 8px 0;
            color: var(--accent-2);
            font-size: 0.76rem;
            font-weight: 700;
            text-transform: uppercase;
        }

        .page-hero h1 {
            margin: 0;
            color: var(--text);
            font-size: 2rem;
            line-height: 1.15;
        }

        .page-hero p {
            max-width: 760px;
            margin: 10px 0 0 0;
            color: var(--muted);
            font-size: 0.98rem;
            line-height: 1.65;
        }

        div[data-testid="stMetric"] {
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px 18px;
            min-height: 118px;
        }

        div[data-testid="stMetric"] label {
            color: var(--muted) !important;
            font-size: 0.78rem;
            text-transform: uppercase;
            font-weight: 700;
        }

        div[data-testid="stMetric"] [data-testid="stMetricValue"] {
            color: var(--text) !important;
            font-weight: 800;
            font-size: 1.85rem;
        }

        div[data-testid="stMetric"]:hover {
            border-color: var(--border-strong);
        }

        .section-label {
            margin: 20px 0 10px 0;
            color: var(--text);
            font-size: 1.05rem;
            font-weight: 700;
        }

        div[data-testid="stPlotlyChart"],
        div[data-testid="stDataFrame"] {
            border: 1px solid var(--border);
            border-radius: 8px;
            background: var(--panel);
            padding: 10px;
        }

        div[data-testid="stAlert"] {
            border-radius: 8px;
            border: 1px solid var(--border);
            background: rgba(15, 23, 42, 0.86);
        }

        hr {
            border-color: rgba(148, 163, 184, 0.16) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_brand() -> None:
    """Render the dashboard brand block in the sidebar."""
    st.sidebar.markdown(
        """
        <div class="sidebar-brand">
            <div class="brand-mark">CR</div>
            <h2>CodeReview Agent</h2>
            <p>Review intelligence dashboard</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_page_header(title: str, eyebrow: str, description: str) -> None:
    """Render a consistent page header."""
    st.markdown(
        f"""
        <section class="page-hero">
            <p class="eyebrow">{eyebrow}</p>
            <h1>{title}</h1>
            <p>{description}</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def section_title(title: str) -> None:
    """Render a compact section title."""
    st.markdown(f'<div class="section-label">{title}</div>', unsafe_allow_html=True)


def empty_state(message: str) -> None:
    """Render a calm empty state message."""
    st.info(message)


def run_query[T](awaitable: Awaitable[T], fallback: T, label: str) -> T:
    """Run a dashboard query and return a fallback if the DB is not ready."""
    import asyncio

    try:
        return asyncio.run(awaitable)
    except (SQLAlchemyError, OSError) as exc:
        logger.warning("Dashboard query failed for %s: %s", label, exc)
        return fallback


def apply_chart_layout(fig: go.Figure, *, yaxis_title: str | None = None) -> go.Figure:
    """Apply shared Plotly styling."""
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#CBD5E1", family="Inter"),
        margin=dict(l=22, r=22, t=28, b=22),
        hovermode="x unified",
        xaxis=dict(gridcolor="rgba(148, 163, 184, 0.12)", zeroline=False),
        yaxis=dict(gridcolor="rgba(148, 163, 184, 0.12)", zeroline=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.5, xanchor="center"),
    )
    fig.update_xaxes(title=None)
    if yaxis_title is not None:
        fig.update_yaxes(title=yaxis_title)
    return fig
