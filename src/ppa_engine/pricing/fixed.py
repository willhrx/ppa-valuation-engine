"""
fixed.py — Fixed pricing structures (Phase 2).

Two variants:
  FixedFlat       Constant EUR/MWh for the full PPA tenor.
  FixedEscalated  Annual escalation (e.g., CPI-linked) applied to a base price.

Fixed pricing eliminates price risk for both parties: the producer knows
exactly what they receive; the offtaker knows exactly what they pay.  The
trade-off is basis risk vs. actual spot prices.
"""

from __future__ import annotations

import pandas as pd

from ppa_engine.pricing.base import PricingStructure


class FixedFlat(PricingStructure):
    """
    Constant strike price for every hour of the PPA.

    Parameters
    ----------
    strike: float
        Fixed price in EUR/MWh.
    """

    def __init__(self, strike: float) -> None:
        self.strike = strike

    def strike_price(self, market_prices: pd.Series) -> pd.Series:
        return pd.Series(self.strike, index=market_prices.index, name="strike_eur_mwh")


class FixedEscalated(PricingStructure):
    """
    Strike price that escalates annually by a fixed percentage.

    Parameters
    ----------
    base_strike: float
        Starting price in EUR/MWh (applied in ``base_year``).
    escalation_rate: float
        Annual escalation fraction (e.g., 0.02 for 2 % per year).
    base_year: int | None
        Reference year for the base strike price. When None (default), the
        first year of the price series — i.e. the contract start year — is
        used, so the strike starts at ``base_strike`` regardless of deal
        dates.
    """

    def __init__(
        self,
        base_strike: float,
        escalation_rate: float = 0.02,
        base_year: int | None = None,
    ) -> None:
        self.base_strike = base_strike
        self.escalation_rate = escalation_rate
        self.base_year = base_year
        # Extracting .year from a tz-aware 87k-hour index costs ~50ms; the
        # valuation engine calls this once per supply structure with the very
        # same index — cache the result by index identity.
        self._cache: tuple[pd.Index, pd.Series] | None = None

    def strike_price(self, market_prices: pd.Series) -> pd.Series:
        index = market_prices.index
        cached = self._cache
        if cached is not None and cached[0] is index:
            return cached[1]
        years = index.year
        base = self.base_year if self.base_year is not None else int(years.min())
        years_elapsed = years - base
        strikes = self.base_strike * (1 + self.escalation_rate) ** years_elapsed
        result = pd.Series(strikes, index=index, name="strike_eur_mwh")
        self._cache = (index, result)
        return result
