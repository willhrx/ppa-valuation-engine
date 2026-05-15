"""Streamlit entry point for the PPA valuation engine UI."""

from __future__ import annotations

import sys
from importlib import metadata
from pathlib import Path

import streamlit as st


_APP_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _APP_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))


def _version() -> str:
    try:
        return metadata.version("ppa-valuation-engine")
    except metadata.PackageNotFoundError:
        return "dev"


def _build_app() -> None:
    from app.state import SessionState

    st.set_page_config(
        page_title="PPA Valuation Engine",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    SessionState()  # seed defaults

    with st.sidebar:
        st.markdown("## ⚡ PPA Valuation Engine")
        st.caption(f"v{_version()}")
        st.divider()

        st.page_link("main.py", label="Home", icon="🏠")
        st.page_link("pages/01_deal_setup.py", label="1 · Deal setup", icon="📐")
        st.page_link("pages/02_run_simulation.py", label="2 · Run simulation", icon="🎲")
        st.page_link("pages/03_risk_summary.py", label="3 · Risk summary", icon="📊")
        st.page_link("pages/04_reports.py", label="4 · Reports", icon="📑")

        st.divider()
        if st.button("Reset all", use_container_width=True):
            SessionState.reset()
            st.rerun()

    st.title("PPA Valuation Engine")
    st.markdown(
        "Scenario-conditional valuation and risk decomposition for utility-scale solar PPAs."
    )

    st.markdown(
        """
        ### Workflow
        1. **Deal setup** — configure the solar asset, market, and offtaker.
        2. **Run simulation** — launch a Monte Carlo across price and volume risk.
        3. **Risk summary** — explore the NPV distribution, capture rates and break-evens.
        4. **Reports** — export PDF and Excel deliverables.
        """
    )

    st.info(
        "Open **1 · Deal setup** from the sidebar to begin. "
        "All assumptions are explicit and editable.",
        icon="💡",
    )


def run() -> None:
    """Entry point exposed via the ``ppa-app`` console script."""
    import subprocess

    target = Path(__file__).resolve()
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(target)],
        check=False,
    )


# Streamlit executes this file top-level on every rerun, so call directly.
_build_app()
