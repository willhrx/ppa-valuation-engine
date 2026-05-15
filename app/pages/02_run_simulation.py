"""Page 2 — Monte Carlo launcher."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st

_REPO = Path(__file__).resolve().parents[2]
for p in (_REPO, _REPO / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from app.state import SessionState

st.set_page_config(page_title="Run simulation · PPA", page_icon="🎲", layout="wide")
state = SessionState()

st.title("2 · Run Monte Carlo simulation")
st.caption("Three ensembles × four pricing × three supply structures. Risk is decomposed into price, volume, and interaction.")

col_a, col_b = st.columns(2)
with col_a:
    state.n_paths = st.selectbox(
        "Paths per ensemble",
        options=[100, 250, 500, 1000, 2000],
        index=[100, 250, 500, 1000, 2000].index(state.n_paths) if state.n_paths in (100, 250, 500, 1000, 2000) else 2,
        help="500 paths ≈ 20 s; 1000 paths ≈ 40 s.",
    )
with col_b:
    state.base_strike = st.slider(
        "Base strike for FixedFlat / FixedEscalated (€/MWh)",
        min_value=30.0, max_value=120.0, step=0.5, value=float(state.base_strike),
    )

modes = st.multiselect(
    "Modes",
    options=["joint", "price", "volume"],
    default=["joint", "price", "volume"],
)

st.subheader("Structure × pricing matrix")
structure_matrix = pd.DataFrame(
    [
        ("PayAsProduced", "FixedFlat", "Typical — single price for the full term"),
        ("PayAsProduced", "FixedEscalated", "Typical — annual escalator (inflation-linked)"),
        ("PayAsProduced", "IndexedWithFloorCap", "Common — index-linked with collar"),
        ("PayAsProduced", "Floating", "Less common — pure spot exposure"),
        ("PayAsNominated", "FixedFlat", "Typical — imbalance risk on the producer"),
        ("PayAsNominated", "FixedEscalated", "Typical"),
        ("PayAsNominated", "IndexedWithFloorCap", "Niche"),
        ("PayAsNominated", "Floating", "Rare"),
        ("Baseload", "FixedFlat", "Typical — full firming on the producer"),
        ("Baseload", "FixedEscalated", "Typical"),
        ("Baseload", "IndexedWithFloorCap", "Less common"),
        ("Baseload", "Floating", "Rare"),
    ],
    columns=["Supply", "Pricing", "Description"],
)


def _highlight_typical(row):
    is_typical = "Typical" in row["Description"]
    style = "background-color: rgba(59,130,246,0.20)" if is_typical else ""
    return [style] * len(row)


st.dataframe(
    structure_matrix.style.apply(_highlight_typical, axis=1),
    use_container_width=True,
    hide_index=True,
)

st.divider()

if st.button("▶ Run Monte Carlo simulation", type="primary", use_container_width=True):
    try:
        state.config.validate()
    except ValueError as exc:
        st.error(f"Invalid config: {exc}")
        st.stop()

    from ppa_engine.pricing.fixed import FixedFlat
    from ppa_engine.risk.metrics import summarise_risk
    from ppa_engine.risk.monte_carlo import run_monte_carlo
    from ppa_engine.structures.baseload import Baseload
    from ppa_engine.structures.pay_as_nominated import PayAsNominated
    from ppa_engine.structures.pay_as_produced import PayAsProduced
    from ppa_engine.valuation.solver import (
        compute_tornado,
        solve_negotiation_range,
    )
    from ppa_engine.data.consumer_load import generate_consumer_load
    from ppa_engine.data.market_prices import generate_market_prices
    from ppa_engine.data.solar_production import generate_solar_production

    progress = st.progress(0, text="Setting up...")
    status = st.empty()
    t0 = time.time()

    status.info("Running Monte Carlo paths…")
    mc_result = run_monte_carlo(
        state.config,
        n_paths=state.n_paths,
        base_strike=state.base_strike,
        modes=modes,
        verbose=False,
    )
    progress.progress(60, text="Summarising risk metrics…")

    state.mc_result = mc_result
    state.risk_summary = summarise_risk(mc_result)

    progress.progress(75, text="Solving negotiation ranges…")
    central_solar = generate_solar_production(state.config)
    central_prices = generate_market_prices(state.config)
    central_load = generate_consumer_load(state.config)

    negotiation = {}
    for supply in (PayAsProduced(), PayAsNominated(), Baseload()):
        negotiation[type(supply).__name__] = solve_negotiation_range(
            supply, central_solar, central_load, central_prices, state.config,
        )

    progress.progress(90, text="Computing tornado sensitivities…")
    tornado_pap = compute_tornado(
        PayAsProduced(), FixedFlat, state.base_strike,
        central_solar, central_load, central_prices, state.config,
    )

    state.solver_results = {
        "negotiation": negotiation,
        "tornado_pap_fixedflat": tornado_pap,
        "base_strike": state.base_strike,
    }
    state.simulation_ran = True

    progress.progress(100, text="Done")
    elapsed = time.time() - t0
    status.success(
        f"Simulation complete — {state.n_paths} paths × {len(modes)} ensembles × 12 combinations in {elapsed:.1f}s."
    )

    st.page_link(
        "pages/03_risk_summary.py",
        label="→ View risk summary",
        icon="📊",
    )

elif state.simulation_ran:
    st.success(
        f"Last run: {state.n_paths} paths · base strike €{state.base_strike:.1f}/MWh."
    )
    st.page_link("pages/03_risk_summary.py", label="→ View risk summary", icon="📊")
