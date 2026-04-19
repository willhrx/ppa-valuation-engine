"""
risk — Monte Carlo risk engine (Phase 3).

Modules
-------
price_process         AR(1) stochastic price path simulator
production_scenarios  P10/P50/P90 solar production scenarios
monte_carlo           N-path Monte Carlo orchestrator with variance decomposition
metrics               VaR, Expected Shortfall, NPV distribution statistics
"""

from ppa_engine.risk.monte_carlo import MonteCarloResult, run_monte_carlo
from ppa_engine.risk.metrics import (
    PathDistribution,
    VarianceDecomposition,
    ComboRiskSummary,
    RiskSummary,
    value_at_risk,
    expected_shortfall,
    decompose_risk,
    summarise_risk,
    risk_by_supply_structure,
)
from ppa_engine.risk.price_process import simulate_price_paths, build_deterministic_price
from ppa_engine.risk.production_scenarios import (
    generate_production_scenarios,
    compute_annual_percentiles,
)

__all__ = [
    "MonteCarloResult",
    "run_monte_carlo",
    "PathDistribution",
    "VarianceDecomposition",
    "ComboRiskSummary",
    "RiskSummary",
    "value_at_risk",
    "expected_shortfall",
    "decompose_risk",
    "summarise_risk",
    "risk_by_supply_structure",
    "simulate_price_paths",
    "build_deterministic_price",
    "generate_production_scenarios",
    "compute_annual_percentiles",
]
