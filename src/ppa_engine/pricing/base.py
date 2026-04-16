"""
base.py — Abstract base class for pricing structures (Phase 2).

A PricingStructure converts market prices and deal parameters into the
contractual strike price applied to each settled MWh.  Any pricing structure
can be combined with any supply structure.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class PricingStructure(ABC):
    """Abstract base class for PPA pricing structures."""

    @abstractmethod
    def strike_price(self, market_prices: pd.Series) -> pd.Series:
        """
        Return the contractual strike price for each settlement hour.

        Parameters
        ----------
        market_prices:
            Hourly spot prices [EUR/MWh].

        Returns
        -------
        pd.Series
            Hourly strike price [EUR/MWh], same index as ``market_prices``.
        """
        ...

    def __repr__(self) -> str:  # pragma: no cover
        return f"{self.__class__.__name__}()"
