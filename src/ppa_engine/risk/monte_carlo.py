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

import logging
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
    _layer3a_demand,
    _layer3b_wind_supply,
    _layer4_cannibalisation,
    compute_system_solar_proxy,
    compute_wind_factor,
)
from ppa_engine.data.solar_production import _clearsky_poa, compute_cloud_factor
from ppa_engine.utils.ar1 import ar1_process
from ppa_engine.valuation.engine import value_all_combinations

logger = logging.getLogger(__name__)

# Seed base values for each ensemble — widely separated so per-path offsets
# (i * _PATH_PRIME) never produce collisions across ensembles
_JOINT_SOLAR_BASE = 101_000
_JOINT_PRICE_BASE = 202_000
_PRICE_PRICE_BASE = 303_000
_VOLUME_SOLAR_BASE = 404_000
_JOINT_WIND_BASE = 505_000
_PRICE_WIND_BASE = 606_000
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


def _cloud_series(
    times: pd.DatetimeIndex,
    config: PPAConfig,
    seed: int,
) -> np.ndarray:
    """Per-path cloud factor — re-used by both solar and (layer 4) prices."""
    return compute_cloud_factor(times, config, seed=seed)


def _wind_series(
    times: pd.DatetimeIndex,
    config: PPAConfig,
    seed: int,
) -> np.ndarray:
    """Per-path wind capacity factor — drives layer 3b on the price side."""
    return compute_wind_factor(times, config, seed=seed)


def _solar_from_cloud(
    times: pd.DatetimeIndex,
    poa_clearsky: np.ndarray,
    degradation: np.ndarray,
    config: PPAConfig,
    cloud: np.ndarray,
) -> pd.Series:
    """Build solar production from a pre-computed cloud factor."""
    sc = config.solar
    out = (
        sc.capacity_mw
        * sc.performance_ratio
        * (poa_clearsky * cloud / 1000.0)
        * degradation
    )
    return pd.Series(out, index=times, name="solar_production_mwh")


def _price_series(
    times: pd.DatetimeIndex,
    deterministic_layers_1_2_3a: np.ndarray,
    config: PPAConfig,
    seed: int,
    cloud_factor: np.ndarray | None = None,
    wind_factor: np.ndarray | None = None,
    system_solar_proxy: np.ndarray | None = None,
) -> pd.Series:
    """
    Generate one price path for a given noise seed.

    ``deterministic_layers_1_2_3a`` is the cached sum of layers 1, 2 and 3a
    (the parts that do NOT depend on realised weather). Layer 3b is computed
    from the supplied ``wind_factor`` (above-mean wind suppresses prices);
    layer 4 is recomputed with the supplied ``cloud_factor`` so the midday
    dip co-moves with production when
    ``market.production_cannibalisation_correlation`` > 0.
    ``system_solar_proxy`` is the cached pvlib clear-sky shape that drives
    layer 4's underlying NL-wide solar pattern (deterministic — same across
    all paths).
    """
    mc = config.market
    layer3b = _layer3b_wind_supply(times, config, wind_cf=wind_factor)
    layer4 = _layer4_cannibalisation(
        times,
        config,
        cloud_factor=cloud_factor,
        system_solar_proxy=system_solar_proxy,
    )
    noise = ar1_process(
        n=len(times),
        phi=mc.ar1_phi,
        sigma_stationary=mc.ar1_sigma,
        seed=seed,
    )
    return pd.Series(
        deterministic_layers_1_2_3a + layer3b + layer4 + noise,
        index=times,
        name="market_price_eur_mwh",
    )


# ---------------------------------------------------------------------------
# Ensemble runner
# ---------------------------------------------------------------------------


