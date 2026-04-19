"""Tests for monte_carlo.py (Phase 3). Uses n_paths=10 to keep runtime <30s."""

import numpy as np
import pytest

from ppa_engine.config import PPAConfig
from ppa_engine.risk.monte_carlo import MonteCarloResult, run_monte_carlo
from ppa_engine.valuation.engine import value_all_combinations
from ppa_engine.data.market_prices import generate_market_prices
from ppa_engine.data.solar_production import generate_solar_production
from ppa_engine.data.consumer_load import generate_consumer_load


@pytest.fixture(scope="module")
def mc_small():
    """Run a small MC (10 paths) once for all tests in this module."""
    cfg = PPAConfig()
    return run_monte_carlo(cfg, n_paths=10, base_strike=65.0, verbose=False)


def test_paths_df_shape(mc_small):
    # 10 paths × 3 modes × 12 combinations = 360 rows
    assert mc_small.paths_df.shape[0] == 10 * 3 * 12


def test_paths_df_columns(mc_small):
    required = {
        "mode", "path", "supply_structure", "pricing_structure",
        "producer_npv", "consumer_npv", "total_volume_mwh",
        "average_strike_eur_mwh", "capture_rate",
    }
    assert required.issubset(set(mc_small.paths_df.columns))


def test_central_df_shape(mc_small):
    assert mc_small.central_df.shape[0] == 12


def test_zero_sum_per_path(mc_small):
    tol = 1.0  # EUR
    violations = mc_small.paths_df.query("abs(producer_npv + consumer_npv) > @tol")
    assert len(violations) == 0, f"{len(violations)} zero-sum violations found"


def test_central_df_matches_direct_engine(mc_small):
    cfg = mc_small.config
    solar = generate_solar_production(cfg)
    prices = generate_market_prices(cfg)
    load = generate_consumer_load(cfg)
    direct = value_all_combinations(solar, load, prices, cfg, base_strike=mc_small.base_strike)
    # Producer NPVs should match within EUR 1 (floating-point only)
    for _, row in mc_small.central_df.iterrows():
        direct_row = direct[
            (direct.supply_structure == row.supply_structure)
            & (direct.pricing_structure == row.pricing_structure)
        ].iloc[0]
        assert abs(row.producer_npv - direct_row.producer_npv) < 1.0


def test_price_mode_has_constant_volume(mc_small):
    # In 'price' mode, solar is fixed → total_volume_mwh must be identical per combination
    for (supply, pricing), grp in mc_small.paths_df[
        mc_small.paths_df["mode"] == "price"
    ].groupby(["supply_structure", "pricing_structure"]):
        vols = grp["total_volume_mwh"].values
        assert np.allclose(vols, vols[0], rtol=1e-6), (
            f"Volume varies in price-only mode for {supply}/{pricing}"
        )


def test_volume_mode_has_constant_fixed_flat_strike(mc_small):
    # In 'volume' mode, prices are fixed → FixedFlat average strike must be constant
    df = mc_small.paths_df[
        (mc_small.paths_df["mode"] == "volume")
        & (mc_small.paths_df["pricing_structure"] == "FixedFlat")
    ]
    for supply, grp in df.groupby("supply_structure"):
        strikes = grp["average_strike_eur_mwh"].values
        assert np.allclose(strikes, strikes[0], rtol=1e-6), (
            f"FixedFlat strike varies in volume-only mode for {supply}"
        )


def test_modes_present(mc_small):
    modes = set(mc_small.paths_df["mode"].unique())
    assert modes == {"joint", "price", "volume"}


def test_n_paths_attribute(mc_small):
    assert mc_small.n_paths == 10


def test_single_mode_run():
    cfg = PPAConfig()
    mc = run_monte_carlo(cfg, n_paths=5, base_strike=65.0, modes=["joint"], verbose=False)
    assert set(mc.paths_df["mode"].unique()) == {"joint"}
    assert mc.paths_df.shape[0] == 5 * 12
