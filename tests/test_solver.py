"""Tests for solver.py (Phase 4)."""

import numpy as np
import pytest

from ppa_engine.config import PPAConfig
from ppa_engine.data.consumer_load import generate_consumer_load
from ppa_engine.data.market_prices import generate_market_prices
from ppa_engine.data.solar_production import generate_solar_production
from ppa_engine.pricing.fixed import FixedFlat, FixedEscalated
from ppa_engine.structures.baseload import Baseload
from ppa_engine.structures.pay_as_produced import PayAsProduced
from ppa_engine.structures.pay_as_nominated import PayAsNominated
from ppa_engine.valuation import (
    solve_break_even,
    solve_consumer_ceiling,
    solve_fair_strike_cross_structure,
    solve_negotiation_range,
    solve_producer_irr,
    compute_tornado,
)
from ppa_engine.valuation.engine import value_ppa


@pytest.fixture(scope="module")
def base_data():
    cfg = PPAConfig()
    solar = generate_solar_production(cfg)
    prices = generate_market_prices(cfg)
    load = generate_consumer_load(cfg)
    return cfg, solar, prices, load


def test_break_even_npv_is_zero(base_data):
    cfg, solar, prices, load = base_data
    result = solve_break_even(PayAsProduced(), solar, load, prices, cfg)
    assert result.converged
    assert abs(result.achieved_npv) < 100.0  # within EUR 100 of zero


def test_break_even_positive_target_npv(base_data):
    cfg, solar, prices, load = base_data
    target = 5_000_000.0
    result = solve_break_even(PayAsProduced(), solar, load, prices, cfg, target_npv=target)
    assert result.converged
    assert abs(result.achieved_npv - target) < 1000.0


def test_break_even_monotone(base_data):
    cfg, solar, prices, load = base_data
    r0 = solve_break_even(PayAsProduced(), solar, load, prices, cfg, target_npv=0.0)
    r1 = solve_break_even(PayAsProduced(), solar, load, prices, cfg, target_npv=10_000_000.0)
    assert r1.strike_eur_mwh > r0.strike_eur_mwh


def test_baseload_higher_break_even_than_pay_as_produced(base_data):
    cfg, solar, prices, load = base_data
    pap = solve_break_even(PayAsProduced(), solar, load, prices, cfg)
    bl = solve_break_even(Baseload(), solar, load, prices, cfg)
    assert bl.strike_eur_mwh > pap.strike_eur_mwh, (
        "Baseload must require a higher strike to break even"
    )


def test_consumer_ceiling_equals_break_even(base_data):
    cfg, solar, prices, load = base_data
    be = solve_break_even(PayAsProduced(), solar, load, prices, cfg, target_npv=0.0)
    ceil = solve_consumer_ceiling(PayAsProduced(), solar, load, prices, cfg)
    assert abs(be.strike_eur_mwh - ceil.strike_eur_mwh) < 0.02


def test_all_structures_converge(base_data):
    cfg, solar, prices, load = base_data
    for supply in [PayAsProduced(), PayAsNominated(), Baseload()]:
        result = solve_break_even(supply, solar, load, prices, cfg)
        assert result.converged, f"{type(supply).__name__} solver did not converge"


def test_negotiation_range_zero_target(base_data):
    cfg, solar, prices, load = base_data
    rng = solve_negotiation_range(PayAsProduced(), solar, load, prices, cfg,
                                  target_producer_npv=0.0)
    assert abs(rng.spread_eur_mwh) < 0.05  # floor == ceiling when target=0


def test_negotiation_range_positive_target(base_data):
    cfg, solar, prices, load = base_data
    rng = solve_negotiation_range(PayAsProduced(), solar, load, prices, cfg,
                                  target_producer_npv=10_000_000.0)
    assert rng.spread_eur_mwh < 0, "Deal not viable: floor > ceiling"


def test_producer_irr_strike_above_break_even(base_data):
    cfg, solar, prices, load = base_data
    be = solve_break_even(PayAsProduced(), solar, load, prices, cfg)
    irr = solve_producer_irr(PayAsProduced(), solar, load, prices, cfg, target_irr=0.09)
    assert irr.strike_eur_mwh > be.strike_eur_mwh


def test_escalated_pricing_solver(base_data):
    cfg, solar, prices, load = base_data
    result = solve_break_even(
        PayAsProduced(), solar, load, prices, cfg,
        pricing_class=FixedEscalated,
        pricing_kwargs={"escalation_rate": 0.02},
    )
    assert result.converged
    assert 30.0 < result.strike_eur_mwh < 150.0


def test_tornado_top_driver_is_price(base_data):
    cfg, solar, prices, load = base_data
    tornado = compute_tornado(PayAsProduced(), FixedFlat, 65.0, solar, load, prices, cfg)
    assert tornado.entries[0].parameter == "Base price (EUR/MWh)", (
        f"Expected base_price as top driver, got {tornado.entries[0].parameter}"
    )


def test_tornado_entries_sorted(base_data):
    cfg, solar, prices, load = base_data
    tornado = compute_tornado(PayAsProduced(), FixedFlat, 65.0, solar, load, prices, cfg)
    swings = [e.abs_swing for e in tornado.entries]
    assert swings == sorted(swings, reverse=True)


def test_fair_strike_p50_equality(base_data):
    cfg, solar, prices, load = base_data
    result = solve_fair_strike_cross_structure(
        PayAsProduced(), Baseload(), FixedFlat,
        solar, load, prices, cfg,
        strike_a=52.0, n_paths=100,
    )
    rel_diff = abs(result.p50_npv_a - result.p50_npv_b) / max(abs(result.p50_npv_a), 1.0)
    assert rel_diff < 0.03, f"P50 NPVs not equal: {rel_diff:.3%} difference"


def test_fair_strike_baseload_above_pay_as_produced(base_data):
    cfg, solar, prices, load = base_data
    result = solve_fair_strike_cross_structure(
        PayAsProduced(), Baseload(), FixedFlat,
        solar, load, prices, cfg,
        strike_a=52.0, n_paths=100,
    )
    assert result.fair_strike_b > result.strike_a, (
        "Baseload fair strike must be above PayAsProduced strike"
    )
