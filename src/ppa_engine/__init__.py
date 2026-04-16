"""
ppa_engine — Scenario-conditional PPA valuation engine.

Package layout
--------------
data/          Synthetic hourly data generators (solar, prices, load)
structures/    Supply structure ABCs and implementations
pricing/       Pricing structure ABCs and implementations
valuation/     NPV, capture-price, and break-even solver
risk/          Monte Carlo engine, stochastic processes, risk metrics
config.py      All assumptions as dataclasses
"""

from ppa_engine.config import PPAConfig, DEFAULT_CONFIG  # noqa: F401
