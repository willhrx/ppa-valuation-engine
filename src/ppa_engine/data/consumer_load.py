"""
consumer_load.py — Hourly industrial offtaker load for the 2027–2036 horizon.

The offtaker is a mid-sized Dutch industrial consumer with ~100 GWh/year
consumption.  The load shape is built from three components:

1. Base hourly profile (weekday / weekend)
   Two 24-element multiplier vectors giving the within-day demand pattern.
   Industrial shape: bimodal peaks at ~10:00 and ~18:00, low overnight.
   Weekend is flatter and lower (reduced industrial activity).

2. Seasonal modulation
   seasonal(t) = 1 + amplitude × cos(2π × (doy − peak_day) / 365)
   Winter uplift (space heating / process heat in cold weather).
   amplitude = 0.15 → ±15 % seasonal swing.

3. Log-normal noise
   Multiplicative noise ~ LogNormal(0, σ) applied per hour.
   Captures equipment cycling, temperature variation, scheduling changes.
   σ = 0.05 → roughly ±5 % hourly variation.

The entire series is rescaled so the annual totals match the target
consumption (100 GWh/year) exactly.  This ensures downstream calculations
(e.g., hedge ratio) are not biased by drift in the noise layer.

Sanity checks
-------------
- Annual total: 100 GWh ± 0.1 % (after rescaling)
- Hourly mean: ~11.4 MWh/h (= 100 000 MWh / 8 760 h)
- Clear weekday/weekend distinction in daily profiles
- Mild seasonal amplitude
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


def generate_consumer_load(config: PPAConfig | None = None) -> pd.Series:
    """
    Generate hourly consumer load [MWh/h] for the full PPA horizon.

    Parameters
    ----------
    config:
        PPAConfig instance.  Uses DEFAULT_CONFIG if None.

    Returns
    -------
    pd.Series
        Hourly load in MWh/h with a timezone-aware DatetimeIndex.
        Name: ``"consumer_load_mwh"``.
        Annual total equals ``config.load.annual_consumption_gwh × 1000`` MWh.
    """
    from ppa_engine.config import DEFAULT_CONFIG

    if config is None:
        config = DEFAULT_CONFIG

    lc = config.load
    dc = config.deal

    rng = np.random.default_rng(lc.seed)
    times = _build_timestamps(config)
    n = len(times)

    # -- Step 1: base hourly shape ------------------------------------------
    wd_shape = np.array(lc.weekday_hourly_shape)
    we_shape = np.array(lc.weekend_hourly_shape)

    hours = times.hour.to_numpy()
    is_weekend = times.dayofweek.to_numpy() >= 5
    base = np.where(is_weekend, we_shape[hours], wd_shape[hours])

    # -- Step 2: seasonal modulation ----------------------------------------
    doy = times.dayofyear.to_numpy().astype(float)
    seasonal = 1.0 + lc.seasonal_amplitude * np.cos(
        2.0 * np.pi * (doy - lc.seasonal_peak_day) / 365.25
    )

    # -- Step 3: log-normal multiplicative noise ----------------------------
    # Log-normal with μ=0, σ=noise_sigma in log-space ≈ ±noise_sigma variation
    log_noise = rng.normal(0.0, lc.noise_sigma, n)
    noise = np.exp(log_noise)

    # -- Step 4: combine and rescale to target annual consumption -----------
    raw_load = base * seasonal * noise

    # Number of years in the horizon (for per-year rescaling)
    start_year = pd.Timestamp(dc.start_date).year
    end_year = pd.Timestamp(dc.end_date).year

    # Rescale each calendar year independently so annual totals match target
    target_mwh = lc.annual_consumption_gwh * 1_000.0
    load = raw_load.copy()
    times_year = times.year.to_numpy()
    for year in range(start_year, end_year + 1):
        mask = times_year == year
        year_sum = raw_load[mask].sum()
        if year_sum > 0:
            load[mask] = raw_load[mask] * (target_mwh / year_sum)

    return pd.Series(load, index=times, name="consumer_load_mwh")
