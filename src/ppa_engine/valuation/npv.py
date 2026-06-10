"""
npv.py — Net-present-value calculator for PPA cash flows (Phase 2).

The NPV of a PPA from the producer's perspective is:

    NPV = Σ_t  [volume(t) × (strike(t) - spot(t))] / (1 + r)^(t/8760)

where r is the annual discount rate and t is the hour index.

From the offtaker's perspective: replace (strike - spot) with (spot - strike)
to get the value of locking in a fixed price vs. buying on the market.

The discount factor is applied on a continuous hourly basis so that
intra-year cash-flow timing is handled correctly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ppa_engine.config import PPAConfig, DEFAULT_CONFIG

# Single-slot cache for discount factors. The factors are a pure function of
# (index, discount rate), and the valuation engine evaluates 12+ combinations
# against the very same index per scenario — recomputing the tz-aware
# timedelta + power over 87k hours each time dominates compute_npv. Identity
# comparison (`is`) plus the stored strong reference makes stale hits
# impossible; a mismatch simply recomputes.
_DISCOUNT_CACHE: list[tuple[pd.Index, float, np.ndarray] | None] = [None]


def _discount_factors(index: pd.Index, r: float) -> np.ndarray:
    cached = _DISCOUNT_CACHE[0]
    if cached is not None and cached[0] is index and cached[1] == r:
        return cached[2]
    hours_elapsed = (index - index[0]).total_seconds() / 3600.0
    factors = np.asarray((1 + r) ** (-hours_elapsed / 8760))
    _DISCOUNT_CACHE[0] = (index, r, factors)
    return factors


def compute_npv(
    volume: pd.Series,
    strike_price: pd.Series,
    market_price: pd.Series,
    config: PPAConfig | None = None,
) -> float:
    """
    Compute the NPV of the PPA cash flows (producer perspective).

    Parameters
    ----------
    volume:
        Hourly settled volume [MWh/h].
    strike_price:
        Contractual strike price [EUR/MWh] per hour.
    market_price:
        Spot market price [EUR/MWh] per hour.
    config:
        Model configuration (uses ``config.deal.discount_rate``).

    Returns
    -------
    float
        NPV in EUR.

    Notes
    -----
    Cash flow per hour = volume × (strike − spot).
    Positive NPV means the producer is better off under the PPA than selling
    at spot; negative NPV means the spot was higher (producer left money on
    the table, offtaker benefited).
    """
    if config is None:
        config = DEFAULT_CONFIG

    # Handle empty series
    if len(volume) == 0:
        return 0.0

    r = config.deal.discount_rate  # annual discount rate (default 0.06)

    # Hourly cash flows (producer perspective: positive when strike > spot)
    cash_flows = volume * (strike_price - market_price)

    # Continuous discount factors: (1 + r)^(-t/8760)
    # where t is hours from start and 8760 is hours per year
    discount_factors = _discount_factors(volume.index, r)

    # NPV = sum of discounted cash flows
    npv = float((cash_flows * discount_factors).sum())

    return npv
