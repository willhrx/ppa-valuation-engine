"""
production_scenarios.py — Solar production P10/P50/P90 scenarios (Phase 3).

P50 is the central (median) production scenario — what we expect half the time.
P90 is the conservative case: production exceeds this level in only 90 % of years.
P10 is the optimistic case: production exceeds this level in only 10 % of years.

The spread between P10 and P90 reflects volume risk (interannual variability
of solar irradiance). For NL utility-scale solar, P90/P50 ≈ 0.88–0.93.

Modelling approach: re-run the cloud factor AR(1) N times with different seeds,
compute annual totals per path, and read off percentiles. This propagates cloud
autocorrelation correctly into the annual production distribution.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.special import expit, logit

from ppa_engine.config import PPAConfig
from ppa_engine.data.solar_production import _clearsky_poa

# Different prime from price_process to avoid seed collisions across modules
_PATH_PRIME = 999_983


def _cloud_factor_matrix(
    times: pd.DatetimeIndex,
    config: PPAConfig,
    n_paths: int,
    base_seed: int | None = None,
) -> np.ndarray:
    """
    Generate an (n_paths, T) cloud factor matrix with values in (0, 1).

    Monthly means are deterministic (from config) and shared across paths.
    Only the AR(1) innovation sequence differs between paths.

    Uses the same vectorised-across-paths strategy as _ar1_noise_matrix:
        cloud[i, t] = expit(monthly_logit_mean[t] + scale * z[i, t])
    where z follows a standardised AR(1) (marginal std = 1).
    """
    sc = config.solar
    seed = base_seed if base_seed is not None else sc.seed

    T = len(times)
    phi = sc.cloud_factor_phi
    scale = sc.cloud_factor_logit_scale
    sigma_innov = np.sqrt(1.0 - phi * phi)

    # Monthly means → logit space (deterministic, same for all paths)
    monthly_logit = np.array([logit(m) for m in sc.monthly_cloud_means])
    hour_logit_mean = monthly_logit[np.array([t.month - 1 for t in times])]

    # Independent standardised AR(1) per path
    all_eps = np.empty((n_paths, T), dtype=np.float64)
    for i in range(n_paths):
        rng = np.random.default_rng(seed + i * _PATH_PRIME)
        all_eps[i] = rng.standard_normal(T)

    # Vectorised standardised AR(1): marginal std = 1
    z = np.empty((n_paths, T), dtype=np.float64)
    z[:, 0] = all_eps[:, 0]
    for t in range(1, T):
        z[:, t] = phi * z[:, t - 1] + sigma_innov * all_eps[:, t]

    # Map to (0, 1): cloud[i, t] = expit(mean[t] + scale * z[i, t])
    # hour_logit_mean shape (T,) → broadcast with z shape (n_paths, T)
    return expit(hour_logit_mean[np.newaxis, :] + scale * z)


def compute_annual_percentiles(
    production_matrix: np.ndarray,
    times: pd.DatetimeIndex,
) -> dict[str, np.ndarray]:
    """
    Compute P10/P50/P90 annual production across n_paths.

    Parameters
    ----------
    production_matrix : np.ndarray
        Shape (n_paths, T), hourly production in MWh/h.
    times : pd.DatetimeIndex
        Used to extract year labels.

    Returns
    -------
    dict with keys 'years', 'p10', 'p50', 'p90'.
    Each percentile array has shape (n_years,) in GWh.
    """
    years = sorted(set(t.year for t in times))
    times_years = np.array([t.year for t in times])

    p10_vals, p50_vals, p90_vals = [], [], []
    for year in years:
        mask = times_years == year
        # Sum across hours for this year → shape (n_paths,); convert MWh → GWh
        annual_totals = production_matrix[:, mask].sum(axis=1) / 1000.0
        p10_vals.append(float(np.percentile(annual_totals, 10)))
        p50_vals.append(float(np.percentile(annual_totals, 50)))
        p90_vals.append(float(np.percentile(annual_totals, 90)))

    return {
        "years": np.array(years),
        "p10": np.array(p10_vals),
        "p50": np.array(p50_vals),
        "p90": np.array(p90_vals),
    }


def generate_production_scenarios(
    config: PPAConfig,
    n_paths: int,
    times: pd.DatetimeIndex,
    poa_clearsky: np.ndarray | None = None,
    base_seed: int | None = None,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """
    Generate n_paths solar production time series.

    Parameters
    ----------
    config : PPAConfig
    n_paths : int
    times : pd.DatetimeIndex
        Full hourly time index.
    poa_clearsky : np.ndarray | None
        Pre-computed clear-sky POA irradiance [W/m²], shape (T,). If None,
        computed internally via pvlib (expensive). Always pass this in when
        calling from the Monte Carlo orchestrator.
    base_seed : int | None
        Override for config.solar.seed.

    Returns
    -------
    production_matrix : np.ndarray
        Shape (n_paths, T). Row i is hourly AC output [MWh/h] for path i.
    annual_percentiles : dict
        Keys: 'years', 'p10', 'p50', 'p90'. Each percentile array has
        shape (n_years,) in GWh, computed across the n_paths paths.
    """
    if poa_clearsky is None:
        poa_clearsky = _clearsky_poa(times, config)

    sc = config.solar
    dc = config.deal
    start_year = pd.Timestamp(dc.start_date).year
    year_offset = np.array([t.year - start_year for t in times])
    degradation = 1.0 - sc.degradation_rate * year_offset

    cloud_matrix = _cloud_factor_matrix(times, config, n_paths, base_seed)

    # Vectorised output: capacity * PR * (poa * cloud / 1000) * degradation
    # poa_clearsky shape (T,), cloud_matrix shape (n_paths, T), degradation shape (T,)
    production_matrix = (
        sc.capacity_mw
        * sc.performance_ratio
        * (poa_clearsky[np.newaxis, :] * cloud_matrix / 1000.0)
        * degradation[np.newaxis, :]
    )

    annual_percentiles = compute_annual_percentiles(production_matrix, times)

    return production_matrix, annual_percentiles
