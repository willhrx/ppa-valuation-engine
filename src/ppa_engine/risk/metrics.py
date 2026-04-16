"""
metrics.py — Risk metrics for the Monte Carlo NPV distribution (Phase 3).

Metrics implemented:
  - VaR(α)   : Value-at-Risk at confidence level α (e.g., 95 %)
                The loss that is not exceeded with probability α.
  - ES(α)    : Expected Shortfall (CVaR) — mean loss in the worst (1-α) % of paths.
                More coherent than VaR; used by banks for capital allocation.
  - P10/P50/P90 NPV: percentile NPVs for deal-sheet reporting.
  - Risk decomposition: variance attribution across price risk, volume risk,
    and their interaction (correlation term).

Note: all metrics are expressed from the *producer's* perspective.  A negative
NPV tail means the PPA locked in a price below what the spot market would have
paid.
"""

from __future__ import annotations

# TODO (Phase 3): implement VaR, Expected Shortfall, and decomposition


def value_at_risk(*args, **kwargs):  # type: ignore[return]
    """Compute Value-at-Risk at confidence level α. (Phase 3)"""
    raise NotImplementedError("VaR will be implemented in Phase 3.")


def expected_shortfall(*args, **kwargs):  # type: ignore[return]
    """Compute Expected Shortfall (CVaR) at confidence level α. (Phase 3)"""
    raise NotImplementedError("Expected Shortfall will be implemented in Phase 3.")
