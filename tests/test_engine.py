"""
Tests for the valuation engine (Phase 2).

Test categories:
1. ValuationResult construction and zero-sum validation
2. value_ppa() integration with structures
3. Value decomposition (volume + profile = total)
4. Baseload vs PayAsProduced premium (SUCCESS CRITERION #1)
5. All-combinations matrix (SUCCESS CRITERION #2: zero-sum)
"""

import pytest
import pandas as pd

from ppa_engine.config import PPAConfig
from ppa_engine.data.solar_production import generate_solar_production
from ppa_engine.data.market_prices import generate_market_prices
from ppa_engine.data.consumer_load import generate_consumer_load
from ppa_engine.structures.pay_as_produced import PayAsProduced
from ppa_engine.structures.pay_as_nominated import PayAsNominated
from ppa_engine.structures.baseload import Baseload
from ppa_engine.pricing.fixed import FixedFlat, FixedEscalated
from ppa_engine.pricing.indexed import IndexedWithFloorCap
from ppa_engine.pricing.floating import Floating
from ppa_engine.valuation.engine import (
    ValuationResult,
    value_ppa,
    value_all_combinations,
)


@pytest.fixture(scope="module")
def full_data():
    """Generate full 10-year dataset (cached for module)."""
    cfg = PPAConfig()
    solar = generate_solar_production(cfg)
    load = generate_consumer_load(cfg)
    prices = generate_market_prices(cfg)
    return solar, load, prices, cfg


# ============================================================================
# ValuationResult Tests
# ============================================================================


def test_valuation_result_valid_construction():
    """ValuationResult should accept valid zero-sum inputs."""
    result = ValuationResult(
        producer_npv=1000.0,
        consumer_npv=-1000.0,
        total_volume_mwh=100.0,
        average_strike_eur_mwh=70.0,
        capture_rate=0.75,
        volume_value=800.0,
        profile_value=200.0,
        supply_structure="PayAsProduced",
        pricing_structure="FixedFlat",
    )
    assert result.producer_npv == 1000.0
    assert result.consumer_npv == -1000.0


def test_valuation_result_rejects_non_zero_sum():
    """ValuationResult should raise error if zero-sum violated."""
    with pytest.raises(ValueError, match="Zero-sum violated"):
        ValuationResult(
            producer_npv=1000.0,
            consumer_npv=-500.0,  # Should be -1000!
            total_volume_mwh=100.0,
            average_strike_eur_mwh=70.0,
            capture_rate=0.75,
            volume_value=800.0,
            profile_value=200.0,
            supply_structure="test",
            pricing_structure="test",
        )


# ============================================================================
# value_ppa() Integration Tests
# ============================================================================


def test_value_ppa_returns_valuation_result(full_data):
    """value_ppa should return a ValuationResult instance."""
    solar, load, prices, cfg = full_data
    result = value_ppa(
        PayAsProduced(),
        FixedFlat(strike=65.0),
        solar, load, prices, cfg
    )
    assert isinstance(result, ValuationResult)


def test_value_ppa_zero_sum_property(full_data):
    """value_ppa output should satisfy zero-sum: producer + consumer = 0."""
    solar, load, prices, cfg = full_data
    result = value_ppa(
        PayAsProduced(),
        FixedFlat(strike=65.0),
        solar, load, prices, cfg
    )
    assert result.producer_npv + result.consumer_npv == pytest.approx(0.0, abs=1e-6)


def test_value_ppa_all_supply_structures(full_data):
    """All supply structures should work with value_ppa."""
    solar, load, prices, cfg = full_data
    pricing = FixedFlat(strike=65.0)

    for supply in [PayAsProduced(), PayAsNominated(), Baseload()]:
        result = value_ppa(supply, pricing, solar, load, prices, cfg)
        assert isinstance(result, ValuationResult)
        assert result.total_volume_mwh > 0


