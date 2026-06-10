"""
ar1.py — Shared AR(1) generators used across the engine.

Two scalar variants are exposed:

- ``ar1_process``        : stationary AR(1) in standard space with a chosen
                           marginal standard deviation.
- ``ar1_logit_process``  : AR(1) in logit-space, mapped through expit so the
                           series lives strictly in (0, 1) — used for the
                           solar cloud factor.

The vectorised matrix variant ``ar1_noise_matrix`` powers the batch Monte
Carlo path generator in ``risk/price_process.py``.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import lfilter
from scipy.special import expit


def _ar1_filter(driver: np.ndarray, phi: float, axis: int = -1) -> np.ndarray:
    """Evaluate x[t] = phi * x[t-1] + driver[t] (x[0] = driver[0]) in C.

    scipy.signal.lfilter with b=[1], a=[1, -phi] computes exactly this
    recurrence, replacing the original pure-Python loop (~87k steps per
    series) with a single C pass. Results match the loop to float precision.
    """
    return lfilter([1.0], [1.0, -phi], driver, axis=axis)


def ar1_process(
    n: int,
    phi: float,
    sigma_stationary: float,
    seed: int,
) -> np.ndarray:
    """Stationary AR(1) series of length n, marginal std = sigma_stationary.

    Recurrence:
        x[0] = sigma_stationary * eps[0]
        x[t] = phi * x[t-1] + sigma_innov * eps[t],    eps ~ N(0, 1)
    where sigma_innov = sigma_stationary * sqrt(1 - phi**2).
    """
    rng = np.random.default_rng(seed)
    sigma_innov = sigma_stationary * np.sqrt(1.0 - phi * phi)

    eps = rng.standard_normal(n)
    driver = sigma_innov * eps
    driver[0] = sigma_stationary * eps[0]
    return _ar1_filter(driver, phi)


def ar1_logit_process(
    n: int,
    phi: float,
    logit_scale: float,
    monthly_logit_means: np.ndarray,
    seed: int,
) -> np.ndarray:
    """AR(1) in logit-space mapped through expit → values in (0, 1).

    The latent process z is a stationary AR(1) with marginal N(0, 1):
        z[t] = phi * z[t-1] + sqrt(1 - phi**2) * eps[t]
    and the returned series is:
        expit(monthly_logit_means + logit_scale * z)

    Parameters
    ----------
    n :
        Number of timesteps.
    phi :
        AR(1) autocorrelation.
    logit_scale :
        Multiplicative spread of the latent AR(1) in logit-space.
    monthly_logit_means :
        Pre-broadcast monthly logit means, shape (n,).
    seed :
        RNG seed.
    """
    rng = np.random.default_rng(seed)
    sigma_innov = np.sqrt(1.0 - phi * phi)

    eps = rng.standard_normal(n)
    driver = sigma_innov * eps
    driver[0] = eps[0]
    z = _ar1_filter(driver, phi)

    return expit(monthly_logit_means + logit_scale * z)


def ar1_noise_matrix(
    T: int,
    n_paths: int,
    phi: float,
    sigma_stationary: float,
    base_seed: int,
    path_prime: int = 1_000_003,
) -> np.ndarray:
    """Vectorised (n_paths, T) matrix of independent stationary AR(1) noise.

    Per-path seeds are derived as ``base_seed + i * path_prime``, guaranteeing
    statistical independence without sequential RNG state.
    """
    sigma_innov = sigma_stationary * np.sqrt(1.0 - phi * phi)

    all_eps = np.empty((n_paths, T), dtype=np.float64)
    for i in range(n_paths):
        rng = np.random.default_rng(base_seed + i * path_prime)
        all_eps[i] = rng.standard_normal(T)

    driver = sigma_innov * all_eps
    driver[:, 0] = sigma_stationary * all_eps[:, 0]
    return _ar1_filter(driver, phi, axis=1)
