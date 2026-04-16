"""
indexed.py — Market-indexed pricing with optional floor and cap (Phase 2).

The strike price tracks the market price, giving both parties exposure to
market movements.  A floor protects the producer from very low prices; a cap
limits the offtaker's downside (i.e., limits how much above the cap they pay).

  effective_price(t) = clip(market_price(t) × index_factor, floor, cap)

Floor/cap combinations are essentially embedded options:
  - Floor = producer's long put option (bought from offtaker)
  - Cap   = offtaker's long call option (bought from producer)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ppa_engine.pricing.base import PricingStructure


class IndexedWithFloorCap(PricingStructure):
    """
    Strike = market price × index_factor, clipped between floor and cap.

    Parameters
    ----------
    index_factor: float
        Multiplier on spot price (e.g., 0.95 = 5 % discount to market).
    floor: float | None
        Minimum strike price in EUR/MWh.  None = no floor.
    cap: float | None
        Maximum strike price in EUR/MWh.  None = no cap.
    """

    def __init__(
        self,
        index_factor: float = 1.0,
        floor: float | None = None,
        cap: float | None = None,
    ) -> None:
        self.index_factor = index_factor
        self.floor = floor
        self.cap = cap

    def strike_price(self, market_prices: pd.Series) -> pd.Series:
        strikes = market_prices * self.index_factor
        if self.floor is not None:
            strikes = strikes.clip(lower=self.floor)
        if self.cap is not None:
            strikes = strikes.clip(upper=self.cap)
        return strikes.rename("strike_eur_mwh")
