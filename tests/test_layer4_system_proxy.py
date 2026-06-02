"""
Tests for the pvlib-derived NL system-wide solar proxy used in layer 4
cannibalisation. Replaces the legacy synthetic sin(hour)×sin(doy) product.

The headline acceptance criterion is *alignment*: the cannibalisation dip
should bottom out at the same hour as the asset's solar production peaks,
since both now share pvlib's solar geometry.
"""

import numpy as np
import pandas as pd
import pytest

from ppa_engine.config import PPAConfig
from ppa_engine.data.market_prices import (
    _build_timestamps,
    _layer4_cannibalisation,
    compute_system_solar_proxy,
)
from ppa_engine.data.solar_production import generate_solar_production


@pytest.fixture(scope="module")
def cfg() -> PPAConfig:
    return PPAConfig()


@pytest.fixture(scope="module")
def times(cfg: PPAConfig) -> pd.DatetimeIndex:
    return _build_timestamps(cfg)


@pytest.fixture(scope="module")
def proxy(cfg: PPAConfig, times: pd.DatetimeIndex) -> np.ndarray:
    return compute_system_solar_proxy(times, cfg)


# ---------------------------------------------------------------------------
# Proxy shape
# ---------------------------------------------------------------------------


def test_system_proxy_bounded(proxy: np.ndarray) -> None:
    assert np.all(proxy >= 0.0), "proxy contains negatives"
    assert np.all(proxy <= 1.0 + 1e-12), "proxy exceeds 1.0"
    assert float(proxy.max()) == pytest.approx(1.0, abs=1e-9), (
        "proxy not normalised so peak = 1.0"
    )


def test_system_proxy_zero_at_night(
    proxy: np.ndarray, times: pd.DatetimeIndex,
) -> None:
    hours = np.array([t.hour for t in times])
    deep_night = np.isin(hours, [0, 1, 2, 3, 23])
    assert float(proxy[deep_night].max()) < 1e-6, (
        "Proxy not effectively zero in deep night hours"
    )


def test_system_proxy_summer_peak(
    proxy: np.ndarray, times: pd.DatetimeIndex,
) -> None:
    """Peak proxy hour should land in late spring / summer near solar noon.
    For a tilted south-facing panel the instantaneous clear-sky POA can peak
    in May (best angle-of-incidence × air-mass tradeoff) rather than at the
    June solstice; accept May-July."""
    peak_idx = int(np.argmax(proxy))
    peak_t = times[peak_idx]
    assert peak_t.month in (5, 6, 7), (
        f"Peak month {peak_t.month}, expected May-Jul"
    )
    assert peak_t.hour in (11, 12, 13, 14), (
        f"Peak hour {peak_t.hour}, expected 11-14 local"
    )


def test_system_proxy_winter_energy_low(
    proxy: np.ndarray, times: pd.DatetimeIndex,
) -> None:
    """Winter (DJF) should deliver far less total solar energy than summer
    (JJA): short days dominate, even though peak instantaneous POA on a
    tilted panel stays moderate in winter (low-elevation sun strikes the
    tilted panel close to perpendicular)."""
    months = np.array([t.month for t in times])
    djf_total = float(proxy[np.isin(months, [12, 1, 2])].sum())
    jja_total = float(proxy[np.isin(months, [6, 7, 8])].sum())
    ratio = djf_total / jja_total
    assert ratio < 0.45, (
        f"DJF/JJA energy ratio {ratio:.2f} too high — winter days are short, "
        f"total cannibalisation pressure should be much smaller"
    )


# ---------------------------------------------------------------------------
# Layer 4 — alignment with asset production
# ---------------------------------------------------------------------------


def test_layer4_aligned_with_pvlib_solar_peak(
    cfg: PPAConfig, times: pd.DatetimeIndex, proxy: np.ndarray,
) -> None:
    """Headline check — across late-June days, the average hour of deepest
    layer-4 suppression should match the average asset solar-peak hour
    within ±1 hour, and the vast majority of individual days should align
    within ±2 hours. The slight per-day jitter comes from cloud-factor
    modulation and from the system reference using a different tilt (30°)
    than the asset (35°)."""
    layer4 = _layer4_cannibalisation(times, cfg, system_solar_proxy=proxy)
    solar = generate_solar_production(cfg)

    df = pd.DataFrame(
        {"layer4": layer4, "solar": solar.values},
        index=times,
    )
    summer = df[(df.index.month == 6) & (df.index.day >= 20)]
    by_day = summer.groupby(summer.index.date)

    deltas = []
    for _, day in by_day:
        deepest = day["layer4"].idxmin().hour
        peak = day["solar"].idxmax().hour
        deltas.append(deepest - peak)
    deltas = np.array(deltas)

    mean_offset = float(np.mean(deltas))
    within_2h = float(np.mean(np.abs(deltas) <= 2))
    assert abs(mean_offset) <= 1.0, (
        f"Mean layer-4-trough vs asset-peak offset {mean_offset:.2f}h "
        f"exceeds ±1h — systematic misalignment"
    )
    assert within_2h >= 0.85, (
        f"Only {within_2h:.0%} of late-June days align within ±2h — too "
        f"much per-day jitter between layer-4 trough and asset peak"
    )


def test_layer4_night_zero(
    cfg: PPAConfig, times: pd.DatetimeIndex, proxy: np.ndarray,
) -> None:
    """Hours with zero system proxy must have zero layer 4 contribution."""
    layer4 = _layer4_cannibalisation(times, cfg, system_solar_proxy=proxy)
    night_mask = proxy < 1e-9
    assert np.all(np.abs(layer4[night_mask]) < 1e-6), (
        "Layer 4 non-zero at hours where system proxy is zero"
    )
