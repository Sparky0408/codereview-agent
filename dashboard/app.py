"""CodeReview Agent Dashboard entrypoint.

Run with:
    streamlit run dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT_PATH = str(Path(__file__).resolve().parents[1])
if ROOT_PATH not in sys.path:
    sys.path.insert(0, ROOT_PATH)

from dashboard.ui import apply_theme, render_sidebar_brand  # noqa: E402

# ---------------------------------------------------------------------------
# Page configuration (must be first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="CodeReview Agent Dashboard",
    page_icon="CR",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_theme()

# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------
render_sidebar_brand()

page = st.sidebar.radio(
    "Navigate",
    options=["Overview", "Feedback", "Eval"],
    index=0,
    key="dashboard_navigation",
    label_visibility="collapsed",
)

st.sidebar.markdown(
    """
    <div class="sidebar-footer">
        <span class="status-dot"></span>
        <span>Auto-refreshes every 60 seconds</span>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Route to the selected page
# ---------------------------------------------------------------------------
if page == "Overview":
    from dashboard.views.overview import render

    render()
elif page == "Feedback":
    from dashboard.views.feedback import render  # type: ignore[no-redef]

    render()
elif page == "Eval":
    from dashboard.views.eval import render  # type: ignore[no-redef]

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
