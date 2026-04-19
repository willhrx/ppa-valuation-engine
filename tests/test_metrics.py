"""Tests for metrics.py (Phase 3)."""

import numpy as np
import pytest

from ppa_engine.risk.metrics import (
    VarianceDecomposition,
    decompose_risk,
    expected_shortfall,
    value_at_risk,
)


@pytest.fixture
def symmetric_npvs():
    rng = np.random.default_rng(42)
    return rng.normal(loc=1_000_000, scale=500_000, size=1000)


def test_var_is_5th_percentile(symmetric_npvs):
    var = value_at_risk(symmetric_npvs, confidence=0.95)
    assert abs(var - np.percentile(symmetric_npvs, 5.0)) < 1e-6


def test_es_below_var(symmetric_npvs):
    var = value_at_risk(symmetric_npvs)
    es = expected_shortfall(symmetric_npvs)
    assert es <= var, f"ES {es:.0f} must be <= VaR {var:.0f}"


def test_var_at_different_confidence():
    npvs = np.arange(1000, dtype=float)
    var_90 = value_at_risk(npvs, confidence=0.90)
    var_95 = value_at_risk(npvs, confidence=0.95)
    assert var_90 > var_95, "Higher confidence should give lower (worse) VaR"


def test_es_known_distribution():
    # Uniform [0, 100]: P5 = 5, ES(95%) = mean of [0, 5] = 2.5
    npvs = np.linspace(0, 100, 10_001)
    es = expected_shortfall(npvs, confidence=0.95)
    assert abs(es - 2.5) < 0.5


def test_decompose_risk_shares_sum_to_one():
    rng = np.random.default_rng(0)
    joint = rng.normal(0, 2, 500)
    price = rng.normal(0, 1.5, 500)
    volume = rng.normal(0, 0.8, 500)
    vd = decompose_risk(joint, price, volume)
    total = vd.price_share + vd.volume_share + vd.interaction_share
    assert abs(total - 1.0) < 1e-10


def test_decompose_risk_price_dominant():
    # When only price is stochastic, price_share should dominate
    rng = np.random.default_rng(1)
    price = rng.normal(0, 10, 500)
    volume = rng.normal(0, 0.1, 500)  # tiny volume noise
    joint = price + volume
    vd = decompose_risk(joint, price, volume)
    assert vd.price_share > 0.9, f"Price share too low: {vd.price_share:.3f}"


def test_decompose_risk_zero_variance_returns_zeros():
    constant = np.ones(100) * 5.0
    vd = decompose_risk(constant, constant, constant)
    assert vd.price_share == 0.0
    assert vd.volume_share == 0.0
    assert vd.interaction_share == 0.0


def test_interaction_can_be_negative():
    # Negatively correlated price and volume risks: joint variance < price + volume
    rng = np.random.default_rng(99)
    base = rng.normal(0, 1, 500)
    price = base + rng.normal(0, 0.5, 500)
    volume = -base + rng.normal(0, 0.5, 500)  # anti-correlated with price
    joint = price + volume
    vd = decompose_risk(joint, price, volume)
    assert vd.interaction_share < 0, (
        "Anti-correlated risks should give negative interaction_share"
    )
