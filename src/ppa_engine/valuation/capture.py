"""
capture.py — Capture-price decomposition (Phase 2, used in Phase 1 sanity checks).

The capture price is the volume-weighted average price received by a solar asset:

    capture_price = Σ_t [P(t) × Q(t)] / Σ_t Q(t)

where P(t) is the spot price and Q(t) is solar generation in hour t.

The capture rate is:

    capture_rate = capture_price / Σ_t P(t) / N

i.e., capture price divided by the simple time-weighted average price.

A capture rate below 1.0 means the solar asset systematically generates more
when prices are low (the cannibalisation / profile-risk effect).  For Dutch
solar, capture rates are in the 0.65–0.85 range and declining as penetration
grows.

This module also provides an annual time-series of capture rates so the
erosion trend over the PPA horizon is visible.
"""

from __future__ import annotations

import pandas as pd


def capture_price(market_prices: pd.Series, solar: pd.Series) -> float:
    """
    Return the energy-weighted average price received by the solar asset.

    Parameters
    ----------
    market_prices:
        Hourly spot prices [EUR/MWh].
    solar:
        Hourly solar AC output [MWh/h].

    Returns
    -------
    float
        Capture price in EUR/MWh.
    """
    generation_hours = solar > 0
    if not generation_hours.any():
        return float("nan")
    return float(
        (market_prices[generation_hours] * solar[generation_hours]).sum()
        / solar[generation_hours].sum()
    )


def capture_rate(market_prices: pd.Series, solar: pd.Series) -> float:
    """
    Return the ratio of capture price to the time-weighted average price.

    Values below 1.0 indicate the asset earns less than the average market price
    (profile risk / cannibalisation effect).
    """
    avg_price = float(market_prices.mean())
    if avg_price == 0:
        return float("nan")
    return capture_price(market_prices, solar) / avg_price


def annual_capture_rates(market_prices: pd.Series, solar: pd.Series) -> pd.Series:
    """
    Return a year-by-year Series of capture rates.

    Useful for visualising the decline in capture rate as solar penetration grows.

    Returns
    -------
    pd.Series
        Index: year (int), Values: capture rate (float).
    """
    years = market_prices.index.year.unique()
    rates = {}
    for year in sorted(years):
        mask = market_prices.index.year == year
        rates[year] = capture_rate(market_prices[mask], solar[mask])
    return pd.Series(rates, name="capture_rate")
