"""
Tests for the NPV calculator (Phase 2).

Test categories:
1. Basic functionality: known inputs -> known outputs
2. Edge cases: empty series, single hour, all zeros
3. Discount rate sensitivity: higher rate -> lower NPV
4. Time structure: front-loaded cash flows worth more
5. Integration with full horizon data
"""

import numpy as np
import pandas as pd
import pytest

from ppa_engine.config import PPAConfig
from ppa_engine.valuation.npv import compute_npv


@pytest.fixture
def simple_data():
    """Create simple test data: 100 hours, constant values."""
    idx = pd.date_range("2027-01-01", periods=100, freq="h", tz="Europe/Amsterdam")
    volume = pd.Series(10.0, index=idx)   # 10 MWh/h
    strike = pd.Series(70.0, index=idx)   # 70 EUR/MWh
    market = pd.Series(60.0, index=idx)   # 60 EUR/MWh
    return volume, strike, market


def test_npv_positive_when_strike_above_market(simple_data):
    """When strike > market, producer NPV should be positive."""
    volume, strike, market = simple_data
    npv = compute_npv(volume, strike, market)
    assert npv > 0, f"Expected positive NPV, got {npv}"


def test_npv_negative_when_strike_below_market(simple_data):
    """When strike < market, producer NPV should be negative."""
    volume, strike, market = simple_data
    strike_low = pd.Series(50.0, index=strike.index)
    npv = compute_npv(volume, strike_low, market)
    assert npv < 0, f"Expected negative NPV, got {npv}"


def test_npv_zero_when_strike_equals_market(simple_data):
    """When strike = market exactly, NPV should be zero."""
    volume, strike, market = simple_data
    npv = compute_npv(volume, market, market)  # strike = market
    assert abs(npv) < 1e-10, f"Expected zero NPV, got {npv}"


def test_npv_scales_with_volume(simple_data):
    """Doubling volume should approximately double NPV."""
    volume, strike, market = simple_data
    npv1 = compute_npv(volume, strike, market)
    npv2 = compute_npv(volume * 2, strike, market)
    ratio = npv2 / npv1
    assert abs(ratio - 2.0) < 0.01, f"NPV should double: ratio = {ratio}"


def test_npv_scales_with_price_spread(simple_data):
    """Doubling the price spread should double NPV."""
    volume, strike, market = simple_data
    # Original spread: 70 - 60 = 10
    npv1 = compute_npv(volume, strike, market)
    # Double spread: 80 - 60 = 20
    strike_double = pd.Series(80.0, index=strike.index)
    npv2 = compute_npv(volume, strike_double, market)
    ratio = npv2 / npv1
    assert abs(ratio - 2.0) < 0.01, f"NPV should double with spread: ratio = {ratio}"


def test_npv_empty_series():
    """Empty series should return zero NPV."""
    idx = pd.DatetimeIndex([], tz="Europe/Amsterdam")
    volume = pd.Series([], index=idx, dtype=float)
    strike = pd.Series([], index=idx, dtype=float)
    market = pd.Series([], index=idx, dtype=float)
    npv = compute_npv(volume, strike, market)
    assert npv == 0.0


def test_npv_single_hour():
    """Single hour should compute correctly."""
    idx = pd.date_range("2027-01-01", periods=1, freq="h", tz="Europe/Amsterdam")
    volume = pd.Series([10.0], index=idx)   # 10 MWh
    strike = pd.Series([70.0], index=idx)   # 70 EUR/MWh
    market = pd.Series([60.0], index=idx)   # 60 EUR/MWh

    # Cash flow = 10 * (70 - 60) = 100 EUR
    # At t=0, discount factor = 1.0
    npv = compute_npv(volume, strike, market)
    assert abs(npv - 100.0) < 0.01, f"Expected ~100 EUR, got {npv}"


