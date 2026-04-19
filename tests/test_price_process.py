"""Tests for price_process.py (Phase 3)."""

import numpy as np
import pandas as pd
import pytest

from ppa_engine.config import PPAConfig
from ppa_engine.data.market_prices import _build_timestamps
from ppa_engine.risk.price_process import (
    _ar1_noise_matrix,
    build_deterministic_price,
    simulate_price_paths,
)


@pytest.fixture
def cfg():
    return PPAConfig()


@pytest.fixture
def times(cfg):
    return _build_timestamps(cfg)


def test_output_shape(cfg, times):
    result = simulate_price_paths(cfg, n_paths=10, times=times)
    assert result.shape == (10, len(times))


def test_single_path_dtype(cfg, times):
    result = simulate_price_paths(cfg, n_paths=1, times=times)
    assert result.dtype == np.float64


def test_deterministic_layer_reused(cfg, times):
    det = build_deterministic_price(times, cfg)
    r1 = simulate_price_paths(cfg, n_paths=5, times=times, deterministic_layers=det)
    r2 = simulate_price_paths(cfg, n_paths=5, times=times, deterministic_layers=det)
    np.testing.assert_array_equal(r1, r2)


def test_different_seeds_give_different_paths(cfg, times):
    r1 = simulate_price_paths(cfg, n_paths=3, times=times, base_seed=1)
    r2 = simulate_price_paths(cfg, n_paths=3, times=times, base_seed=9999)
    assert not np.allclose(r1, r2)


def test_paths_are_independent(cfg, times):
    # Rows of the noise matrix should be uncorrelated across paths
    T = len(times)
    noise = _ar1_noise_matrix(T, 200, cfg.market.ar1_phi, cfg.market.ar1_sigma, 42)
    # Cross-path correlation between first two paths should be near zero
    corr = float(np.corrcoef(noise[0], noise[1])[0, 1])
    assert abs(corr) < 0.15, f"Paths too correlated: {corr:.3f}"


def test_stationary_std(cfg, times):
    # Column-wise std should converge to ar1_sigma
    noise = _ar1_noise_matrix(
        len(times), 500, cfg.market.ar1_phi, cfg.market.ar1_sigma, 0
    )
    col_std = noise.std(axis=0)
    target = cfg.market.ar1_sigma
    # Mean column std should be within 15 % of target
    assert abs(col_std.mean() / target - 1.0) < 0.15


def test_sigma_param_affects_output(cfg, times):
    from copy import deepcopy
    cfg2 = deepcopy(cfg)
    cfg2.market.ar1_sigma = cfg.market.ar1_sigma * 2.0
    r1 = simulate_price_paths(cfg, n_paths=50, times=times, base_seed=7)
    r2 = simulate_price_paths(cfg2, n_paths=50, times=times, base_seed=7)
    # Higher sigma → higher variance
    assert r2.std() > r1.std()


def test_price_levels_reasonable(cfg, times):
    paths = simulate_price_paths(cfg, n_paths=100, times=times)
    mean_price = paths.mean()
    # Dutch day-ahead prices in 2027–2036 should average roughly 60–90 EUR/MWh
    assert 40.0 < mean_price < 120.0, f"Unrealistic mean price: {mean_price:.1f}"
