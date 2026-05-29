"""
Tests for the production-cannibalisation correlation in layer 4 of the
synthetic Dutch price model.

The asset-level cloud factor now modulates the midday cannibalisation dip:
clear-sky days (low cloud cover, high production) should see a deeper dip,
overcast days a shallower one. ρ = 0 must reproduce the legacy behaviour.
"""

from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from ppa_engine.config import PPAConfig
from ppa_engine.data.market_prices import (
    _build_timestamps,
    _layer4_cannibalisation,
    generate_market_prices,
)
from ppa_engine.data.solar_production import (
    compute_cloud_factor,
    generate_solar_production,
)
from ppa_engine.valuation.capture import capture_rate


def _cfg(rho: float) -> PPAConfig:
    cfg = PPAConfig()
    cfg.market.production_cannibalisation_correlation = rho
    return cfg


def test_rho_zero_reproduces_legacy_layer4():
    """ρ = 0 must give an identical layer-4 series with or without cloud."""
    cfg = _cfg(0.0)
    times = _build_timestamps(cfg)
    cloud = compute_cloud_factor(times, cfg)

    legacy = _layer4_cannibalisation(times, cfg)
    with_cloud = _layer4_cannibalisation(times, cfg, cloud_factor=cloud)

    np.testing.assert_array_equal(legacy, with_cloud)


def test_clear_day_deepens_dip():
    """At ρ > 0, an artificial clear-sky cloud array must produce a deeper
    midday dip than the legacy unmodulated proxy."""
    cfg = _cfg(0.7)
    times = _build_timestamps(cfg)

    # Force "perfectly clear" skies: cloud factor at the upper bound of the
    # monthly mean × 1.5 (well above typical).
    monthly_means = np.asarray(cfg.solar.monthly_cloud_means, dtype=float)
    months = np.array([t.month - 1 for t in times])
    clear_cloud = np.clip(monthly_means[months] * 1.5, 0.0, 0.999)

    legacy = _layer4_cannibalisation(times, cfg)  # no cloud
    deepened = _layer4_cannibalisation(times, cfg, cloud_factor=clear_cloud)

    # Layer 4 is non-positive; deeper dip = more negative. Restrict to summer
    # midday where the proxy is materially non-zero.
    mask = (times.month.isin([5, 6, 7, 8])) & (times.hour.isin([11, 12, 13, 14]))
    assert deepened[mask].mean() < legacy[mask].mean()


def test_cloudy_day_shallows_dip():
    """Heavy overcast (cloud factor well below monthly mean) must shrink the
    midday dip relative to the legacy proxy."""
    cfg = _cfg(0.7)
    times = _build_timestamps(cfg)

    monthly_means = np.asarray(cfg.solar.monthly_cloud_means, dtype=float)
    months = np.array([t.month - 1 for t in times])
    overcast_cloud = monthly_means[months] * 0.4  # ~60% below typical

    legacy = _layer4_cannibalisation(times, cfg)
    shallow = _layer4_cannibalisation(times, cfg, cloud_factor=overcast_cloud)

    mask = (times.month.isin([5, 6, 7, 8])) & (times.hour.isin([11, 12, 13, 14]))
    # Shallow dip is closer to zero → higher mean (less negative).
    assert shallow[mask].mean() > legacy[mask].mean()


def test_correlation_lowers_capture_rate():
    """End-to-end check: turning the correlation on should depress the asset
    capture rate (clear days now coincide with cheaper midday prices) by a
    measurable but bounded amount on the central scenario."""
    cfg_off = _cfg(0.0)
    cfg_on = _cfg(0.7)

    prices_off = generate_market_prices(cfg_off)
    prices_on = generate_market_prices(cfg_on)
    solar = generate_solar_production(cfg_off)  # production identical (same seed)

    cr_off = float(capture_rate(prices_off, solar))
    cr_on = float(capture_rate(prices_on, solar))

    assert cr_on < cr_off, (
        f"Capture rate did not decline with correlation on: "
        f"off={cr_off:.4f} on={cr_on:.4f}"
    )
    # Sanity bound: the effect should be material (>0.2pp) but not catastrophic.
    delta = cr_off - cr_on
    assert 0.002 < delta < 0.10, (
        f"Capture-rate impact out of expected range: Δ={delta:.4f}"
    )


def test_pydantic_default_matches_engine():
    """Backend schema default must match the engine dataclass default so the
    UI form and the simulation agree out of the box."""
    from backend.schemas.config import MarketPriceConfigSchema

    cfg = PPAConfig()
    schema = MarketPriceConfigSchema()
    assert (
        schema.production_cannibalisation_correlation
        == cfg.market.production_cannibalisation_correlation
    )


def test_config_validate_rejects_out_of_range():
    cfg = PPAConfig()
    cfg.market.production_cannibalisation_correlation = 1.5
    with pytest.raises(ValueError, match="production_cannibalisation_correlation"):
        cfg.validate()

    cfg.market.production_cannibalisation_correlation = -0.1
    with pytest.raises(ValueError, match="production_cannibalisation_correlation"):
        cfg.validate()
