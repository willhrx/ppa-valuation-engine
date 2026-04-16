"""
base.py — Abstract base class for supply structures (Phase 2).

A SupplyStructure converts raw solar production and consumer load into the
settled hourly energy volume that flows under the PPA contract.  Any supply
structure can be paired with any pricing structure (3 × 4 = 12 combinations).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class SupplyStructure(ABC):
    """
    Abstract base class for PPA supply structures.

    Subclasses must implement ``settled_volume``, which takes the full set of
    hourly data and returns the contractual volume in MWh per hour.
    """

    @abstractmethod
    def settled_volume(
        self,
        solar: pd.Series,
        load: pd.Series,
    ) -> pd.Series:
        """
        Return the hourly contracted volume (MWh) for this supply structure.

        Parameters
        ----------
        solar:
            Hourly AC output of the solar asset [MWh/h].
        load:
            Hourly consumption of the offtaker [MWh/h].

        Returns
        -------
        pd.Series
            Hourly settled volume [MWh/h], same index as inputs.
        """
        ...

    def __repr__(self) -> str:  # pragma: no cover
        return f"{self.__class__.__name__}()"