def test_npv_discount_effect():
    """Cash flows later in a contract should contribute less to NPV than earlier ones."""
    # Create a 10-year series where we can compare year 1 vs year 10 contributions
    # Strategy: First compute NPV with cash flows only in year 1, then only in year 10

    # Full 10-year index
    idx_full = pd.date_range("2027-01-01", periods=8760 * 10, freq="h", tz="Europe/Amsterdam")

    # Cash flows only in Year 1 (hours 0-8759)
    volume_y1_only = pd.Series(0.0, index=idx_full)
    volume_y1_only.iloc[:8760] = 10.0  # 10 MWh/h in Year 1 only

    # Cash flows only in Year 10 (hours ~78840-87599)
    volume_y10_only = pd.Series(0.0, index=idx_full)
    volume_y10_only.iloc[-8760:] = 10.0  # 10 MWh/h in Year 10 only

    strike = pd.Series(70.0, index=idx_full)
    market = pd.Series(60.0, index=idx_full)

    npv_y1_only = compute_npv(volume_y1_only, strike, market)
    npv_y10_only = compute_npv(volume_y10_only, strike, market)

    # Year 1 cash flows should be worth more (less discounting)
    assert npv_y1_only > npv_y10_only, \
        f"Year 1 NPV ({npv_y1_only:.0f}) should exceed Year 10 NPV ({npv_y10_only:.0f})"

    # At 6% discount rate, 9 years of discounting: (1.06)^9 ~ 1.69
    # Year 10 value should be roughly 1/1.69 = 0.59 of Year 1 value
    ratio = npv_y10_only / npv_y1_only
    expected_ratio = 1 / (1.06 ** 9)  # ~0.59
    assert abs(ratio - expected_ratio) < 0.05, \
        f"Discount ratio {ratio:.3f} differs from expected {expected_ratio:.3f}"


def test_npv_with_custom_discount_rate(simple_data):
    """Higher discount rate should reduce NPV for positive cash flows."""
    volume, strike, market = simple_data

    cfg_low = PPAConfig()
    cfg_low.deal.discount_rate = 0.03

    cfg_high = PPAConfig()
    cfg_high.deal.discount_rate = 0.10

    npv_low = compute_npv(volume, strike, market, cfg_low)
    npv_high = compute_npv(volume, strike, market, cfg_high)

    assert npv_low > npv_high, f"Lower rate NPV ({npv_low:.2f}) should exceed higher rate ({npv_high:.2f})"


def test_npv_zero_discount_rate(simple_data):
    """Zero discount rate should give undiscounted sum."""
    volume, strike, market = simple_data

    cfg = PPAConfig()
    cfg.deal.discount_rate = 0.0

    npv = compute_npv(volume, strike, market, cfg)

    # Undiscounted: 100 hours * 10 MWh * (70 - 60) EUR/MWh = 10,000 EUR
    expected = 100 * 10 * 10
    assert abs(npv - expected) < 0.01, f"Expected {expected}, got {npv}"


def test_npv_negative_prices():
    """NPV should handle negative market prices correctly."""
    idx = pd.date_range("2027-01-01", periods=100, freq="h", tz="Europe/Amsterdam")
    volume = pd.Series(10.0, index=idx)
    strike = pd.Series(50.0, index=idx)    # Fixed at 50
    market = pd.Series(-20.0, index=idx)   # Negative prices

    # Producer gets strike (50) instead of negative spot (-20)
    # Cash flow = 10 * (50 - (-20)) = 10 * 70 = 700 EUR/h
    npv = compute_npv(volume, strike, market)

    assert npv > 0, "Producer should benefit when market goes negative"
    # Rough check: 100 hours * 700 EUR/h * avg discount ~ 70,000 * ~0.999 ~ 69,900
    assert 69000 < npv < 71000, f"NPV {npv} outside expected range"


def test_npv_full_horizon():
    """Test NPV calculation over the full 10-year horizon with generated data."""
    from ppa_engine.data.solar_production import generate_solar_production
    from ppa_engine.data.market_prices import generate_market_prices
    from ppa_engine.pricing.fixed import FixedFlat

    cfg = PPAConfig()
    solar = generate_solar_production(cfg)
    prices = generate_market_prices(cfg)
    strikes = FixedFlat(strike=65.0).strike_price(prices)

    npv = compute_npv(solar, strikes, prices, cfg)

    # Sanity check: NPV should be in a reasonable range for 50MW over 10 years
    # At ~10% capacity factor, ~45 GWh/year, 450 GWh total
    # At 5-10 EUR/MWh spread, undiscounted would be 2-5M EUR
    # Discounted should be lower but still in millions range
    assert -50_000_000 < npv < 50_000_000, f"NPV {npv:,.0f} seems unreasonable"

    # Also check it's not zero (would indicate a bug)
    assert abs(npv) > 1000, f"NPV {npv} suspiciously close to zero"
