"""Page 3 — Risk summary dashboard."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

_REPO = Path(__file__).resolve().parents[2]
for p in (_REPO, _REPO / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from app.components import charts
from app.state import SessionState

st.set_page_config(page_title="Risk summary · PPA", page_icon="📊", layout="wide")
state = SessionState()

st.title("3 · Risk summary")

if not state.simulation_ran or state.mc_result is None or state.risk_summary is None:
    st.info("Run a simulation first.")
    st.page_link("pages/02_run_simulation.py", label="→ Run a simulation", icon="🎲")
    st.stop()

mc_result = state.mc_result
risk_summary = state.risk_summary
solver_results = state.solver_results or {}

central_df = mc_result.central_df
paths_df = mc_result.paths_df

# ---------------------------------------------------------------------------
# Section A — Top metrics
# ---------------------------------------------------------------------------

pap_fixedflat_central = central_df[
    (central_df.supply_structure == "PayAsProduced")
    & (central_df.pricing_structure == "FixedFlat")
].iloc[0]

pap_ff_summary = next(
    c for c in risk_summary.combinations
    if c.supply_structure == "PayAsProduced" and c.pricing_structure == "FixedFlat"
)

negotiation = solver_results.get("negotiation", {})
pap_neg = negotiation.get("PayAsProduced")

st.subheader("Headline metrics")
c1, c2, c3, c4 = st.columns(4)
c1.metric("P50 producer NPV", f"€{pap_ff_summary.joint.p50/1_000_000:,.2f} M")
c2.metric("P50 capture rate", f"{pap_ff_summary.central_capture_rate*100:.1f}%")
if pap_neg is not None:
    c3.metric("Break-even strike", f"€{pap_neg.producer_floor.strike_eur_mwh:,.2f}/MWh")
    c4.metric("Negotiation spread", f"€{pap_neg.spread_eur_mwh:,.2f}/MWh")
else:
    c3.metric("Break-even strike", "—")
    c4.metric("Negotiation spread", "—")

st.divider()

# ---------------------------------------------------------------------------
# Section B — NPV distribution per supply structure
# ---------------------------------------------------------------------------

st.subheader("NPV distribution")
supply_tabs = st.tabs(["PayAsProduced", "PayAsNominated", "Baseload"])
for tab, supply_name in zip(supply_tabs, ["PayAsProduced", "PayAsNominated", "Baseload"]):
    with tab:
        # Pull raw arrays into a dict for the histogram overlay
        combo_summaries = [
            c for c in risk_summary.combinations if c.supply_structure == supply_name
        ]
        if not combo_summaries:
            st.warning(f"No data for {supply_name}.")
            continue

        # Pricing selector
        pricing_names = [c.pricing_structure for c in combo_summaries]
        selected_pricing = st.radio(
            "Pricing structure",
            pricing_names,
            horizontal=True,
            key=f"pricing_{supply_name}",
        )
        combo = next(c for c in combo_summaries if c.pricing_structure == selected_pricing)

        mask = (
            (paths_df.supply_structure == supply_name)
            & (paths_df.pricing_structure == selected_pricing)
        )
        raw = {
            "joint": paths_df[mask & (paths_df["mode"] == "joint")]["producer_npv"].to_numpy(),
            "price": paths_df[mask & (paths_df["mode"] == "price")]["producer_npv"].to_numpy(),
            "volume": paths_df[mask & (paths_df["mode"] == "volume")]["producer_npv"].to_numpy(),
        }
        combo.raw = raw  # type: ignore[attr-defined]
        st.plotly_chart(
            charts.chart_npv_distribution(combo),
            use_container_width=True,
        )

        # Risk table for all 4 pricing structures
        rows = []
        for c in combo_summaries:
            rows.append({
                "Pricing": c.pricing_structure,
                "P10 (€M)": c.joint.p10 / 1e6,
                "P50 (€M)": c.joint.p50 / 1e6,
                "P90 (€M)": c.joint.p90 / 1e6,
                "VaR-95 (€M)": c.joint.var_95 / 1e6,
                "ES-95 (€M)": c.joint.es_95 / 1e6,
                "P(NPV<0)": c.joint.prob_negative,
            })
        df_risk = pd.DataFrame(rows)

        def _style(df):
            def _row(r):
                styles = [""] * len(r)
                p50 = r["P50 (€M)"]
                var_95 = r["VaR-95 (€M)"]
                if p50 > 0:
                    styles[df.columns.get_loc("P50 (€M)")] = "color: #10B981"
                else:
                    styles[df.columns.get_loc("P50 (€M)")] = "color: #EF4444"
                if var_95 < -5:
                    styles[df.columns.get_loc("VaR-95 (€M)")] = "color: #EF4444"
                return styles
            return df.style.apply(_row, axis=1).format({
                "P10 (€M)": "{:.2f}", "P50 (€M)": "{:.2f}", "P90 (€M)": "{:.2f}",
                "VaR-95 (€M)": "{:.2f}", "ES-95 (€M)": "{:.2f}", "P(NPV<0)": "{:.1%}",
            })

        st.dataframe(_style(df_risk), use_container_width=True, hide_index=True)

st.divider()

# ---------------------------------------------------------------------------
# Section C — Variance decomposition
# ---------------------------------------------------------------------------

st.subheader("Risk attribution by structure")
st.plotly_chart(
    charts.chart_variance_decomposition(risk_summary),
    use_container_width=True,
)
st.caption(
    "Cannibalisation causes negative interaction terms for PayAsProduced because "
    "high solar output simultaneously increases volume and suppresses prices."
)

st.divider()

# ---------------------------------------------------------------------------
# Section D — Capture rate timeline
# ---------------------------------------------------------------------------

st.subheader("Capture rate timeline")
st.plotly_chart(charts.chart_capture_rate_timeline(mc_result), use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Section E — Break-even analysis
# ---------------------------------------------------------------------------

st.subheader("Break-even analysis")
left, right = st.columns(2)
with left:
    if negotiation:
        st.plotly_chart(
            charts.chart_negotiation_range(solver_results),
            use_container_width=True,
        )
    else:
        st.warning("Negotiation ranges not available.")
with right:
    if negotiation:
        rows = []
        for supply_name, neg in negotiation.items():
            rows.append({
                "Supply": supply_name,
                "Producer floor (€/MWh)": neg.producer_floor.strike_eur_mwh,
                "Consumer ceiling (€/MWh)": neg.consumer_ceiling.strike_eur_mwh,
                "Midpoint (€/MWh)": neg.midpoint,
                "Spread (€/MWh)": neg.spread_eur_mwh,
            })
        st.dataframe(
            pd.DataFrame(rows).style.format({
                "Producer floor (€/MWh)": "{:.2f}",
                "Consumer ceiling (€/MWh)": "{:.2f}",
                "Midpoint (€/MWh)": "{:.2f}",
                "Spread (€/MWh)": "{:.2f}",
            }),
            use_container_width=True,
            hide_index=True,
        )
        st.caption(
            "Fair-strike equivalence (FixedFlat) — Baseload at midpoint = "
            "PayAsProduced at midpoint = PayAsNominated at midpoint, in P50 NPV terms."
        )

st.divider()

# ---------------------------------------------------------------------------
# Section F — Tornado chart
# ---------------------------------------------------------------------------

tornado = solver_results.get("tornado_pap_fixedflat")
if tornado is not None:
    st.subheader("Tornado — NPV sensitivity")
    st.plotly_chart(charts.chart_tornado(tornado), use_container_width=True)
