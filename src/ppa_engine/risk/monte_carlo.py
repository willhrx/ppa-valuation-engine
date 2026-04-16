"""
monte_carlo.py — 1,000-path Monte Carlo orchestrator (Phase 3).

For each path:
  1. Draw an independent price path (AR(1) residuals around central scenario)
  2. Draw an independent production path (cloud factor re-seed)
  3. Combine via chosen supply + pricing structure
  4. Compute NPV

The resulting distribution of 1,000 NPVs supports:
  - P10/P50/P90 NPV range
  - Value-at-Risk (VaR) at 95 % confidence
  - Expected Shortfall (ES / CVaR)
  - Risk decomposition: how much does each source contribute to NPV variance?
"""

from __future__ import annotations

# TODO (Phase 3): implement Monte Carlo orchestrator


def run_monte_carlo(*args, **kwargs):  # type: ignore[return]
    """Run N-path Monte Carlo simulation over the PPA horizon. (Phase 3)"""
    raise NotImplementedError("Monte Carlo engine will be implemented in Phase 3.")
