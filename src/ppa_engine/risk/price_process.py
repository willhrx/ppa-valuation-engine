"""
price_process.py — Stochastic price process for Monte Carlo (Phase 3).

Implements an AR(1) process (discrete-time equivalent of Ornstein-Uhlenbeck)
to simulate N independent price paths around the central scenario.

The AR(1) noise layer in the central scenario (market_prices.py, Layer 5) is
a single realisation of this process. Phase 3 generates N independent
realisations to build a distribution of outcomes.

Why AR(1) matters for risk quantification:
  - Autocorrelation clusters low prices with high solar output → the
    cannibalisation effect is a *clustering* phenomenon, not just an average
  - Without it, Monte Carlo systematically underestimates revenue volatility
  - AR(1) is tractable, interpretable, and calibratable from EPEX data
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ppa_engine.config import PPAConfig
from ppa_engine.data.market_prices import (
    _layer1_level,
    _layer2_seasonal,
    _layer3_intraday,
    _layer4_cannibalisation,
)

# Large prime for per-path seed derivation; prevents seed collisions across paths
_PATH_PRIME = 1_000_003


def _ar1_noise_matrix(
    T: int,
    n_paths: int,
    phi: float,
    sigma_stationary: float,
    base_seed: int,
) -> np.ndarray:
    """
    Generate an (n_paths, T) matrix of independent stationary AR(1) noise.

    Each row is an independent realisation with marginal distribution
    N(0, sigma_stationary^2). Seeds are derived as base_seed + i * _PATH_PRIME,
    guaranteeing independence and reproducibility without sequential RNG state.

    The inner loop runs T iterations on an (n_paths,) vector — NumPy C-level
    operations — which is ~50-100x faster than a pure Python path-at-a-time loop.
    """
    sigma_innov = sigma_stationary * np.sqrt(1.0 - phi * phi)

    # Each path gets its own RNG for statistical independence
    all_eps = np.empty((n_paths, T), dtype=np.float64)
    for i in range(n_paths):
        rng = np.random.default_rng(base_seed + i * _PATH_PRIME)
        all_eps[i] = rng.standard_normal(T)

    # Vectorised AR(1) recurrence: each time step updates all paths simultaneously
    noise = np.empty((n_paths, T), dtype=np.float64)
    noise[:, 0] = sigma_stationary * all_eps[:, 0]
    for t in range(1, T):
        noise[:, t] = phi * noise[:, t - 1] + sigma_innov * all_eps[:, t]

    return noise


def build_deterministic_price(
    times: pd.DatetimeIndex,
    config: PPAConfig,
) -> np.ndarray:
    """
    Compute the sum of price layers 1–4 (fully deterministic).

    Shape: (T,). This is the base signal that all stochastic paths share.
    Compute once and pass into simulate_price_paths to avoid redundant work.
    """
    return (
        _layer1_level(times, config)
        + _layer2_seasonal(times, config)
        + _layer3_intraday(times, config)
        + _layer4_cannibalisation(times, config)
    )


def simulate_price_paths(
    config: PPAConfig,
    n_paths: int,
    times: pd.DatetimeIndex,
    deterministic_layers: np.ndarray | None = None,
    base_seed: int | None = None,
) -> np.ndarray:
    """
    Simulate n_paths independent hourly price paths over the given time index.

    Parameters
    ----------
    config : PPAConfig
        Uses config.market.ar1_phi, ar1_sigma, and seed.
    n_paths : int
        Number of independent Monte Carlo paths.
    times : pd.DatetimeIndex
        Full hourly time index; T = len(times).
    deterministic_layers : np.ndarray | None
        Pre-computed sum of layers 1–4, shape (T,). If None, computed
        internally. Always pass this in when running multiple ensembles.
    base_seed : int | None
        Override for config.market.seed.

    Returns
    -------
    np.ndarray
        Shape (n_paths, T). Row i is the full hourly price series for path i.
        Each path = deterministic_layers + independent AR(1) noise realisation.
    """
    if deterministic_layers is None:
        deterministic_layers = build_deterministic_price(times, config)

    seed = base_seed if base_seed is not None else config.market.seed
    mc = config.market
    T = len(times)

    noise = _ar1_noise_matrix(T, n_paths, mc.ar1_phi, mc.ar1_sigma, seed)

    # Broadcast deterministic_layers (T,) across all n_paths rows
    return deterministic_layers[np.newaxis, :] + noise
