"""
baseload.py — Baseload (flat) supply structure (Phase 2).

The offtaker receives a flat, constant volume each hour throughout the year,
regardless of actual solar generation.  This fully decouples the offtaker from
solar variability — they receive a "synthetic baseload" shaped by the PPA.

The producer must manage the gap between actual generation (highly variable)
and the flat obligation via the spot market.  In hours of low generation the
producer buys from the market; in hours of high generation they sell surplus.

The flat volume is typically set equal to the expected average generation
(≈ capacity × capacity_factor).  This is the highest-certainty structure for
the offtaker and the most complex for the producer to operate.

Volume risk: producer
Profile risk: producer (they must fill the shape gap)
"""

from __future__ import annotations

import pandas as pd

from ppa_engine.structures.base import SupplyStructure


class Baseload(SupplyStructure):
    """
    Settled volume is a constant flat volume every hour.

    Parameters
    ----------
    flat_volume_mwh:
        Constant hourly volume [MWh/h].  If None, defaults to the mean of
        ``solar`` at call time (i.e., the expected P50 generation rate).
    """

    def __init__(self, flat_volume_mwh: float | None = None) -> None:
        self.flat_volume_mwh = flat_volume_mwh

    def settled_volume(
        self,
        solar: pd.Series,
        load: pd.Series,
    ) -> pd.Series:
        """Return a constant hourly volume across the full horizon."""
        flat = (
            self.flat_volume_mwh
            if self.flat_volume_mwh is not None
            else float(solar.mean())
        )
        return pd.Series(flat, index=solar.index, name="settled_volume_mwh")
