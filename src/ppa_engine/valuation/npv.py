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

from ppa_engine.config import PPAConfig


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
    # TODO (Phase 2): implement
    raise NotImplementedError("NPV calculator will be implemented in Phase 2.")