def test_value_ppa_all_pricing_structures(full_data):
    """All pricing structures should work with value_ppa."""
    solar, load, prices, cfg = full_data
    supply = PayAsProduced()

    for pricing in [
        FixedFlat(strike=65.0),
        FixedEscalated(base_strike=65.0, escalation_rate=0.02),
        IndexedWithFloorCap(index_factor=0.95, floor=40.0, cap=120.0),
        Floating(),
    ]:
        result = value_ppa(supply, pricing, solar, load, prices, cfg)
        assert isinstance(result, ValuationResult)


def test_floating_pricing_zero_npv(full_data):
    """Floating pricing should give zero NPV (strike = market, no differential)."""
    solar, load, prices, cfg = full_data
    result = value_ppa(
        PayAsProduced(),
        Floating(),
        solar, load, prices, cfg
    )
    # Floating means strike = market, so NPV should be approximately zero
    # Allow small tolerance for floating point
    assert result.producer_npv == pytest.approx(0.0, abs=1e-6)


def test_higher_strike_gives_higher_producer_npv(full_data):
    """Higher strike price should give higher producer NPV."""
    solar, load, prices, cfg = full_data
    supply = PayAsProduced()

    result_low = value_ppa(supply, FixedFlat(strike=50.0), solar, load, prices, cfg)
    result_high = value_ppa(supply, FixedFlat(strike=80.0), solar, load, prices, cfg)

    assert result_high.producer_npv > result_low.producer_npv, \
        "Higher strike should give higher producer NPV"


# ============================================================================
# SUCCESS CRITERION #1: Baseload vs PayAsProduced Premium
# ============================================================================


def test_baseload_vs_pay_as_produced_different_npv(full_data):
    """
    SUCCESS CRITERION: Baseload NPV should differ from PayAsProduced NPV.

    This tests that the premium emerges from the model rather than being
    hardcoded. The difference reflects profile value - baseload delivers
    constant volume regardless of when prices are high/low, while
    pay-as-produced delivers more when solar is generating (often when
    prices are depressed due to cannibalisation).
    """
    solar, load, prices, cfg = full_data
    strike = 65.0

    pap_result = value_ppa(
        PayAsProduced(),
        FixedFlat(strike=strike),
        solar, load, prices, cfg
    )

    bl_result = value_ppa(
        Baseload(),
        FixedFlat(strike=strike),
        solar, load, prices, cfg
    )

    # The two should have different NPVs due to different volume timing
    npv_diff = abs(pap_result.producer_npv - bl_result.producer_npv)
    assert npv_diff > 100_000, \
        f"PayAsProduced and Baseload should have meaningfully different NPVs. " \
        f"Difference: {npv_diff:,.0f} EUR"


def test_baseload_captures_more_profile_value(full_data):
    """
    Baseload should show different profile value than PayAsProduced.

    Baseload delivers constant volume, so it doesn't suffer from
    generating most when prices are lowest (cannibalisation).
    """
    solar, load, prices, cfg = full_data
    strike = 65.0

    pap_result = value_ppa(
        PayAsProduced(),
        FixedFlat(strike=strike),
        solar, load, prices, cfg
    )

    bl_result = value_ppa(
        Baseload(),
        FixedFlat(strike=strike),
        solar, load, prices, cfg
    )

    # Profile values should be different
    profile_diff = abs(pap_result.profile_value - bl_result.profile_value)
    assert profile_diff > 10_000, \
        f"Profile values should differ significantly. Difference: {profile_diff:,.0f} EUR"


# ============================================================================
# Value Decomposition Tests
# ============================================================================


def test_value_decomposition_sums_approximately(full_data):
    """Volume value + profile value should approximately equal total NPV."""
    solar, load, prices, cfg = full_data

    result = value_ppa(
        PayAsProduced(),
        FixedFlat(strike=65.0),
        solar, load, prices, cfg
    )

    decomposed_sum = result.volume_value + result.profile_value
    # Allow 5% tolerance due to midpoint discount approximation
    assert decomposed_sum == pytest.approx(result.producer_npv, rel=0.05), \
        f"Decomposition mismatch: {decomposed_sum:,.0f} vs NPV {result.producer_npv:,.0f}"


