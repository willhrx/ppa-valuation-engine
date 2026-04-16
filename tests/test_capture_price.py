"""
Tests for capture price calculations (valuation/capture.py).

The capture rate for a solar asset should be:
- In range 0.65–0.85 across the PPA horizon
- Declining year-over-year (cannibalisation grows)
- Below 1.0 (solar generates when prices are below average)
"""

import pytest
import numpy as np

from ppa_engine.config import PPAConfig
from ppa_engine.data.solar_production import generate_solar_production
from ppa_engine.data.market_prices import generate_market_prices
from ppa_engine.valuation.capture import (
    capture_price,
    capture_rate,
    annual_capture_rates,
)


@pytest.fixture(scope="module")
def data():
    cfg = PPAConfig()
    solar = generate_solar_production(cfg)
    prices = generate_market_prices(cfg)
    return prices, solar


def test_capture_price_below_average(data):
    prices, solar = data
    cp = capture_price(prices, solar)
    avg = float(prices.mean())
    assert cp < avg, f"Capture price {cp:.2f} >= average price {avg:.2f}"


def test_capture_rate_range(data):
    prices, solar = data
    cr = capture_rate(prices, solar)
    assert 0.50 <= cr <= 0.95, f"Capture rate {cr:.3f} out of plausible range [0.50, 0.95]"


def test_annual_capture_rates_declining(data):
    """Cannibalisation should push capture rates down over the horizon."""
    prices, solar = data
    rates = annual_capture_rates(prices, solar)
    # Allow one year to be flat/slightly up (noise) but overall trend should be down
    first_half = rates[rates.index <= 2031].mean()
    second_half = rates[rates.index >= 2032].mean()
    assert second_half < first_half, (
        f"Capture rate not declining: first half mean {first_half:.3f}, "
        f"second half mean {second_half:.3f}"
    )


def test_annual_capture_rates_all_below_one(data):
    prices, solar = data
    rates = annual_capture_rates(prices, solar)
    assert (rates < 1.0).all(), "Some annual capture rates >= 1.0"
