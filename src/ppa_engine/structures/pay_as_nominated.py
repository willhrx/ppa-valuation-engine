"""
pay_as_nominated.py — Pay-as-nominated supply structure (Phase 2).

The offtaker pre-nominates a schedule (e.g., day-ahead).  Settlement is
against the nominated volume, not actual production.  Deviations between
actual generation and the nomination are the producer's responsibility to
balance — they incur imbalance costs (positive or negative).

This structure introduces a nomination accuracy risk for the producer and
is common in markets with strict balancing responsibilities.

Simplifying assumption (v1): nomination equals the prior-day P50 forecast of
solar generation, derived by scaling actual solar by a P50-to-actual factor.
A more sophisticated implementation would model the nomination separately using
a weather forecast process.
"""

from __future__ import annotations

import pandas as pd

from ppa_engine.structures.base import SupplyStructure


class PayAsNominated(SupplyStructure):
    """
    Settled volume is the pre-agreed nomination schedule.

    Parameters
    ----------
    nomination_fraction:
        Fraction of expected (P50) generation nominated each day.
        Default 1.0 means nominate the full P50 forecast.
    """

    def __init__(self, nomination_fraction: float = 1.0) -> None:
        self.nomination_fraction = nomination_fraction

    def settled_volume(
        self,
        solar: pd.Series,
        load: pd.Series,
    ) -> pd.Series:
        """
        Return nominated volume.

        Nomination is the daily mean of solar, broadcast back to hourly.
        This is a first-order approximation of a day-ahead nomination schedule.
        """
        # TODO (Phase 2): replace with a proper nomination model
        daily_mean = solar.resample("D").transform("mean")
        nominated = (daily_mean * self.nomination_fraction).rename(
            "settled_volume_mwh"
        )
        return nominated