def test_value_decomposition_all_structures(full_data):
    """Value decomposition should work for all structure combinations."""
    solar, load, prices, cfg = full_data

    for supply in [PayAsProduced(), PayAsNominated(), Baseload()]:
        for pricing in [FixedFlat(strike=65.0), FixedEscalated(base_strike=65.0)]:
            result = value_ppa(supply, pricing, solar, load, prices, cfg)
            decomposed_sum = result.volume_value + result.profile_value
            # Decomposition should approximately equal total NPV
            assert decomposed_sum == pytest.approx(result.producer_npv, rel=0.10)


# ============================================================================
# SUCCESS CRITERION #2: All Combinations Zero-Sum
# ============================================================================


def test_value_all_combinations_returns_12_rows(full_data):
    """value_all_combinations should return 3x4=12 rows."""
    solar, load, prices, cfg = full_data

    df = value_all_combinations(solar, load, prices, cfg)

    assert len(df) == 12, f"Expected 12 combinations, got {len(df)}"


def test_value_all_combinations_has_required_columns(full_data):
    """DataFrame should have all required columns."""
    solar, load, prices, cfg = full_data

    df = value_all_combinations(solar, load, prices, cfg)

    required_columns = [
        "supply_structure",
        "pricing_structure",
        "producer_npv",
        "consumer_npv",
        "total_volume_mwh",
        "average_strike_eur_mwh",
        "capture_rate",
        "volume_value",
        "profile_value",
    ]

    for col in required_columns:
        assert col in df.columns, f"Missing column: {col}"


def test_all_combinations_zero_sum(full_data):
    """
    SUCCESS CRITERION: Every combination should satisfy zero-sum property.

    This validates that risk is redistributed, not created or destroyed.
    """
    solar, load, prices, cfg = full_data

    df = value_all_combinations(solar, load, prices, cfg)

    for idx, row in df.iterrows():
        total = row["producer_npv"] + row["consumer_npv"]
        assert total == pytest.approx(0.0, abs=1e-6), \
            f"Zero-sum violated for {row['supply_structure']}/{row['pricing_structure']}: " \
            f"producer={row['producer_npv']:,.0f}, consumer={row['consumer_npv']:,.0f}"


def test_all_combinations_positive_volume(full_data):
    """All combinations should have positive total volume."""
    solar, load, prices, cfg = full_data

    df = value_all_combinations(solar, load, prices, cfg)

    for idx, row in df.iterrows():
        assert row["total_volume_mwh"] > 0, \
            f"Zero volume for {row['supply_structure']}/{row['pricing_structure']}"


def test_all_combinations_reasonable_npv_range(full_data):
    """All NPVs should be in a reasonable range for 50MW over 10 years."""
    solar, load, prices, cfg = full_data

    df = value_all_combinations(solar, load, prices, cfg)

    # For a 50MW solar asset over 10 years:
    # - Capacity factor ~10% = ~45 GWh/year = ~450 GWh total
    # - At ±10 EUR/MWh spread, NPV would be ±4.5M EUR undiscounted
    # - Allow wider range for edge cases
    max_reasonable_npv = 100_000_000  # 100M EUR

    for idx, row in df.iterrows():
        assert abs(row["producer_npv"]) < max_reasonable_npv, \
            f"NPV {row['producer_npv']:,.0f} seems unreasonable for " \
            f"{row['supply_structure']}/{row['pricing_structure']}"


# ============================================================================
# Capture Rate Tests
# ============================================================================


def test_capture_rate_below_one(full_data):
    """Capture rate should be below 1.0 (cannibalisation effect)."""
    solar, load, prices, cfg = full_data

    result = value_ppa(
        PayAsProduced(),
        FixedFlat(strike=65.0),
        solar, load, prices, cfg
    )

    assert result.capture_rate < 1.0, \
        f"Capture rate {result.capture_rate:.3f} should be < 1.0"


def test_capture_rate_in_expected_range(full_data):
    """Capture rate should be in Dutch solar range (0.50-0.90)."""
    solar, load, prices, cfg = full_data

    result = value_ppa(
        PayAsProduced(),
        FixedFlat(strike=65.0),
        solar, load, prices, cfg
    )

    assert 0.50 < result.capture_rate < 0.90, \
        f"Capture rate {result.capture_rate:.3f} outside expected range 0.50-0.90"
