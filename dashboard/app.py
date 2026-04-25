"""CodeReview Agent Dashboard — Streamlit entrypoint.

Run with:
    streamlit run dashboard/app.py
"""

from __future__ import annotations

import streamlit as st

# ---------------------------------------------------------------------------
# Page configuration (must be first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="CodeReview Agent Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS for a premium dark-themed dashboard
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    /* ── Global ───────────────────────────────────────────────── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    /* ── Sidebar ──────────────────────────────────────────────── */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1E1B4B 0%, #0F172A 100%);
    }
    section[data-testid="stSidebar"] .stRadio label {
        color: #CBD5E1;
        font-weight: 500;
    }

    /* ── Metric cards ─────────────────────────────────────────── */
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
        border: 1px solid rgba(99, 102, 241, 0.25);
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 4px 24px rgba(0, 0, 0, 0.3);
    }
    div[data-testid="stMetric"] label {
        color: #94A3B8 !important;
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: #E2E8F0 !important;
        font-weight: 700;
        font-size: 1.8rem;
    }

    /* ── Dividers ─────────────────────────────────────────────── */
    hr {
        border-color: rgba(99, 102, 241, 0.2) !important;
    }

    /* ── Dataframes ───────────────────────────────────────────── */
    .stDataFrame {
        border-radius: 8px;
        overflow: hidden;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------
st.sidebar.markdown(
    """
    <div style="text-align:center; padding: 16px 0 8px 0;">
        <span style="font-size:2rem;">🤖</span>
        <h2 style="margin:4px 0 0 0; color:#E2E8F0; font-weight:700;">
            CodeReview Agent
        </h2>
        <p style="color:#64748B; font-size:0.8rem; margin:0;">Dashboard v1.0</p>
    </div>
    """,
    unsafe_allow_html=True,
)

page = st.sidebar.radio(
    "Navigate",
    options=["Overview", "Feedback", "Eval"],
    index=0,
    label_visibility="collapsed",
)

st.sidebar.divider()
st.sidebar.caption("Auto-refreshes every 60 s")

# ---------------------------------------------------------------------------
# Route to the selected page
# ---------------------------------------------------------------------------
if page == "Overview":
    from dashboard.pages.overview import render

    render()
elif page == "Feedback":
    from dashboard.pages.feedback import render  # type: ignore[no-redef]

    render()
elif page == "Eval":
    from dashboard.pages.eval import render  # type: ignore[no-redef]

    render()

# ---------------------------------------------------------------------------
# Auto-refresh every 60 seconds (Streamlit ≥ 1.37 fragment-based approach
# falls back to a simple rerun timer for broad compatibility).
# ---------------------------------------------------------------------------
try:
    # Streamlit >= 1.37 supports st.fragment with run_every
    @st.fragment(run_every=60)  # type: ignore[misc]
    def _auto_refresh() -> None:
        """Hidden fragment that triggers a rerun every 60 seconds."""
        pass

    _auto_refresh()
except (TypeError, AttributeError):
    # Older Streamlit — use a manual time-based rerun via the cache trick.
    import time

    if "last_refresh" not in st.session_state:
        st.session_state["last_refresh"] = time.time()
    if time.time() - st.session_state["last_refresh"] > 60:
        st.session_state["last_refresh"] = time.time()
        st.rerun()
