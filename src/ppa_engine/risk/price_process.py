"""
price_process.py — Stochastic price process for Monte Carlo (Phase 3).

Implements an AR(1) process (discrete-time equivalent of Ornstein-Uhlenbeck)
to simulate alternative price paths around the central scenario.

The AR(1) noise layer in the central scenario (market_prices.py, Layer 5) is
a single realisation of this process.  Phase 3 generates N independent
realisations to build a distribution of outcomes.

Why AR(1) matters for risk quantification:
  - Autocorrelation clusters low prices with high solar output → the
    cannibalisation effect is a *clustering* phenomenon, not just an average
  - Without it, Monte Carlo systematically underestimates revenue volatility
  - AR(1) is tractable, interpretable, and calibratable from EPEX data
"""

from __future__ import annotations

# TODO (Phase 3): implement stochastic AR(1) / OU price path generator


def simulate_price_paths(*args, **kwargs):  # type: ignore[return]
    """Simulate N stochastic price paths around the central scenario. (Phase 3)"""
    raise NotImplementedError("Price path simulator will be implemented in Phase 3.")
