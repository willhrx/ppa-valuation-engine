"""
solar_production.py — Hourly solar AC output for the 2027–2036 PPA horizon.

Generation pipeline
-------------------
1. Define asset location (Utrecht, NL) via pvlib.
2. Build hourly timestamps for the full 10-year horizon.
3. Compute clear-sky irradiance using the Ineichen model.
4. Project onto a 35° south-facing tilted plane → POA irradiance.
5. Apply a stochastic cloud factor (beta-distributed in spirit, AR(1) in
   logit-space so values stay in (0,1)).  φ ≈ 0.90 captures the persistence
   of Dutch weather systems.
6. Apply performance ratio (~0.80) and linear annual degradation (0.5 %/yr).
7. Scale by capacity (50 MW) → AC output in MWh/h.

Sanity checks (verifiable in notebooks/00_data_sanity_checks.ipynb)
--------------------------------------------------------------------
- Annual yield:      900–1 000 kWh/kWp
- Capacity factor:   10–12 %
- Night-time output: exactly 0 (when POA clear-sky is 0)
- Visible "bad weeks" and "good weeks" from autocorrelated cloud factor
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pvlib
from scipy.special import logit

from ppa_engine.config import PPAConfig
from ppa_engine.utils.ar1 import ar1_logit_process


def _build_timestamps(config: PPAConfig) -> pd.DatetimeIndex:
    """Return the hourly DatetimeIndex for the full PPA horizon."""
    return pd.date_range(
        start=config.deal.start_date,
        end=config.deal.end_date + " 23:00",
        freq="h",
        tz=config.location.tz,
    )


def _clearsky_poa(times: pd.DatetimeIndex, config: PPAConfig) -> np.ndarray:
    """
    Compute clear-sky plane-of-array (POA) irradiance [W/m²].

    Uses pvlib Ineichen clear-sky model and isotropic sky diffuse model.
    """
    lc = config.location
    sc = config.solar

    location = pvlib.location.Location(
        latitude=lc.lat,
        longitude=lc.lon,
        tz=lc.tz,
        altitude=lc.altitude,
    )

    # Clear-sky GHI, DNI, DHI via Ineichen
    clearsky = location.get_clearsky(times)

    # Solar position
    solar_pos = location.get_solarposition(times)

    # Decompose onto tilted surface
    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=sc.tilt_deg,
        surface_azimuth=sc.azimuth_deg,
        solar_zenith=solar_pos["apparent_zenith"],
        solar_azimuth=solar_pos["azimuth"],
        dni=clearsky["dni"],
        ghi=clearsky["ghi"],
        dhi=clearsky["dhi"],
        model="isotropic",
    )

    return poa["poa_global"].fillna(0.0).values


def compute_cloud_factor(
    times: pd.DatetimeIndex,
    config: PPAConfig,
    seed: int | None = None,
) -> np.ndarray:
    """
    Public helper used by both the solar generator and the price layer-4
    cannibalisation modulation. Re-using the same cloud realisation across
    production and prices is what creates the production–cannibalisation
    correlation in the central scenario.
    """
    sc = config.solar
    monthly_logit = np.array([logit(m) for m in sc.monthly_cloud_means])
    hour_logit_mean = monthly_logit[np.array([t.month - 1 for t in times])]
    return ar1_logit_process(
        n=len(times),
        phi=sc.cloud_factor_phi,
        logit_scale=sc.cloud_factor_logit_scale,
        monthly_logit_means=hour_logit_mean,
        seed=sc.seed if seed is None else seed,
    )


def _cloud_factor(times: pd.DatetimeIndex, config: PPAConfig) -> np.ndarray:
    """
    Generate a stochastic hourly cloud factor in (0, 1).

    Methodology
    -----------
    We model the cloud factor in logit-space as:

        logit(CF(t)) = μ_month(t) + scale × z(t)

    where z(t) follows a stationary AR(1):

        z(t) = φ × z(t-1) + sqrt(1 - φ²) × ε(t),   ε ~ N(0, 1)

    Applying the logistic function keeps CF(t) in (0, 1).  The monthly mean
    μ_month encodes Dutch climatology (cloudier in winter, less so in summer).
    The AR(1) autocorrelation (φ ≈ 0.90) ensures weather-system persistence.

    Parameters
    ----------
    times:
        Hourly DatetimeIndex for the full horizon.
    config:
        PPAConfig with solar.monthly_cloud_means, solar.cloud_factor_phi,
        solar.cloud_factor_logit_scale, and solar.seed.

    Returns
    -------
    np.ndarray
        Cloud factor values in (0, 1), shape (len(times),).
    """
    return compute_cloud_factor(times, config)


def generate_solar_production(config: PPAConfig | None = None) -> pd.Series:
    """
    Generate hourly solar AC output [MWh/h] for the full PPA horizon.

    Parameters
    ----------
    config:
        PPAConfig instance.  Uses DEFAULT_CONFIG if None.

    Returns
    -------
    pd.Series
        Hourly AC output in MWh/h with a timezone-aware DatetimeIndex.
        Name: ``"solar_production_mwh"``.

    Notes
    -----
    Degradation is applied linearly: year 2027 → factor 1.0,
    year 2036 → factor (1 − 0.005 × 9) = 0.955.
    """
    from ppa_engine.config import DEFAULT_CONFIG

    if config is None:
        config = DEFAULT_CONFIG

    sc = config.solar
    dc = config.deal

    times = _build_timestamps(config)

    # Step 1: clear-sky POA irradiance [W/m²]
    poa_clearsky = _clearsky_poa(times, config)

    # Step 2: stochastic cloud factor
    cloud = _cloud_factor(times, config)

    # Step 3: actual POA = clear-sky × cloud factor
    poa_actual = poa_clearsky * cloud

    # Step 4: annual degradation factor (linear, from base year)
    start_year = pd.Timestamp(dc.start_date).year
    year_offset = np.array([t.year - start_year for t in times])
    degradation = 1.0 - sc.degradation_rate * year_offset

    # Step 5: AC output
    #   MWh/h = capacity_MW × PR × (POA [W/m²] / 1000 [W/kW]) × degradation
    #         = capacity_MW × PR × POA_kW/m² × degradation
    output_mwh = sc.capacity_mw * sc.performance_ratio * (poa_actual / 1000.0) * degradation

    return pd.Series(output_mwh, index=times, name="solar_production_mwh")
