"""
market_prices.py — Six-layer synthetic Dutch day-ahead wholesale price model.

The intra-day shape is split into two **independently determined** sublayers:
demand (3a, deterministic) and wind supply (3b, stochastic). Together with
the solar cannibalisation layer (4), the renewable-supply picture is complete
and demand is isolated. The layers are summed to give the final hourly price
series.  Negative prices are allowed (real EPEX NL goes negative on sunny,
windy Sundays).

Layer 1 — Long-term level and drift
    level(t) = base_price + drift × years_from_2027(t)
    Highest uncertainty; always report as a sensitivity.

Layer 2 — Seasonal shape
    seasonal(t) = amplitude × cos(2π × (doy − peak_day) / 365)
    Winter high (gas heating demand), summer low (solar oversupply).

Layer 3a — Demand intra-day shape (deterministic)
    24-element additive vector, separate weekday/weekend profiles.  Bimodal
    weekday pattern (morning peak ~08:00, evening peak ~18:00) with a flat
    midday plateau on the linear envelope between the two peaks.  No baked-in
    "solar dip" — that effect now belongs entirely to layers 3b + 4.
    A mild seasonal uplift amplifies the curve in winter (heating demand).

Layer 3b — Wind supply suppression (stochastic, per Monte Carlo path)
    wind_cf(t) ∈ (0, 1) is an AR(1) process in logit-space, with monthly means
    reflecting Dutch wind climatology (winter > summer) and a small diurnal
    adder (overnight slightly higher, mid-afternoon slightly lower).
    layer3b(t) = −β(year) × (wind_cf(t) − reference_cf)
    β grows linearly 2027→2036 reflecting NL offshore-wind buildout.  Above-
    mean wind suppresses prices, below-mean lifts them.

Layer 4 — Solar cannibalisation
    cannibalisation(t) = −α(year) × solar_proxy(t) × modulation(t)
    solar_proxy peaks at noon in mid-summer (all NL panels generate together).
    α grows linearly from 2027→2036 reflecting continued solar build-out.
    modulation(t) ties the dip to the realised asset cloud factor via
    ρ = market.production_cannibalisation_correlation.  Critical for
    capture-rate erosion: mid-summer noon prices start ~45 EUR/MWh in 2027 and
    can go negative by 2034.

Layer 5 — AR(1) autocorrelated noise
    noise(t) = φ × noise(t-1) + σ_innov × ε(t),  ε ~ N(0,1)
    φ = 0.70 → half-life ≈ 2 hours; creates realistic price clustering.

Calibration targets
-------------------
Annual average    ~80 EUR/MWh in 2027, declining to ~63 EUR/MWh by 2036
Peak hours        120–150 EUR/MWh (17:00–20:00, winter weekdays)
Solar peak        40–50 EUR/MWh (12:00–14:00, summer, 2027)
Weekend nights    30–50 EUR/MWh (summer)
Capture rate      0.65–0.85, declining over the horizon
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.special import logit

from ppa_engine.config import PPAConfig
from ppa_engine.utils.ar1 import ar1_logit_process, ar1_process


def _build_timestamps(config: PPAConfig) -> pd.DatetimeIndex:
    return pd.date_range(
        start=config.deal.start_date,
        end=config.deal.end_date + " 23:00",
        freq="h",
        tz=config.location.tz,
    )


def _layer1_level(times: pd.DatetimeIndex, config: PPAConfig) -> np.ndarray:
    """Long-term price level with drift."""
    mc = config.market
    start_year = pd.Timestamp(config.deal.start_date).year
    # Fractional years elapsed (continuous, to avoid step discontinuities)
    years = np.array(
        [(t.year - start_year) + (t.dayofyear - 1) / 365.25 for t in times]
    )
    return mc.base_price + mc.drift * years


def _layer2_seasonal(times: pd.DatetimeIndex, config: PPAConfig) -> np.ndarray:
    """Seasonal cosine wave — winter high, summer low."""
    mc = config.market
    doy = np.array([t.dayofyear for t in times])
    return mc.seasonal_amplitude * np.cos(
        2.0 * np.pi * (doy - mc.seasonal_peak_day) / 365.25
    )


def _layer3a_demand(times: pd.DatetimeIndex, config: PPAConfig) -> np.ndarray:
    """
    Demand intra-day shape adder [EUR/MWh].

    Deterministic — depends only on hour-of-day, day-of-week, and day-of-year
    (for the mild winter uplift). Uses two 24-element shape vectors from
    config.market.demand_weekday_shape / demand_weekend_shape. The weekday
    shape is bimodal (morning + evening peaks) with no embedded midday dip:
    the noon plateau sits between the morning and evening peaks rather than
    below them. Any midday price suppression must come from layers 3b + 4.
    """
    mc = config.market
    wd_arr = np.array(mc.demand_weekday_shape, dtype=float)
    we_arr = np.array(mc.demand_weekend_shape, dtype=float)

    hours = np.array([t.hour for t in times], dtype=int)
    is_weekend = np.array([t.dayofweek >= 5 for t in times])
    base = np.where(is_weekend, we_arr[hours], wd_arr[hours])

    doy = np.array([t.dayofyear for t in times], dtype=float)
    seasonal_uplift = 1.0 + mc.demand_winter_uplift * np.cos(
        2.0 * np.pi * (doy - mc.demand_peak_day) / 365.25
    )
    return base * seasonal_uplift


def compute_wind_factor(
    times: pd.DatetimeIndex,
    config: PPAConfig,
    seed: int | None = None,
) -> np.ndarray:
    """
    Public helper returning a stochastic Dutch system-wide wind capacity
    factor in (0, 1), the same length as ``times``.

    The latent process is a stationary AR(1) in logit-space (φ ≈ 0.95 for
    multi-day persistence). The monthly mean reflects Dutch climatology
    (winter > summer); a small diurnal adder in logit-space mildly raises
    overnight values and depresses mid-afternoon values.

    Used by ``_layer3b_wind_supply``. Exposed publicly so the Monte Carlo
    orchestrator can pre-compute one per path and pass it in.
    """
    mc = config.market
    monthly_logit = np.array([logit(m) for m in mc.monthly_wind_means])
    months = np.array([t.month - 1 for t in times], dtype=int)
    hours = np.array([t.hour for t in times], dtype=int)
    diurnal = np.array(mc.wind_diurnal_logit_adder, dtype=float)
    logit_mean = monthly_logit[months] + diurnal[hours]
    return ar1_logit_process(
        n=len(times),
        phi=mc.wind_cf_phi,
        logit_scale=mc.wind_cf_logit_scale,
        monthly_logit_means=logit_mean,
        seed=mc.wind_seed if seed is None else seed,
    )


def _layer3b_wind_supply(
    times: pd.DatetimeIndex,
    config: PPAConfig,
    wind_cf: np.ndarray | None = None,
    seed: int | None = None,
) -> np.ndarray:
    """
    Wind supply suppression term [EUR/MWh].

    layer3b(t) = −β(year) × (wind_cf(t) − reference_cf)

    Above-mean wind realisations suppress prices; below-mean realisations lift
    them. β(year) grows linearly from beta_wind_2027 to beta_wind_2036 to
    reflect Dutch offshore-wind buildout.

    Parameters
    ----------
    wind_cf :
        Pre-computed wind capacity factor, same length as ``times``. When
        omitted, a fresh AR(1) draw is taken via ``compute_wind_factor``
        with ``seed`` (or ``config.market.wind_seed`` if seed is None).
    """
    mc = config.market
    start_year = pd.Timestamp(config.deal.start_date).year
    end_year = pd.Timestamp(config.deal.end_date).year
    tenor = max(end_year - start_year, 1)

    if wind_cf is None:
        wind_cf = compute_wind_factor(times, config, seed=seed)

    years = np.array([t.year - start_year for t in times], dtype=float)
    beta = mc.beta_wind_2027 + (
        mc.beta_wind_2036 - mc.beta_wind_2027
    ) * years / tenor

    deviation = np.asarray(wind_cf, dtype=float) - mc.wind_reference_cf
    return -beta * deviation


def _layer4_cannibalisation(
    times: pd.DatetimeIndex,
    config: PPAConfig,
    cloud_factor: np.ndarray | None = None,
) -> np.ndarray:
    """
    Solar cannibalisation term [EUR/MWh].

    system_solar_proxy(t) ∈ [0, 1] peaks at noon in mid-summer:
        proxy(t) = max(0, sin(π × (hour − 6) / 12))
                 × max(0, sin(π × (doy − 80) / 185))

    The first factor is zero outside 06:00–18:00; the second is zero outside
    roughly March–September.  Their product peaks at solar noon in late June.

    α(year) interpolates linearly from alpha_2027 to alpha_2036.

    Parameters
    ----------
    cloud_factor :
        Optional asset-level cloud factor in (0, 1), same length as ``times``.
        When provided together with
        ``market.production_cannibalisation_correlation > 0`` the dip is
        modulated by clearness relative to the monthly climatological mean:

            relative_clearness(t) = cloud_factor(t) / monthly_mean(month)
            modulation(t)         = (1 - ρ) + ρ × relative_clearness(t)

        modulation is clipped to [0, 2.5] so a single extreme realisation
        cannot blow up the price. When ``cloud_factor`` is None or ρ == 0
        the function returns the legacy purely-diurnal cannibalisation.
    """
    mc = config.market
    start_year = pd.Timestamp(config.deal.start_date).year
    end_year = pd.Timestamp(config.deal.end_date).year
    tenor = end_year - start_year  # = 9

    hours = np.array([t.hour for t in times], dtype=float)
    doy = np.array([t.dayofyear for t in times], dtype=float)
    months = np.array([t.month - 1 for t in times], dtype=int)
    years = np.array([t.year - start_year for t in times], dtype=float)

    # Diurnal solar proxy (zero at night)
    hour_proxy = np.maximum(0.0, np.sin(np.pi * (hours - 6.0) / 12.0))

    # Seasonal solar proxy (zero in winter)
    season_proxy = np.maximum(0.0, np.sin(np.pi * (doy - 80.0) / 185.0))

    system_solar_proxy = hour_proxy * season_proxy

    rho = float(mc.production_cannibalisation_correlation)
    if cloud_factor is not None and rho > 0.0:
        monthly_means = np.asarray(config.solar.monthly_cloud_means, dtype=float)
        expected_cloud = monthly_means[months]
        relative_clearness = np.asarray(cloud_factor, dtype=float) / expected_cloud
        modulation = np.clip((1.0 - rho) + rho * relative_clearness, 0.0, 2.5)
        system_solar_proxy = system_solar_proxy * modulation

    # Growing cannibalisation coefficient
    alpha = mc.cannibalisation_alpha_2027 + (
        mc.cannibalisation_alpha_2036 - mc.cannibalisation_alpha_2027
    ) * years / tenor

    return -alpha * system_solar_proxy


def _layer5_ar1_noise(times: pd.DatetimeIndex, config: PPAConfig) -> np.ndarray:
    """
    AR(1) autocorrelated noise [EUR/MWh].

    Stationary AR(1): noise(t) = φ × noise(t-1) + σ_innov × ε(t)
    Stationary distribution: N(0, σ²)  where σ = config.market.ar1_sigma.

    φ = 0.70 gives a half-life of ≈ 2 hours — realistic for EPEX NL where
    gas-price movements, weather events, and outages persist over hours/days.
    """
    mc = config.market
    return ar1_process(
        n=len(times),
        phi=mc.ar1_phi,
        sigma_stationary=mc.ar1_sigma,
        seed=mc.seed,
    )


def generate_market_prices(config: PPAConfig | None = None) -> pd.Series:
    """
    Generate hourly Dutch day-ahead wholesale prices [EUR/MWh].

    Parameters
    ----------
    config:
        PPAConfig instance.  Uses DEFAULT_CONFIG if None.

    Returns
    -------
    pd.Series
        Hourly prices in EUR/MWh with a timezone-aware DatetimeIndex.
        Name: ``"market_price_eur_mwh"``.
        Negative prices are possible (no floor at zero).
    """
    from ppa_engine.config import DEFAULT_CONFIG

    if config is None:
        config = DEFAULT_CONFIG

    times = _build_timestamps(config)

    # Layer 4 is conditional on the asset's cloud factor when
    # production_cannibalisation_correlation > 0, so production and prices
    # share the same realised weather. Using the solar seed keeps the central
    # price scenario coherent with the central solar production series.
    from ppa_engine.data.solar_production import compute_cloud_factor

    cloud = (
        compute_cloud_factor(times, config)
        if config.market.production_cannibalisation_correlation > 0.0
        else None
    )

    # Layer 3b draws an independent AR(1) wind factor using config.market.wind_seed.
    wind_cf = compute_wind_factor(times, config)

    layer1 = _layer1_level(times, config)
    layer2 = _layer2_seasonal(times, config)
    layer3a = _layer3a_demand(times, config)
    layer3b = _layer3b_wind_supply(times, config, wind_cf=wind_cf)
    layer4 = _layer4_cannibalisation(times, config, cloud_factor=cloud)
    layer5 = _layer5_ar1_noise(times, config)

    prices = layer1 + layer2 + layer3a + layer3b + layer4 + layer5

    return pd.Series(prices, index=times, name="market_price_eur_mwh")
