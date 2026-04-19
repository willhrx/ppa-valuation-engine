"""
monte_carlo.py — 1,000-path Monte Carlo orchestrator (Phase 3).

For each path:
  1. Draw an independent price path (AR(1) residuals around the central scenario)
  2. Draw an independent production path (cloud factor re-seeded)
  3. Combine via all 12 supply × pricing structure combinations
  4. Compute NPV for each combination

Three ensembles support risk decomposition:
  'joint'  — both price and solar seeds perturbed independently
  'price'  — only price seed perturbed; solar fixed at central scenario
  'volume' — only solar seed perturbed; prices fixed at central scenario

Variance decomposition uses the three-ensemble method:
  V_joint = V_price + V_volume + interaction_term
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ppa_engine.config import PPAConfig
from ppa_engine.data.consumer_load import generate_consumer_load
from ppa_engine.data.market_prices import (
    _build_timestamps,
    _layer1_level,
    _layer2_seasonal,
    _layer3_intraday,
    _layer4_cannibalisation,
)
from ppa_engine.data.solar_production import _clearsky_poa
from ppa_engine.valuation.engine import value_all_combinations

# Seed base values for each ensemble — widely separated so per-path offsets
# (i * _PATH_PRIME) never produce collisions across ensembles
_JOINT_SOLAR_BASE = 101_000
_JOINT_PRICE_BASE = 202_000
_PRICE_PRICE_BASE = 303_000
_VOLUME_SOLAR_BASE = 404_000
_PATH_PRIME = 1_000_003  # Large prime for per-path derivation


@dataclass
class MonteCarloResult:
    """
    Container for Monte Carlo simulation outputs.

    Attributes
    ----------
    paths_df : pd.DataFrame
        Long-form DataFrame. Columns:
            mode, path, supply_structure, pricing_structure,
            producer_npv, consumer_npv, total_volume_mwh,
            average_strike_eur_mwh, capture_rate, volume_value, profile_value
        Total rows: len(modes) * n_paths * 12 combinations.
    central_df : pd.DataFrame
        12-row output from value_all_combinations() at base seeds.
    n_paths : int
        Paths per ensemble.
    base_strike : float
        Strike used for FixedFlat and FixedEscalated pricing structures.
    config : PPAConfig
    elapsed_seconds : float
    """

    paths_df: pd.DataFrame
    central_df: pd.DataFrame
    n_paths: int
    base_strike: float
    config: PPAConfig
    elapsed_seconds: float


# ---------------------------------------------------------------------------
# Internal path generators
# ---------------------------------------------------------------------------


def _solar_series(
    times: pd.DatetimeIndex,
    poa_clearsky: np.ndarray,
    degradation: np.ndarray,
    config: PPAConfig,
    seed: int,
) -> pd.Series:
    """Generate one solar production path for a given seed."""
    from scipy.special import expit, logit

    sc = config.solar
    T = len(times)
    phi = sc.cloud_factor_phi
    scale = sc.cloud_factor_logit_scale
    sigma_innov = np.sqrt(1.0 - phi * phi)

    monthly_logit = np.array([logit(m) for m in sc.monthly_cloud_means])
    hour_logit_mean = monthly_logit[np.array([t.month - 1 for t in times])]

    rng = np.random.default_rng(seed)
    eps = rng.standard_normal(T)
    z = np.empty(T)
    z[0] = eps[0]
    for t in range(1, T):
        z[t] = phi * z[t - 1] + sigma_innov * eps[t]

    cloud = expit(hour_logit_mean + scale * z)
    out = (
        sc.capacity_mw
        * sc.performance_ratio
        * (poa_clearsky * cloud / 1000.0)
        * degradation
    )
    return pd.Series(out, index=times, name="solar_production_mwh")


def _price_series(
    times: pd.DatetimeIndex,
    deterministic_layers: np.ndarray,
    config: PPAConfig,
    seed: int,
) -> pd.Series:
    """Generate one price path for a given seed."""
    mc = config.market
    T = len(times)
    phi = mc.ar1_phi
    sigma = mc.ar1_sigma
    sigma_innov = sigma * np.sqrt(1.0 - phi * phi)

    rng = np.random.default_rng(seed)
    eps = rng.standard_normal(T)
    noise = np.empty(T)
    noise[0] = sigma * eps[0]
    for t in range(1, T):
        noise[t] = phi * noise[t - 1] + sigma_innov * eps[t]

    return pd.Series(
        deterministic_layers + noise, index=times, name="market_price_eur_mwh"
    )


# ---------------------------------------------------------------------------
# Ensemble runner
# ---------------------------------------------------------------------------


def _run_ensemble(
    mode: str,
    times: pd.DatetimeIndex,
    poa_clearsky: np.ndarray,
    degradation: np.ndarray,
    deterministic_price: np.ndarray,
    load: pd.Series,
    config: PPAConfig,
    n_paths: int,
    base_strike: float,
    central_solar: pd.Series,
    central_prices: pd.Series,
    verbose: bool,
) -> pd.DataFrame:
    """
    Run n_paths for one decomposition mode.

    mode='joint'  — both seeds perturbed
    mode='price'  — only price seed perturbed; solar = central_solar
    mode='volume' — only solar seed perturbed; prices = central_prices
    """
    if verbose:
        print(f"  [{mode}] running {n_paths} paths...")

    t0 = time.time()
    rows: list[pd.DataFrame] = []

    for i in range(n_paths):
        if mode == "volume":
            solar = _solar_series(
                times, poa_clearsky, degradation, config,
                _VOLUME_SOLAR_BASE + i * _PATH_PRIME,
            )
            prices = central_prices
        elif mode == "price":
            solar = central_solar
            prices = _price_series(
                times, deterministic_price, config,
                _PRICE_PRICE_BASE + i * _PATH_PRIME,
            )
        else:  # joint
            solar = _solar_series(
                times, poa_clearsky, degradation, config,
                _JOINT_SOLAR_BASE + i * _PATH_PRIME,
            )
            prices = _price_series(
                times, deterministic_price, config,
                _JOINT_PRICE_BASE + i * _PATH_PRIME,
            )

        combo = value_all_combinations(solar, load, prices, config, base_strike=base_strike)
        combo["path"] = i
        combo["mode"] = mode
        rows.append(combo)

        if verbose and ((i + 1) % 100 == 0 or i == n_paths - 1):
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (n_paths - i - 1) / rate
            print(
                f"    path {i + 1:>4}/{n_paths}  "
                f"elapsed={elapsed:5.1f}s  rate={rate:.1f}p/s  eta={eta:.0f}s"
            )

    return pd.concat(rows, ignore_index=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_monte_carlo(
    config: PPAConfig | None = None,
    n_paths: int = 1000,
    base_strike: float = 65.0,
    modes: list[str] | None = None,
    verbose: bool = True,
) -> MonteCarloResult:
    """
    Run the full three-ensemble Monte Carlo simulation.

    Parameters
    ----------
    config : PPAConfig | None
        Uses DEFAULT_CONFIG if None.
    n_paths : int
        Paths per ensemble. Total rows in paths_df = n_paths * len(modes) * 12.
    base_strike : float
        Strike for FixedFlat and FixedEscalated pricing structures [EUR/MWh].
    modes : list[str] | None
        Subset of ['joint', 'price', 'volume']. Default: all three.
    verbose : bool
        Print progress to stdout.

    Returns
    -------
    MonteCarloResult

    Performance contract
    --------------------
    With n_paths=1000 and all three modes, total runtime is 40–60s on a modern
    laptop (dominated by 3,000 calls to value_all_combinations).
    Deterministic inputs (pvlib clear-sky, price layers 1–4) are computed once.

    Seed scheme (no collisions guaranteed by large prime offsets)
    -------------------------------------------------------------
    joint  mode: solar_seed_i = 101_000 + i*1_000_003
                 price_seed_i = 202_000 + i*1_000_003
    price  mode: price_seed_i = 303_000 + i*1_000_003
    volume mode: solar_seed_i = 404_000 + i*1_000_003
    """
    from ppa_engine.config import DEFAULT_CONFIG

    if config is None:
        config = DEFAULT_CONFIG
    if modes is None:
        modes = ["joint", "price", "volume"]

    t_start = time.time()

    # Step 1: build time index
    times = _build_timestamps(config)
    T = len(times)
    if verbose:
        print(f"Horizon: {times[0]} to {times[-1]}  ({T:,} hours)")

    # Step 2: cache deterministic inputs (pvlib is expensive — compute once)
    if verbose:
        print("  Caching deterministic inputs...")

    poa_clearsky = _clearsky_poa(times, config)

    start_year = pd.Timestamp(config.deal.start_date).year
    year_offset = np.array([t.year - start_year for t in times])
    degradation = 1.0 - config.solar.degradation_rate * year_offset

    deterministic_price = (
        _layer1_level(times, config)
        + _layer2_seasonal(times, config)
        + _layer3_intraday(times, config)
        + _layer4_cannibalisation(times, config)
    )

    load = generate_consumer_load(config)

    # Step 3: central scenario at base seeds
    if verbose:
        print("  Computing central scenario...")
    central_solar = _solar_series(
        times, poa_clearsky, degradation, config, config.solar.seed
    )
    central_prices = _price_series(
        times, deterministic_price, config, config.market.seed
    )
    central_df = value_all_combinations(
        central_solar, load, central_prices, config, base_strike=base_strike
    )

    # Step 4: run ensembles
    frames: list[pd.DataFrame] = []
    for mode in modes:
        df = _run_ensemble(
            mode, times, poa_clearsky, degradation, deterministic_price,
            load, config, n_paths, base_strike, central_solar, central_prices,
            verbose,
        )
        frames.append(df)

    paths_df = pd.concat(frames, ignore_index=True)
    elapsed = time.time() - t_start

    if verbose:
        print(
            f"\n  Done in {elapsed:.1f}s.  "
            f"Total: {len(paths_df):,} rows "
            f"({n_paths} paths × {len(modes)} modes × 12 combos)."
        )

    return MonteCarloResult(
        paths_df=paths_df,
        central_df=central_df,
        n_paths=n_paths,
        base_strike=base_strike,
        config=config,
        elapsed_seconds=elapsed,
    )
