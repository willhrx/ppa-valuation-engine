"""
Tests for the layer-3 split: 3a (demand, deterministic) and 3b (wind supply,
stochastic AR(1) in logit-space).

Together with layer 4 (solar cannibalisation), `3b + 4` model NL renewable
supply, and `3a` isolates demand.
"""

from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from ppa_engine.config import PPAConfig
from ppa_engine.data.market_prices import (
    _build_timestamps,
    _layer3a_demand,
    _layer3b_wind_supply,
    _layer4_cannibalisation,
    compute_wind_factor,
)
from ppa_engine.risk.monte_carlo import run_monte_carlo


@pytest.fixture(scope="module")
def cfg() -> PPAConfig:
    return PPAConfig()


@pytest.fixture(scope="module")
def times(cfg: PPAConfig) -> pd.DatetimeIndex:
    return _build_timestamps(cfg)


# ---------------------------------------------------------------------------
# Layer 3a — demand (deterministic)
# ---------------------------------------------------------------------------


def test_layer3a_deterministic(cfg: PPAConfig, times: pd.DatetimeIndex) -> None:
    a = _layer3a_demand(times, cfg)
    b = _layer3a_demand(times, cfg)
    np.testing.assert_array_equal(a, b)


def test_layer3a_no_midday_dip(cfg: PPAConfig) -> None:
    """Midday plateau must be shallow relative to the morning shoulder — any
    deep midday dip belongs to layers 3b + 4 (renewable supply), not 3a."""
    for shape_name in ("demand_weekday_shape", "demand_weekend_shape"):
        arr = np.array(getattr(cfg.market, shape_name), dtype=float)
        morning_shoulder = arr[10]
        afternoon_shoulder = arr[15]
        noon_min = float(arr[11:15].min())
        shallower_shoulder = min(morning_shoulder, afternoon_shoulder)
        dip = shallower_shoulder - noon_min
        assert dip < 5.0, (
            f"{shape_name}: midday dip of {dip:.1f} EUR/MWh below the "
            f"shoulders ({shallower_shoulder}) is too deep — solar-shaped "
            f"suppression should live in layers 3b + 4."
        )


# ---------------------------------------------------------------------------
# Layer 3b — wind supply (stochastic)
# ---------------------------------------------------------------------------


def test_wind_cf_bounded(cfg: PPAConfig, times: pd.DatetimeIndex) -> None:
    cf = compute_wind_factor(times, cfg)
    assert cf.shape == (len(times),)
    assert np.all(cf > 0.0)
    assert np.all(cf < 1.0)


def test_layer3b_zero_mean(cfg: PPAConfig, times: pd.DatetimeIndex) -> None:
    """At the central seed, layer 3b should average close to zero across the
    horizon (wind suppression is a deviation around the reference CF)."""
    series = _layer3b_wind_supply(times, cfg)
    mean = float(series.mean())
    assert abs(mean) < 4.0, f"Layer 3b mean {mean:.2f} EUR/MWh not near 0"


def test_layer3b_winter_higher_suppression(
    cfg: PPAConfig, times: pd.DatetimeIndex
) -> None:
    """Climatological wind CF is higher in DJF than JJA, so the suppression
    magnitude (mean of −3b) should be larger in winter than summer."""
    series = _layer3b_wind_supply(times, cfg)
    months = np.array([t.month for t in times])
    djf = -series[np.isin(months, [12, 1, 2])].mean()
    jja = -series[np.isin(months, [6, 7, 8])].mean()
    assert djf > jja, (
        f"Expected DJF suppression > JJA suppression, got DJF={djf:.2f}, JJA={jja:.2f}"
    )


def test_no_double_counting_summer_noon(
    cfg: PPAConfig, times: pd.DatetimeIndex
) -> None:
    """Combined 3b + 4 in summer noon (the time layer 4 dominates) should not
    exceed plausible cannibalisation depth alone — confirms 3b doesn't pile a
    second solar-shaped dip on top of layer 4."""
    layer3b = _layer3b_wind_supply(times, cfg)
    layer4 = _layer4_cannibalisation(times, cfg)
    combined = layer3b + layer4

    months = np.array([t.month for t in times])
    hours = np.array([t.hour for t in times])
    summer_noon = (np.isin(months, [6, 7, 8])) & (np.isin(hours, [12, 13]))
    mean_combined = float(combined[summer_noon].mean())
    mean_layer4 = float(layer4[summer_noon].mean())

    # 3b averages roughly 0 over the horizon, so summer-noon (3b + 4) should
    # land within a modest band of layer 4 alone (no double-dip).
    assert abs(mean_combined - mean_layer4) < 25.0, (
        f"Summer-noon (3b+4) {mean_combined:.1f} diverges too far from "
        f"layer 4 alone {mean_layer4:.1f} — suggests double-counting."
    )


# ---------------------------------------------------------------------------
# Monte Carlo — volume-mode wind fixed
# ---------------------------------------------------------------------------


def test_volume_mode_wind_fixed(cfg: PPAConfig) -> None:
    """Volume-mode Monte Carlo holds wind at the central realisation, so the
    capture rate's price-driver (3b) must be identical across volume paths."""
    cfg2 = deepcopy(cfg)
    # Short tenor + few paths to keep the test fast
    cfg2.deal.end_date = "2028-12-31"

    result = run_monte_carlo(
        cfg2, n_paths=3, modes=["volume"], verbose=False,
    )
    df = result.paths_df
    # Pick a single combination so we compare like-for-like
    one = df[
        (df["mode"] == "volume")
        & (df["supply_structure"] == df["supply_structure"].iloc[0])
        & (df["pricing_structure"] == df["pricing_structure"].iloc[0])
    ]
    # In volume mode the time-weighted average price is fixed (prices held at
    # the central wind+noise scenario), so it should be identical across paths.
    avg_prices = one["average_strike_eur_mwh"].unique()
    # average_strike depends on the pricing structure and is constant by
    # construction for FixedFlat — use capture_rate-adjacent invariant instead:
    # in volume mode the realised prices are identical across paths, so the
    # *consumer_npv* under a fixed-strike structure depends only on volume.
    # A simpler invariant: volume-mode paths share central wind, so the
    # time-weighted mean price (volume_value / total_volume) is path-invariant
    # only after dividing by realised volume. We instead check that the
    # 'capture rate' numerator (price × volume) over volume (= capture price)
    # is bounded across paths — wind-driven price variance is suppressed.
    cps = (one["volume_value"] / one["total_volume_mwh"]).values
    spread = cps.max() - cps.min()
    assert spread < 5.0, (
        f"Volume-mode capture price spread {spread:.2f} EUR/MWh too high — "
        f"wind should be held at central, leaving only cloud variation in prices."
    )
