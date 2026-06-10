"""Reusable Streamlit widgets for editing a ``PPAConfig``.

Each ``render_*`` function mutates the supplied config and returns it. The
config object lives in ``st.session_state["config"]`` and is the single
source of truth across pages.
"""

from __future__ import annotations

import datetime as dt

import streamlit as st

from ppa_engine.config import PPAConfig


_PRESETS = {
    "Industrial": [
        0.55, 0.50, 0.48, 0.48, 0.52, 0.62,
        0.78, 0.90, 0.98, 1.02, 1.10, 1.06,
        1.00, 1.02, 1.00, 1.02, 1.05, 1.08,
        1.10, 1.04, 0.92, 0.80, 0.70, 0.60,
    ],
    "Office": [
        0.40, 0.40, 0.40, 0.40, 0.42, 0.50,
        0.65, 0.80, 1.00, 1.20, 1.30, 1.30,
        1.20, 1.15, 1.10, 1.05, 1.00, 0.90,
        0.75, 0.65, 0.55, 0.50, 0.45, 0.42,
    ],
    "Datacentre": [1.0] * 24,
}


def render_solar(config: PPAConfig) -> None:
    sc = config.solar
    with st.expander("Solar asset parameters", expanded=True):
        sc.capacity_mw = st.slider(
            "Capacity (MW)", 10, 500, value=int(sc.capacity_mw), step=5, key="cfg_capacity_mw"
        )
        sc.performance_ratio = st.slider(
            "Performance ratio", 0.70, 0.92, value=float(sc.performance_ratio), step=0.01,
            key="cfg_pr",
        )
        sc.degradation_rate = st.number_input(
            "Degradation rate (per year)", min_value=0.001, max_value=0.010,
            value=float(sc.degradation_rate), step=0.001, format="%.3f",
            key="cfg_degradation",
        )
        sc.tilt_deg = st.slider(
            "Tilt (°)", 10, 60, value=int(sc.tilt_deg), step=5, key="cfg_tilt"
        )
        sc.azimuth_deg = st.slider(
            "Azimuth (°)", 135, 225, value=int(sc.azimuth_deg), step=5,
            help="180° = south-facing", key="cfg_azimuth",
        )
        sc.cloud_factor_phi = st.slider(
            "Cloud factor φ (persistence)", 0.70, 0.97, value=float(sc.cloud_factor_phi),
            step=0.01, key="cfg_cloud_phi",
        )


def render_location(config: PPAConfig) -> None:
    lc = config.location
    with st.expander("Location"):
        lc.lat = st.number_input(
            "Latitude (°N)", min_value=50.0, max_value=54.0, value=float(lc.lat),
            step=0.1, key="cfg_lat",
        )
        lc.lon = st.number_input(
            "Longitude (°E)", min_value=3.0, max_value=7.5, value=float(lc.lon),
            step=0.1, key="cfg_lon",
        )
        import pandas as pd  # local import keeps cold-start light
        st.map(pd.DataFrame({"lat": [lc.lat], "lon": [lc.lon]}), zoom=6)


def render_market(config: PPAConfig) -> None:
    mc = config.market
    with st.expander("Market price model"):
        mc.base_price = float(st.slider(
            "Base price 2027 (€/MWh)", 40, 130, value=int(mc.base_price), step=1,
            key="cfg_base_price",
        ))
        mc.drift = st.slider(
            "Drift (€/MWh per year)", -5.0, 1.0, value=float(mc.drift), step=0.25,
            key="cfg_drift",
        )
        mc.ar1_sigma = st.slider(
            "AR(1) noise σ (€/MWh)", 2.0, 20.0, value=float(mc.ar1_sigma), step=0.5,
            key="cfg_ar1_sigma",
        )
        mc.ar1_phi = st.slider(
            "AR(1) noise φ", 0.30, 0.95, value=float(mc.ar1_phi), step=0.05,
            key="cfg_ar1_phi",
        )
        mc.cannibalisation_alpha_start = float(st.slider(
            "Cannibalisation α (contract start)", 20, 100, value=int(mc.cannibalisation_alpha_start),
            step=5, key="cfg_alpha_start",
        ))
        mc.cannibalisation_alpha_end = float(st.slider(
            "Cannibalisation α (contract end)", 40, 150, value=int(mc.cannibalisation_alpha_end),
            step=5, key="cfg_alpha_end",
        ))


def render_load(config: PPAConfig) -> None:
    lc = config.load
    with st.expander("Offtaker load profile", expanded=True):
        lc.annual_consumption_gwh = float(st.slider(
            "Annual consumption (GWh)", 20, 500, value=int(lc.annual_consumption_gwh),
            step=10, key="cfg_annual_gwh",
        ))
        lc.seasonal_amplitude = st.slider(
            "Seasonal amplitude", 0.0, 0.30, value=float(lc.seasonal_amplitude),
            step=0.01, key="cfg_seasonal",
        )
        lc.noise_sigma = st.slider(
            "Hourly noise σ", 0.01, 0.15, value=float(lc.noise_sigma), step=0.01,
            key="cfg_noise",
        )

        preset = st.radio(
            "Weekday hourly shape preset",
            options=list(_PRESETS.keys()) + ["Custom"],
            horizontal=True,
            index=0,
            key="cfg_load_preset",
        )
        if preset != "Custom":
            lc.weekday_hourly_shape = list(_PRESETS[preset])
        else:
            import pandas as pd
            df = pd.DataFrame(
                {"hour": list(range(24)), "multiplier": lc.weekday_hourly_shape}
            )
            edited = st.data_editor(
                df,
                hide_index=True,
                num_rows="fixed",
                key="cfg_load_editor",
                column_config={
                    "hour": st.column_config.NumberColumn("Hour", disabled=True),
                    "multiplier": st.column_config.NumberColumn(
                        "Multiplier", min_value=0.0, max_value=3.0, step=0.05
                    ),
                },
            )
            lc.weekday_hourly_shape = [float(x) for x in edited["multiplier"].tolist()]


def render_deal(config: PPAConfig) -> None:
    dc = config.deal
    with st.expander("Deal parameters"):
        try:
            start_default = dt.date.fromisoformat(dc.start_date)
        except ValueError:
            start_default = dt.date(2027, 1, 1)
        try:
            end_default = dt.date.fromisoformat(dc.end_date)
        except ValueError:
            end_default = dt.date(2036, 12, 31)

        start = st.date_input(
            "Start date",
            value=start_default,
            min_value=dt.date(2025, 1, 1),
            max_value=dt.date(2045, 12, 31),
            key="cfg_start_date",
        )
        end = st.date_input(
            "End date",
            value=end_default,
            min_value=dt.date(2025, 1, 1),
            max_value=dt.date(2045, 12, 31),
            key="cfg_end_date",
        )
        dc.start_date = start.isoformat()
        dc.end_date = end.isoformat()
        dc.discount_rate = st.slider(
            "Discount rate", 0.03, 0.15, value=float(dc.discount_rate), step=0.005,
            format="%.3f", key="cfg_discount",
        )
