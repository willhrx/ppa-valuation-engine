"""Page 4 — PDF and Excel report download."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

_REPO = Path(__file__).resolve().parents[2]
for p in (_REPO, _REPO / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from app.components.report_builder import build_excel_report, build_pdf_report
from app.state import SessionState

st.set_page_config(page_title="Reports · PPA", page_icon="📑", layout="wide")
state = SessionState()

st.title("4 · Reports")

if not state.simulation_ran or state.mc_result is None or state.risk_summary is None:
    st.info("Run a simulation first.")
    st.page_link("pages/02_run_simulation.py", label="→ Run a simulation", icon="🎲")
    st.stop()

st.markdown(
    "Generate a PDF deal summary or an Excel workbook containing every "
    "configuration value, valuation result, and risk metric."
)

col_pdf, col_xlsx = st.columns(2)

with col_pdf:
    if st.button("Build PDF report", use_container_width=True):
        with st.spinner("Rendering PDF..."):
            pdf_bytes = build_pdf_report(
                state.config, state.mc_result, state.risk_summary, state.solver_results or {},
            )
        st.download_button(
            "📄 Download PDF report",
            data=pdf_bytes,
            file_name="ppa_valuation_report.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

with col_xlsx:
    if st.button("Build Excel workbook", use_container_width=True):
        with st.spinner("Writing workbook..."):
            xlsx_bytes = build_excel_report(
                state.config, state.mc_result, state.risk_summary, state.solver_results or {},
            )
        st.download_button(
            "📊 Download Excel workbook",
            data=xlsx_bytes,
            file_name="ppa_valuation_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
