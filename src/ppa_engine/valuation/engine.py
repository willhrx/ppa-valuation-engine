"""
engine.py — PPA valuation orchestration layer (Phase 2).

This module provides the high-level interface for valuing PPAs. It combines:
- Supply structures (determining volume)
- Pricing structures (determining strike price)
- NPV computation (discounting cash flows)

The main entry points are:
- value_ppa(): Value a single supply/pricing combination
- value_all_combinations(): Value all 12 combinations (3 supply x 4 pricing)

The valuation is always zero-sum: producer NPV + consumer NPV = 0.
This reflects that PPAs redistribute risk between parties but do not create
or destroy value in aggregate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import pandas as pd

from ppa_engine.config import PPAConfig, DEFAULT_CONFIG
from ppa_engine.structures.base import SupplyStructure
from ppa_engine.pricing.base import PricingStructure
from ppa_engine.valuation.npv import compute_npv
from ppa_engine.valuation.capture import capture_rate


@dataclass
class ValuationResult:
    """
    Container for PPA valuation outputs.

    Attributes
    ----------
    producer_npv : float
        NPV from producer's perspective [EUR].
        Positive = PPA better than spot market for producer.
    consumer_npv : float
        NPV from consumer's perspective [EUR].
        Always equals -producer_npv (zero-sum by construction).
    total_volume_mwh : float
        Total contracted volume over the PPA horizon [MWh].
    average_strike_eur_mwh : float
        Volume-weighted average strike price [EUR/MWh].
    capture_rate : float
        Ratio of capture price to time-weighted average price.
    volume_value : float
        Value component from total volume at avg price diff [EUR].
    profile_value : float
        Value component from generation timing [EUR].
    supply_structure : str
        Name of the supply structure used.
    pricing_structure : str
        Name of the pricing structure used.
    """

    producer_npv: float
    consumer_npv: float
    total_volume_mwh: float
    average_strike_eur_mwh: float
    capture_rate: float
    volume_value: float
    profile_value: float
    supply_structure: str
    pricing_structure: str

    def __post_init__(self) -> None:
        """Validate zero-sum property."""
        tolerance = 1e-6
        if abs(self.producer_npv + self.consumer_npv) > tolerance:
            raise ValueError(
                f"Zero-sum violated: producer_npv ({self.producer_npv}) + "
                f"consumer_npv ({self.consumer_npv}) != 0"
            )


def value_ppa(
    supply_structure: SupplyStructure,
    pricing_structure: PricingStructure,
    solar: pd.Series,
    load: pd.Series,
    market_prices: pd.Series,
    config: PPAConfig | None = None,
) -> ValuationResult:
    """
    Value a PPA under a given supply and pricing structure combination.

    Parameters
    ----------
    supply_structure : SupplyStructure
        Determines hourly settled volume.
    pricing_structure : PricingStructure
        Determines hourly strike price.
    solar : pd.Series
        Hourly solar production [MWh/h].
    load : pd.Series
        Hourly consumer load [MWh/h].
    market_prices : pd.Series
        Hourly spot prices [EUR/MWh].
    config : PPAConfig | None
        Configuration. Uses DEFAULT_CONFIG if None.

    Returns
    -------
    ValuationResult
        Complete valuation results including NPVs and decomposition.
    """
    if config is None:
        config = DEFAULT_CONFIG

    # Step 1: Compute settled volume via supply structure
    volume = supply_structure.settled_volume(solar, load)

    # Step 2: Compute strike prices via pricing structure
    strikes = pricing_structure.strike_price(market_prices)

    # Step 3: Compute producer NPV
    producer_npv = compute_npv(volume, strikes, market_prices, config)

    # Step 4: Consumer NPV is negative of producer (zero-sum)
    consumer_npv = -producer_npv

    # Step 5: Compute auxiliary metrics
    total_volume = float(volume.sum())

    if total_volume > 0:
        avg_strike = float((strikes * volume).sum() / total_volume)
    else:
        avg_strike = 0.0

    cr = capture_rate(market_prices, solar)

    # Step 6: Value decomposition
    volume_value, profile_value = _decompose_value(
        volume, strikes, market_prices, config
    )

    return ValuationResult(
        producer_npv=producer_npv,
        consumer_npv=consumer_npv,
        total_volume_mwh=total_volume,
        average_strike_eur_mwh=avg_strike,
        capture_rate=cr,
        volume_value=volume_value,
        profile_value=profile_value,
        supply_structure=type(supply_structure).__name__,
        pricing_structure=type(pricing_structure).__name__,
    )


def _decompose_value(
    volume: pd.Series,
    strike: pd.Series,
    market_price: pd.Series,
    config: PPAConfig,
) -> Tuple[float, float]:
    """
    Decompose NPV into volume value and profile value.

    Volume Value: What you would get from total volume at average price differential
        = total_volume * (avg_strike - avg_market) * mid_discount_factor

    Profile Value: Additional value from when generation occurs
        = total_NPV - volume_value

    This decomposition shows how much of the PPA value comes from simply
    locking in a price differential (volume value) vs. the timing of when
    generation occurs relative to price movements (profile value).

    Parameters
    ----------
    volume : pd.Series
        Hourly settled volume [MWh/h].
    strike : pd.Series
        Hourly strike price [EUR/MWh].
    market_price : pd.Series
        Hourly spot price [EUR/MWh].
    config : PPAConfig
        Configuration (for discount rate).

    Returns
    -------
    Tuple[float, float]
        (volume_value, profile_value) in EUR.
    """
    r = config.deal.discount_rate

    total_volume = float(volume.sum())
    if total_volume == 0:
        return (0.0, 0.0)

    # Volume-weighted average prices
    avg_strike = float((strike * volume).sum() / total_volume)
    avg_market = float((market_price * volume).sum() / total_volume)

    # Approximate volume value by discounting to contract midpoint
    # This is an approximation since actual discounting is hourly
    n_hours = len(volume)
    mid_hours = n_hours / 2.0
    mid_discount = (1 + r) ** (-mid_hours / 8760)

    volume_value = total_volume * (avg_strike - avg_market) * mid_discount

    # Compute total NPV for decomposition
    total_npv = compute_npv(volume, strike, market_price, config)

    # Profile value is the residual
    profile_value = total_npv - volume_value

    return (volume_value, profile_value)


def value_all_combinations(
    solar: pd.Series,
    load: pd.Series,
    market_prices: pd.Series,
    config: PPAConfig | None = None,
    base_strike: float = 65.0,
) -> pd.DataFrame:
    """
    Value all 12 supply/pricing structure combinations.

    Creates a matrix of 3 supply structures x 4 pricing structures
    and computes valuation results for each combination.

    Parameters
    ----------
    solar : pd.Series
        Hourly solar production [MWh/h].
    load : pd.Series
        Hourly consumer load [MWh/h].
    market_prices : pd.Series
        Hourly spot prices [EUR/MWh].
    config : PPAConfig | None
        Configuration. Uses DEFAULT_CONFIG if None.
    base_strike : float
        Base strike price for fixed pricing structures [EUR/MWh].
        Default is 65.0, chosen to be near typical solar capture price.

    Returns
    -------
    pd.DataFrame
        Results for all 12 combinations, one row per combination.
        Columns match ValuationResult fields.
    """
    from ppa_engine.structures.pay_as_produced import PayAsProduced
    from ppa_engine.structures.pay_as_nominated import PayAsNominated
    from ppa_engine.structures.baseload import Baseload
    from ppa_engine.pricing.fixed import FixedFlat, FixedEscalated
    from ppa_engine.pricing.indexed import IndexedWithFloorCap
    from ppa_engine.pricing.floating import Floating

    if config is None:
        config = DEFAULT_CONFIG

    supply_structures = [
        PayAsProduced(),
        PayAsNominated(),
        Baseload(),
    ]

    pricing_structures = [
        FixedFlat(strike=base_strike),
        FixedEscalated(
            base_strike=base_strike,
            escalation_rate=0.02,
            base_year=pd.Timestamp(config.deal.start_date).year,
        ),
        IndexedWithFloorCap(index_factor=0.95, floor=40.0, cap=120.0),
        Floating(),
    ]

    results = []
    for supply in supply_structures:
        for pricing in pricing_structures:
            result = value_ppa(
                supply, pricing, solar, load, market_prices, config
            )
            results.append({
                "supply_structure": result.supply_structure,
                "pricing_structure": result.pricing_structure,
                "producer_npv": result.producer_npv,
                "consumer_npv": result.consumer_npv,
                "total_volume_mwh": result.total_volume_mwh,
                "average_strike_eur_mwh": result.average_strike_eur_mwh,
                "capture_rate": result.capture_rate,
                "volume_value": result.volume_value,
                "profile_value": result.profile_value,
            })

    return pd.DataFrame(results)
