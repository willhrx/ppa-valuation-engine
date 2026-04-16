"""
pay_as_produced.py — Pay-as-produced supply structure (Phase 2).

The offtaker buys 100 % of whatever the solar asset generates, hour by hour.
This is the standard structure for utility-scale solar PPAs without a balancing
obligation.  The offtaker bears the volume risk (actual production varies from
forecasts); the producer has no curtailment obligation.

Volume risk is fully transferred to the offtaker.
Profile risk (cannibalisation) sits with the offtaker.
"""

from __future__ import annotations

import pandas as pd

from ppa_engine.structures.base import SupplyStructure


class PayAsProduced(SupplyStructure):
    """
    Settled volume equals actual solar generation in every hour.

    Under this structure the offtaker takes whatever the asset produces —
    no more, no less.  Any excess vs. their own consumption must be resold
    on the spot market (or stored); any shortfall must be purchased separately.
    """

    def settled_volume(
        self,
        solar: pd.Series,
        load: pd.Series,
    ) -> pd.Series:
        """Return solar production as the settled volume (load is not used)."""
        return solar.rename("settled_volume_mwh")
