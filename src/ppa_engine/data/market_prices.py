"""
market_prices.py — Five-layer synthetic Dutch day-ahead wholesale price model.

Every layer is a named, documentable assumption.  The layers are summed to
give the final hourly price series.  Negative prices are allowed (real EPEX
NL goes negative on sunny, windy Sundays).

Layer 1 — Long-term level and drift
    level(t) = base_price + drift × years_from_2027(t)
    Highest uncertainty; always report as a sensitivity.

Layer 2 — Seasonal shape
    seasonal(t) = amplitude × cos(2π × (doy − peak_day) / 365)
    Winter high (gas heating demand), summer low (solar oversupply).

Layer 3 — Intra-day shape
    24-element additive vector, separate weekday/weekend profiles.
    Calibrated to match EPEX NL structural patterns:
      - Evening peak ~17:00–20:00 (domestic heating, industrial wind-down)
      - Morning peak ~07:00–09:00
      - Night trough

Layer 4 — Solar cannibalisation
    cannibalisation(t) = −α(year) × solar_proxy(t)
    solar_proxy peaks at noon in mid-summer (all NL panels generate together).
    α grows linearly from 2027→2036 reflecting continued solar build-out.
    Critical for capture-rate erosion: mid-summer noon prices start ~45 EUR/MWh
    in 2027 and can go negative by 2034.

Layer 5 — AR(1) autocorrelated noise
    noise(t) = φ × noise(t-1) + σ_innov × ε(t),  ε ~ N(0,1)
    φ = 0.70 → half-life ≈ 2 hours; creates realistic price clustering.
    Without autocorrelation, Monte Carlo underestimates revenue volatility.

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

from ppa_engine.config import PPAConfig


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


def _layer3_intraday(times: pd.DatetimeIndex, config: PPAConfig) -> np.ndarray:
    """
    Intra-day shape adder [EUR/MWh].

    Uses two 24-element vectors (weekday, weekend) from config.
    Weekday profile has a pronounced evening peak (~17:00) reflecting
    European industrial and residential demand patterns.
    """
    mc = config.market
    wd_arr = np.array(mc.weekday_hourly_adder)
    we_arr = np.array(mc.weekend_hourly_adder)

    hours = np.array([t.hour for t in times], dtype=int)
    is_weekend = np.array([t.dayofweek >= 5 for t in times])

    return np.where(is_weekend, we_arr[hours], wd_arr[hours])


def _layer4_cannibalisation(times: pd.DatetimeIndex, config: PPAConfig) -> np.ndarray:
    """
    Solar cannibalisation term [EUR/MWh].

    system_solar_proxy(t) ∈ [0, 1] peaks at noon in mid-summer:
        proxy(t) = max(0, sin(π × (hour − 6) / 12))
                 × max(0, sin(π × (doy − 80) / 185))

    The first factor is zero outside 06:00–18:00; the second is zero outside
    roughly March–September.  Their product peaks at solar noon in late June.

    α(year) interpolates linearly from alpha_2027 to alpha_2036.
    """
    mc = config.market
    start_year = pd.Timestamp(config.deal.start_date).year
    end_year = pd.Timestamp(config.deal.end_date).year
    tenor = end_year - start_year  # = 9

    hours = np.array([t.hour for t in times], dtype=float)
    doy = np.array([t.dayofyear for t in times], dtype=float)
    years = np.array([t.year - start_year for t in times], dtype=float)

    # Diurnal solar proxy (zero at night)
    hour_proxy = np.maximum(0.0, np.sin(np.pi * (hours - 6.0) / 12.0))

    # Seasonal solar proxy (zero in winter)
    season_proxy = np.maximum(0.0, np.sin(np.pi * (doy - 80.0) / 185.0))

    system_solar_proxy = hour_proxy * season_proxy

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
    rng = np.random.default_rng(mc.seed)

    n = len(times)
    phi = mc.ar1_phi
    sigma = mc.ar1_sigma
    sigma_innov = sigma * np.sqrt(1.0 - phi**2)

    eps = rng.standard_normal(n)
    noise = np.empty(n)
    noise[0] = sigma * eps[0]   # draw from stationary N(0, σ²)
    for t in range(1, n):
        noise[t] = phi * noise[t - 1] + sigma_innov * eps[t]

    return noise


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

    layer1 = _layer1_level(times, config)
    layer2 = _layer2_seasonal(times, config)
    layer3 = _layer3_intraday(times, config)
    layer4 = _layer4_cannibalisation(times, config)
    layer5 = _layer5_ar1_noise(times, config)

    prices = layer1 + layer2 + layer3 + layer4 + layer5

    return pd.Series(prices, index=times, name="market_price_eur_mwh")
