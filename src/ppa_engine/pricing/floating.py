"""
floating.py — Pure floating (spot pass-through) pricing (Phase 2).

The offtaker pays the market spot price for every MWh.  There is no price
certainty for either party.  Used as a benchmark / "no-deal" alternative to
assess the value of a fixed-price structure.

Under a pay-as-produced + floating combination the value to the offtaker vs.
buying on the spot market is zero by construction — capture-rate effects only
appear when the contracted price differs from the settlement-hour spot price.
"""

from __future__ import annotations

import pandas as pd

from ppa_engine.pricing.base import PricingStructure


class Floating(PricingStructure):
    """Strike price equals the market spot price every hour (no discount/premium)."""

    def strike_price(self, market_prices: pd.Series) -> pd.Series:
        return market_prices.rename("strike_eur_mwh")
