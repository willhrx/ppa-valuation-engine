"""Page 1 — Deal setup. Edit the PPAConfig and preview the central scenario."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

_REPO = Path(__file__).resolve().parents[2]
for p in (_REPO, _REPO / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from app.components import charts, config_form
from app.state import SessionState

st.set_page_config(page_title="Deal setup · PPA", page_icon="📐", layout="wide")
state = SessionState()

st.title("1 · Deal setup")
st.caption("Every forward-looking input is an explicit, named assumption. Edit, validate, then preview.")

col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Solar production")
    config_form.render_solar(state.config)
    config_form.render_location(state.config)
    config_form.render_market(state.config)

with col_right:
    st.subheader("Consumption")
    config_form.render_load(state.config)

    st.markdown("**Weekday hourly profile**")
    st.plotly_chart(
        charts.chart_hourly_shape(state.config.load.weekday_hourly_shape, "Weekday"),
        use_container_width=True,
    )

    config_form.render_deal(state.config)

st.divider()


@st.cache_data(show_spinner=False, max_entries=4)
def _generate_series(config_hash: str, config_dict: dict):
    """Cache central-scenario generation by stable hash of the config dict."""
    from ppa_engine.data.consumer_load import generate_consumer_load
    from ppa_engine.data.market_prices import generate_market_prices
    from ppa_engine.data.solar_production import generate_solar_production
    from ppa_engine.config import (
        PPAConfig, LocationConfig, SolarConfig, MarketPriceConfig,
        ConsumerLoadConfig, DealConfig,
    )

    cfg = PPAConfig(
        location=LocationConfig(**config_dict["location"]),
        solar=SolarConfig(**config_dict["solar"]),
        market=MarketPriceConfig(**config_dict["market"]),
        load=ConsumerLoadConfig(**config_dict["load"]),
        deal=DealConfig(**config_dict["deal"]),
    )
    solar = generate_solar_production(cfg)
    prices = generate_market_prices(cfg)
    load = generate_consumer_load(cfg)
    return solar, prices, load


def _config_to_dict(cfg) -> dict:
    from dataclasses import asdict
    return asdict(cfg)


if st.button("▶ Preview central scenario", type="primary", use_container_width=True):
    try:
        state.config.validate()
    except ValueError as exc:
        st.error(f"Invalid config: {exc}")
    else:
        cfg_dict = _config_to_dict(state.config)
        with st.spinner("Generating solar, price and load series..."):
            solar, prices, load = _generate_series(str(hash(repr(cfg_dict))), cfg_dict)
        state.preview = {"solar": solar, "prices": prices, "load": load}

if state.preview is not None:
    solar = state.preview["solar"]
    prices = state.preview["prices"]
    load = state.preview["load"]

    horizon_years = max(1, (solar.index[-1].year - solar.index[0].year) + 1)
    solar_gwh = float(solar.sum()) / 1000.0 / horizon_years
    avg_price = float(prices.mean())
    load_gwh = float(load.sum()) / 1000.0 / horizon_years
    hedge_ratio = solar_gwh / load_gwh if load_gwh > 0 else 0.0

    st.subheader("Central scenario summary")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Solar yield (avg)", f"{solar_gwh:,.1f} GWh/yr")
    m2.metric("Avg market price", f"€{avg_price:,.1f}/MWh")
    m3.metric("Annual load", f"{load_gwh:,.1f} GWh/yr")
    m4.metric("Hedge ratio", f"{hedge_ratio * 100:.1f}%")

    # Pick a July week to show the seasonal high-solar / mid-price interaction
    week_start = pd.Timestamp(f"{solar.index[0].year}-07-01", tz=solar.index.tz)
    st.plotly_chart(
        charts.chart_sample_week(solar, load, prices, str(week_start.date())),
        use_container_width=True,
    )
