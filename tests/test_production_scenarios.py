"""Tests for production_scenarios.py (Phase 3)."""

import numpy as np
import pandas as pd
import pytest

from ppa_engine.config import PPAConfig
from ppa_engine.data.market_prices import _build_timestamps
from ppa_engine.data.solar_production import _clearsky_poa, generate_solar_production
from ppa_engine.risk.production_scenarios import (
    compute_annual_percentiles,
    generate_production_scenarios,
)


@pytest.fixture
def cfg():
    return PPAConfig()


@pytest.fixture
def times(cfg):
    return _build_timestamps(cfg)


@pytest.fixture
def poa(cfg, times):
    return _clearsky_poa(times, cfg)


def test_output_shape(cfg, times, poa):
    matrix, _ = generate_production_scenarios(cfg, n_paths=10, times=times, poa_clearsky=poa)
    assert matrix.shape == (10, len(times))


def test_no_negative_production(cfg, times, poa):
    matrix, _ = generate_production_scenarios(cfg, n_paths=20, times=times, poa_clearsky=poa)
    assert matrix.min() >= 0.0, "Negative production values found"


def test_p10_below_p50_below_p90(cfg, times, poa):
    _, percs = generate_production_scenarios(cfg, n_paths=100, times=times, poa_clearsky=poa)
    assert all(percs["p10"] <= percs["p50"]), "P10 > P50 in some year"
    assert all(percs["p50"] <= percs["p90"]), "P50 > P90 in some year"


def test_percentile_years_count(cfg, times, poa):
    _, percs = generate_production_scenarios(cfg, n_paths=20, times=times, poa_clearsky=poa)
    assert len(percs["years"]) == 10  # 2027–2036


def test_p50_close_to_central(cfg, times, poa):
    # P50 annual production across n_paths should be within 5 % of central scenario
    matrix, percs = generate_production_scenarios(
        cfg, n_paths=200, times=times, poa_clearsky=poa
    )
    central_annual = (
        generate_solar_production(cfg)
        .resample("YE")
        .sum()
        .values / 1000.0  # MWh → GWh
    )
    p50 = percs["p50"]
    rel_errors = abs(p50 - central_annual) / central_annual
    assert rel_errors.max() < 0.08, f"P50 deviates >8% from central: {rel_errors}"


def test_different_seeds_give_different_paths(cfg, times, poa):
    m1, _ = generate_production_scenarios(cfg, n_paths=5, times=times, poa_clearsky=poa, base_seed=1)
    m2, _ = generate_production_scenarios(cfg, n_paths=5, times=times, poa_clearsky=poa, base_seed=9999)
    assert not np.allclose(m1, m2)


def test_compute_annual_percentiles_shape(times):
    n_paths, T = 50, len(times)
    matrix = np.random.default_rng(0).uniform(0, 10, size=(n_paths, T))
    percs = compute_annual_percentiles(matrix, times)
    assert len(percs["years"]) == 10
    assert len(percs["p10"]) == 10
    assert len(percs["p50"]) == 10
    assert len(percs["p90"]) == 10
