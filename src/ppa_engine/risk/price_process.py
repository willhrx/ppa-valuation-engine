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
from ppa_engine.utils.ar1 import ar1_noise_matrix as _shared_ar1_noise_matrix

# Large prime for per-path seed derivation; prevents seed collisions across paths
_PATH_PRIME = 1_000_003


def _ar1_noise_matrix(
    T: int,
    n_paths: int,
    phi: float,
    sigma_stationary: float,
    base_seed: int,
) -> np.ndarray:
    """Vectorised (n_paths, T) AR(1) noise matrix (thin wrapper)."""
    return _shared_ar1_noise_matrix(
        T=T,
        n_paths=n_paths,
        phi=phi,
        sigma_stationary=sigma_stationary,
        base_seed=base_seed,
        path_prime=_PATH_PRIME,
    )


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
