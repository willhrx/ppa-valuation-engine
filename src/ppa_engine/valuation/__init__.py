"""
valuation — Core valuation engine (Phase 2).

Modules
-------
npv       Discounted cash-flow calculator for PPA revenue streams
capture   Capture-price decomposition (volume-weighted vs. time-weighted)
engine    Orchestration layer for supply/pricing combinations
solver    Break-even price solver using scipy.optimize.brentq (Phase 4)
"""

from ppa_engine.valuation.npv import compute_npv
from ppa_engine.valuation.capture import capture_price, capture_rate, annual_capture_rates
from ppa_engine.valuation.engine import ValuationResult, value_ppa, value_all_combinations
from ppa_engine.valuation.solver import (
    SolverResult,
    NegotiationRange,
    FairStrikeResult,
    TornadoEntry,
    TornadoResult,
    OptionPremiumResult,
    solve_break_even,
    solve_producer_irr,
    solve_consumer_ceiling,
    solve_negotiation_range,
    solve_fair_strike_cross_structure,
    compute_tornado,
    compute_option_premium,
)

__all__ = [
    "compute_npv",
    "capture_price",
    "capture_rate",
    "annual_capture_rates",
    "ValuationResult",
    "value_ppa",
    "value_all_combinations",
    "SolverResult",
    "NegotiationRange",
    "FairStrikeResult",
    "TornadoEntry",
    "TornadoResult",
    "OptionPremiumResult",
    "solve_break_even",
    "solve_producer_irr",
    "solve_consumer_ceiling",
    "solve_negotiation_range",
    "solve_fair_strike_cross_structure",
    "compute_tornado",
    "compute_option_premium",
]
