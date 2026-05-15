"""Streamlit session-state wrapper.

A thin facade over ``st.session_state`` that exposes typed attributes for the
PPA app. Streamlit re-runs the script on every interaction, so all mutable
state must live here.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from ppa_engine.config import PPAConfig


_DEFAULTS: dict[str, Any] = {
    "config": None,
    "mc_result": None,
    "risk_summary": None,
    "solver_results": None,
    "n_paths": 500,
    "base_strike": 65.0,
    "simulation_ran": False,
    "preview": None,
}


class SessionState:
    """Typed proxy over ``st.session_state``.

    Reads pass through. Writes go straight into ``st.session_state`` so the
    Streamlit runtime persists them across reruns.
    """

    def __init__(self) -> None:
        for key, default in _DEFAULTS.items():
            if key not in st.session_state:
                if key == "config":
                    st.session_state[key] = PPAConfig()
                else:
                    st.session_state[key] = default

    # ---- typed accessors -------------------------------------------------

    @property
    def config(self) -> PPAConfig:
        return st.session_state["config"]

    @config.setter
    def config(self, value: PPAConfig) -> None:
        st.session_state["config"] = value

    @property
    def mc_result(self):
        return st.session_state["mc_result"]

    @mc_result.setter
    def mc_result(self, value) -> None:
        st.session_state["mc_result"] = value

    @property
    def risk_summary(self):
        return st.session_state["risk_summary"]

    @risk_summary.setter
    def risk_summary(self, value) -> None:
        st.session_state["risk_summary"] = value

    @property
    def solver_results(self):
        return st.session_state["solver_results"]

    @solver_results.setter
    def solver_results(self, value) -> None:
        st.session_state["solver_results"] = value

    @property
    def n_paths(self) -> int:
        return int(st.session_state["n_paths"])

    @n_paths.setter
    def n_paths(self, value: int) -> None:
        st.session_state["n_paths"] = int(value)

    @property
    def base_strike(self) -> float:
        return float(st.session_state["base_strike"])

    @base_strike.setter
    def base_strike(self, value: float) -> None:
        st.session_state["base_strike"] = float(value)

    @property
    def simulation_ran(self) -> bool:
        return bool(st.session_state["simulation_ran"])

    @simulation_ran.setter
    def simulation_ran(self, value: bool) -> None:
        st.session_state["simulation_ran"] = bool(value)

    @property
    def preview(self):
        return st.session_state["preview"]

    @preview.setter
    def preview(self, value) -> None:
        st.session_state["preview"] = value

    # ---- maintenance ----------------------------------------------------

    @staticmethod
    def reset() -> None:
        """Clear every entry and reseed defaults."""
        keys = list(st.session_state.keys())
        for k in keys:
            del st.session_state[k]
        SessionState()