def _run_ensemble(
    mode: str,
    times: pd.DatetimeIndex,
    poa_clearsky: np.ndarray,
    degradation: np.ndarray,
    deterministic_price_1_2_3a: np.ndarray,
    system_solar_proxy: np.ndarray,
    load: pd.Series,
    config: PPAConfig,
    n_paths: int,
    base_strike: float,
    central_solar: pd.Series,
    central_prices: pd.Series,
    central_cloud: np.ndarray,
    central_wind: np.ndarray,
) -> pd.DataFrame:
    """
    Run n_paths for one decomposition mode.

    mode='joint'  — independent solar, wind and price-noise seeds; layer 3b
                    uses the path wind factor, layer 4 uses the path cloud.
    mode='price'  — solar fixed at central; layer 3b uses an independent
                    per-path wind factor (price-side weather risk); layer 4
                    uses the central cloud.
    mode='volume' — solar varies (cloud varies); layer 4 ALSO uses the path
                    cloud, so the midday dip co-moves with production via ρ.
                    Wind is held at the central realisation so this ensemble
                    isolates the volume-driven (production-side) component
                    of revenue risk. Layer-5 noise stays at the central seed.
    """
    logger.info("[%s] running %d paths...", mode, n_paths)

    t0 = time.time()
    rows: list[pd.DataFrame] = []

    for i in range(n_paths):
        if mode == "volume":
            cloud = _cloud_series(
                times, config, _VOLUME_SOLAR_BASE + i * _PATH_PRIME,
            )
            solar = _solar_from_cloud(
                times, poa_clearsky, degradation, config, cloud,
            )
            prices = _price_series(
                times, deterministic_price_1_2_3a, config,
                config.market.seed,
                cloud_factor=cloud,
                wind_factor=central_wind,
                system_solar_proxy=system_solar_proxy,
            )
        elif mode == "price":
            solar = central_solar
            wind = _wind_series(
                times, config, _PRICE_WIND_BASE + i * _PATH_PRIME,
            )
            prices = _price_series(
                times, deterministic_price_1_2_3a, config,
                _PRICE_PRICE_BASE + i * _PATH_PRIME,
                cloud_factor=central_cloud,
                wind_factor=wind,
                system_solar_proxy=system_solar_proxy,
            )
        else:  # joint
            cloud = _cloud_series(
                times, config, _JOINT_SOLAR_BASE + i * _PATH_PRIME,
            )
            wind = _wind_series(
                times, config, _JOINT_WIND_BASE + i * _PATH_PRIME,
            )
            solar = _solar_from_cloud(
                times, poa_clearsky, degradation, config, cloud,
            )
            prices = _price_series(
                times, deterministic_price_1_2_3a, config,
                _JOINT_PRICE_BASE + i * _PATH_PRIME,
                cloud_factor=cloud,
                wind_factor=wind,
                system_solar_proxy=system_solar_proxy,
            )

        combo = value_all_combinations(solar, load, prices, config, base_strike=base_strike)
        combo["path"] = i
        combo["mode"] = mode
        rows.append(combo)

        if (i + 1) % 100 == 0 or i == n_paths - 1:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (n_paths - i - 1) / rate
            logger.info(
                "  path %4d/%d  elapsed=%5.1fs  rate=%.1fp/s  eta=%.0fs",
                i + 1, n_paths, elapsed, rate, eta,
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
                 wind_seed_i  = 505_000 + i*1_000_003
    price  mode: price_seed_i = 303_000 + i*1_000_003
                 wind_seed_i  = 606_000 + i*1_000_003
    volume mode: solar_seed_i = 404_000 + i*1_000_003
                 (wind held at central realisation)
    """
    from ppa_engine.config import DEFAULT_CONFIG

    if config is None:
        config = DEFAULT_CONFIG
    if modes is None:
        modes = ["joint", "price", "volume"]

    # When verbose=True attach a stdout handler at INFO level for this run.
    # Cleaned up at the end so we do not leak handlers across calls.
    _handler = None
    _prev_level = logger.level
    if verbose:
        _handler = logging.StreamHandler()
        _handler.setLevel(logging.INFO)
        _handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(_handler)
        logger.setLevel(logging.INFO)

    t_start = time.time()

    # Step 1: build time index
    times = _build_timestamps(config)
    T = len(times)
    logger.info("Horizon: %s to %s  (%s hours)", times[0], times[-1], f"{T:,}")

    # Step 2: cache deterministic inputs (pvlib is expensive — compute once)
    logger.info("Caching deterministic inputs...")

    poa_clearsky = _clearsky_poa(times, config)

    # Layer 4 system-wide solar shape (pvlib at NL system reference) is
    # deterministic across paths — compute once, share across all ensembles.
    system_solar_proxy = compute_system_solar_proxy(times, config)

    start_year = pd.Timestamp(config.deal.start_date).year
    year_offset = np.array([t.year - start_year for t in times])
    degradation = 1.0 - config.solar.degradation_rate * year_offset

    # Layers 1, 2 and 3a are independent of realised weather and can be
    # cached. Layer 3b is recomputed per path from the realised wind factor,
    # and layer 4 is recomputed per path from the realised cloud factor.
    deterministic_price_1_2_3a = (
        _layer1_level(times, config)
        + _layer2_seasonal(times, config)
        + _layer3a_demand(times, config)
    )

    load = generate_consumer_load(config)

    # Step 3: central scenario at base seeds. The central cloud anchors
    # 'price' mode's layer-4 dip; the central wind anchors 'volume' mode's
    # layer-3b suppression.
    logger.info("Computing central scenario...")
    central_cloud = _cloud_series(times, config, config.solar.seed)
    central_wind = _wind_series(times, config, config.market.wind_seed)
    central_solar = _solar_from_cloud(
        times, poa_clearsky, degradation, config, central_cloud,
    )
    central_prices = _price_series(
        times, deterministic_price_1_2_3a, config, config.market.seed,
        cloud_factor=central_cloud,
        wind_factor=central_wind,
        system_solar_proxy=system_solar_proxy,
    )
    central_df = value_all_combinations(
        central_solar, load, central_prices, config, base_strike=base_strike
    )

    # Step 4: run ensembles
    frames: list[pd.DataFrame] = []
    for mode in modes:
        df = _run_ensemble(
            mode, times, poa_clearsky, degradation, deterministic_price_1_2_3a,
            system_solar_proxy, load, config, n_paths, base_strike,
            central_solar, central_prices, central_cloud, central_wind,
        )
        frames.append(df)

    paths_df = pd.concat(frames, ignore_index=True)
    elapsed = time.time() - t_start

    logger.info(
        "Done in %.1fs.  Total: %s rows (%d paths x %d modes x 12 combos).",
        elapsed, f"{len(paths_df):,}", n_paths, len(modes),
    )

    if _handler is not None:
        logger.removeHandler(_handler)
        logger.setLevel(_prev_level)

    return MonteCarloResult(
        paths_df=paths_df,
        central_df=central_df,
        n_paths=n_paths,
        base_strike=base_strike,
        config=config,
        elapsed_seconds=elapsed,
    )
