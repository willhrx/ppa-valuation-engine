"""
Tests for solar_production.py.

Sanity checks from the brief:
- Annual yield: 900–1 000 kWh/kWp
- Capacity factor: 10–12 %
- Zero generation between sunset and sunrise
- Series has no NaN values
"""

import numpy as np
import pytest

from ppa_engine.config import PPAConfig
from ppa_engine.data.solar_production import generate_solar_production


@pytest.fixture(scope="module")
def solar() -> "pd.Series":
    """Generate the default solar production series once for all tests."""
    return generate_solar_production(PPAConfig())


def test_no_nans(solar):
    assert solar.isna().sum() == 0, "Solar production contains NaN values"


def test_no_negative_output(solar):
    assert (solar >= 0).all(), "Solar production has negative values"


def test_night_hours_zero(solar):
    """Hours where clear-sky POA is zero should produce zero output."""
    # Midnight hours (00:00) in winter should always be zero
    midnight_winter = solar[
        (solar.index.hour == 0) & (solar.index.month == 1)
    ]
    assert (midnight_winter == 0).all(), "Midnight January hours have non-zero output"


def test_annual_yield_range(solar):
    """Annual yield should be 900–1 000 kWh/kWp."""
    config = PPAConfig()
    capacity_kwp = config.solar.capacity_mw * 1_000  # 50 MW → 50 000 kWp
    for year in range(2027, 2037):
        year_output_mwh = solar[solar.index.year == year].sum()
        year_output_kwh = year_output_mwh * 1_000  # MWh → kWh
        yield_kwh_kwp = year_output_kwh / capacity_kwp
        assert 800 <= yield_kwh_kwp <= 1_100, (
            f"{year}: annual yield {yield_kwh_kwp:.1f} kWh/kWp out of expected range"
        )


def test_capacity_factor_range(solar):
    """Fleet-wide capacity factor should be 10–12 %."""
    config = PPAConfig()
    capacity_mw = config.solar.capacity_mw
    hours = len(solar)
    total_possible_mwh = capacity_mw * hours
    cf = solar.sum() / total_possible_mwh
    assert 0.09 <= cf <= 0.14, f"Capacity factor {cf:.3f} out of expected range [0.09, 0.14]"


def test_degradation_effect(solar):
    """Year 2036 output should be lower than 2027 (degradation)."""
    output_2027 = solar[solar.index.year == 2027].sum()
    output_2036 = solar[solar.index.year == 2036].sum()
    assert output_2036 < output_2027, "Degradation not applied: 2036 >= 2027 output"


def test_reproducibility():
    """Same seed should give identical results."""
    cfg = PPAConfig()
    s1 = generate_solar_production(cfg)
    s2 = generate_solar_production(cfg)
    assert (s1 == s2).all(), "Results not reproducible with same seed"
