"""
solver.py — Break-even price solver and fair-strike optimizer (Phase 4).

Implements:
  solve_break_even()             — find strike where producer NPV = target
  solve_producer_irr()           — find strike meeting a target IRR
  solve_consumer_ceiling()       — find max strike where consumer NPV >= 0
  solve_negotiation_range()      — producer floor to consumer ceiling range
  solve_fair_strike_cross_structure() — find equivalent strike across supply structures
  compute_tornado()              — rank assumptions by |ΔNPV| sensitivity
  compute_option_premium()       — value floor/cap options via MC paths

The break-even price is the anchor for all pricing conversations:
  - Producer's floor: the minimum price covering LCOE
  - Consumer's ceiling: the price at which PPA equals buying at spot
  - The fair-strike optimizer makes structural choice legible:
    "Baseload at €X = PayAsProduced at €52 in P50 NPV terms"
"""

from __future__ import annotations

import inspect
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from ppa_engine.config import PPAConfig
from ppa_engine.pricing.base import PricingStructure
from ppa_engine.pricing.fixed import FixedFlat
from ppa_engine.structures.base import SupplyStructure
from ppa_engine.utils.ar1 import _ar1_filter
from ppa_engine.valuation.engine import value_ppa
from ppa_engine.valuation.npv import compute_npv

if TYPE_CHECKING:
    from ppa_engine.risk.monte_carlo import MonteCarloResult


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SolverResult:
    """Result of a single Brent's method solve."""

    strike_eur_mwh: float
    achieved_npv: float
    target_npv: float
    n_iterations: int
    converged: bool
    supply_structure: str
    pricing_structure: str


@dataclass
class NegotiationRange:
    """
    The negotiable price interval for a given supply structure.

    producer_floor   : minimum strike where producer_npv >= target_producer_npv
    consumer_ceiling : maximum strike where consumer_npv >= 0
    midpoint         : (floor + ceiling) / 2
    spread_eur_mwh   : ceiling - floor (negative if deal is not viable at target)
    """

    supply_structure: str
    producer_floor: SolverResult
    consumer_ceiling: SolverResult
    midpoint: float
    spread_eur_mwh: float


@dataclass
class FairStrikeResult:
    """Result of the cross-structure equivalence solve."""

    structure_a: str
    structure_b: str
    strike_a: float
    fair_strike_b: float     # Strike for B giving equal P50 NPV as A at strike_a
    p50_npv_a: float
    p50_npv_b: float         # Should be ~= p50_npv_a after convergence
    pricing_structure: str
    n_paths: int


@dataclass
class TornadoEntry:
    """Single parameter entry in a tornado chart."""

    parameter: str
    base_value: float
    low_value: float
    high_value: float
    npv_base: float
    npv_low: float
    npv_high: float
    delta_npv_low: float     # npv_low - npv_base
    delta_npv_high: float    # npv_high - npv_base
    abs_swing: float         # |delta_low| + |delta_high|; used for ranking


@dataclass
class TornadoResult:
    """Ranked sensitivity results for a given supply × pricing combination."""

    entries: list[TornadoEntry]  # sorted by abs_swing descending
    supply_structure: str
    pricing_structure: str
    base_strike: float


@dataclass
class OptionPremiumResult:
    """Incremental value of structural options (floor, cap) from MC paths."""

    supply_structure: str
    pricing_structure_uncapped: str
    pricing_structure_capped: str
    p50_npv_uncapped: float
    p50_npv_capped: float
    incremental_npv: float           # p50_capped - p50_uncapped
    incremental_eur_per_mwh: float   # incremental_npv / total_volume_mwh
    n_paths: int


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _make_pricing(
    pricing_class: type, strike_val: float, pricing_kwargs: dict
) -> PricingStructure:
    """
    Instantiate a pricing structure, handling different constructor signatures.

    FixedFlat uses 'strike'; FixedEscalated uses 'base_strike'. This helper
    detects the first positional parameter name automatically.
    """
    sig = inspect.signature(pricing_class.__init__)
    first_param = next(
        (p for p in sig.parameters if p != "self"),
        "strike",
    )
    return pricing_class(**{first_param: strike_val}, **pricing_kwargs)


def _get_nested(obj: object, path: str) -> float:
    """Get a value from a nested dataclass using dot notation (e.g., 'market.base_price')."""
    for part in path.split("."):
        obj = getattr(obj, part)
    return obj  # type: ignore[return-value]


def _set_nested(obj: object, path: str, value: float) -> None:
    """Set a value in a nested dataclass using dot notation."""
    parts = path.split(".")
    for part in parts[:-1]:
        obj = getattr(obj, part)
    setattr(obj, parts[-1], value)


# Seed constants for fair-strike evaluation paths (separate namespace from MC ensembles)
_FAIR_SOLAR_BASE = 505_000
_FAIR_PRICE_BASE = 606_000
_FAIR_PRIME = 1_000_033  # Different prime to guarantee no seed collisions with MC


def _fair_solar_series(
    times: pd.DatetimeIndex,
    poa_clearsky: np.ndarray,
    degradation: np.ndarray,
    config: PPAConfig,
    i: int,
) -> pd.Series:
    """Generate solar path i for the fair-strike evaluation ensemble."""
    from scipy.special import expit, logit

    sc = config.solar
    T = len(times)
    phi = sc.cloud_factor_phi
    scale = sc.cloud_factor_logit_scale
    sigma_innov = np.sqrt(1.0 - phi * phi)

    monthly_logit = np.array([logit(m) for m in sc.monthly_cloud_means])
    hour_logit_mean = monthly_logit[times.month.to_numpy() - 1]

    rng = np.random.default_rng(_FAIR_SOLAR_BASE + i * _FAIR_PRIME)
    eps = rng.standard_normal(T)
    driver = sigma_innov * eps
    driver[0] = eps[0]
    z = _ar1_filter(driver, phi)

    cloud = expit(hour_logit_mean + scale * z)
    out = (
        sc.capacity_mw
        * sc.performance_ratio
        * (poa_clearsky * cloud / 1000.0)
        * degradation
    )
    return pd.Series(out, index=times, name="solar_production_mwh")


def _fair_price_series(
    times: pd.DatetimeIndex,
    deterministic_layers: np.ndarray,
    config: PPAConfig,
    i: int,
) -> pd.Series:
    """Generate price path i for the fair-strike evaluation ensemble."""
    mc = config.market
    T = len(times)
    phi = mc.ar1_phi
    sigma = mc.ar1_sigma
    sigma_innov = sigma * np.sqrt(1.0 - phi * phi)

    rng = np.random.default_rng(_FAIR_PRICE_BASE + i * _FAIR_PRIME)
    eps = rng.standard_normal(T)
    driver = sigma_innov * eps
    driver[0] = sigma * eps[0]
    noise = _ar1_filter(driver, phi)

    return pd.Series(
        deterministic_layers + noise, index=times, name="market_price_eur_mwh"
    )


# ---------------------------------------------------------------------------
# Core Brent solvers
# ---------------------------------------------------------------------------


def solve_break_even(
    supply_structure: SupplyStructure,
    solar: pd.Series,
    load: pd.Series,
    market_prices: pd.Series,
    config: PPAConfig,
    target_npv: float = 0.0,
    strike_bounds: tuple[float, float] = (0.0, 300.0),
    pricing_class: type = FixedFlat,
    pricing_kwargs: dict | None = None,
) -> SolverResult:
    """
    Find the fixed strike price at which producer NPV equals target_npv.

    Uses scipy.optimize.brentq. The objective f(strike) = producer_npv - target_npv
    is monotone in strike for fixed pricing structures, so convergence is guaranteed
    provided f changes sign within strike_bounds (true for all realistic PPAs).

    Parameters
    ----------
    supply_structure : SupplyStructure
    solar, load, market_prices : pd.Series
        Full 10-year hourly time series.
    config : PPAConfig
    target_npv : float
        0.0 for break-even; positive for a minimum-profit floor.
    strike_bounds : tuple[float, float]
        Search interval. (0, 300) covers all realistic EUR/MWh values.
    pricing_class : type
        Defaults to FixedFlat. For FixedEscalated pass escalation_rate in
        pricing_kwargs (the base_strike parameter is varied by the solver).
    pricing_kwargs : dict | None
        Additional kwargs for pricing_class (e.g., {'escalation_rate': 0.02}).

    Returns
    -------
    SolverResult
    """
    if pricing_kwargs is None:
        pricing_kwargs = {}

    call_count = [0]

    def objective(s: float) -> float:
        call_count[0] += 1
        pricing = _make_pricing(pricing_class, s, pricing_kwargs)
        result = value_ppa(supply_structure, pricing, solar, load, market_prices, config)
        return result.producer_npv - target_npv

    try:
        strike_solved, info = brentq(
            objective,
            a=strike_bounds[0],
            b=strike_bounds[1],
            xtol=0.01,
            rtol=1e-6,
            full_output=True,
        )
    except ValueError as exc:
        raise ValueError(
            f"Brent solver failed for {type(supply_structure).__name__} "
            f"with {pricing_class.__name__}: {exc}"
        ) from exc

    achieved_npv = value_ppa(
        supply_structure,
        _make_pricing(pricing_class, strike_solved, pricing_kwargs),
        solar, load, market_prices, config,
    ).producer_npv

    return SolverResult(
        strike_eur_mwh=float(strike_solved),
        achieved_npv=float(achieved_npv),
        target_npv=target_npv,
        n_iterations=call_count[0],
        converged=bool(info.converged),
        supply_structure=type(supply_structure).__name__,
        pricing_structure=pricing_class.__name__,
    )


def solve_producer_irr(
    supply_structure: SupplyStructure,
    solar: pd.Series,
    load: pd.Series,
    market_prices: pd.Series,
    config: PPAConfig,
    target_irr: float,
    capex_eur: float | None = None,
) -> SolverResult:
    """
    Find the strike where the producer achieves target_irr on PPA cash flows.

    Converts target_irr to an equivalent target_npv using the approximation:
        target_npv = capex * (target_irr - r) / r

    Parameters
    ----------
    target_irr : float
        Annualised target IRR (e.g., 0.08 for 8 %).
    capex_eur : float | None
        Capital expenditure [EUR]. Defaults to capacity_mw * 1_000_000
        (€1M/MW is a reasonable proxy for NL utility-scale solar).
    """
    if capex_eur is None:
        capex_eur = config.solar.capacity_mw * 1_000_000.0

    r = config.deal.discount_rate
    target_npv = capex_eur * (target_irr - r) / r

    return solve_break_even(
        supply_structure, solar, load, market_prices, config, target_npv=target_npv
    )


def solve_consumer_ceiling(
    supply_structure: SupplyStructure,
    solar: pd.Series,
    load: pd.Series,
    market_prices: pd.Series,
    config: PPAConfig,
) -> SolverResult:
    """
    Find the maximum strike where the consumer NPV >= 0.

    Under zero-sum mechanics, consumer_npv = 0 iff producer_npv = 0. So this
    is identical to solve_break_even(target_npv=0) in the deterministic case.
    The consumer ceiling is where buying under PPA exactly equals buying at spot.
    """
    return solve_break_even(
        supply_structure, solar, load, market_prices, config, target_npv=0.0
    )


def solve_negotiation_range(
    supply_structure: SupplyStructure,
    solar: pd.Series,
    load: pd.Series,
    market_prices: pd.Series,
    config: PPAConfig,
    target_producer_npv: float = 0.0,
) -> NegotiationRange:
    """
    Compute the full negotiation range: producer floor to consumer ceiling.

    With target_producer_npv=0, floor == ceiling (zero-sum). Set a positive
    target to represent the producer's LCOE-based profit floor, creating an
    asymmetry: the spread shows whether the deal is viable at that requirement.

    Parameters
    ----------
    target_producer_npv : float
        Minimum acceptable producer NPV [EUR]. Use solve_producer_irr to derive
        this from a target IRR.
    """
    producer_floor = solve_break_even(
        supply_structure, solar, load, market_prices, config,
        target_npv=target_producer_npv,
    )
    consumer_ceiling = solve_consumer_ceiling(
        supply_structure, solar, load, market_prices, config
    )

    midpoint = (producer_floor.strike_eur_mwh + consumer_ceiling.strike_eur_mwh) / 2.0
    spread = consumer_ceiling.strike_eur_mwh - producer_floor.strike_eur_mwh

    return NegotiationRange(
        supply_structure=type(supply_structure).__name__,
        producer_floor=producer_floor,
        consumer_ceiling=consumer_ceiling,
        midpoint=float(midpoint),
        spread_eur_mwh=float(spread),
    )


# ---------------------------------------------------------------------------
# Fair-strike cross-structure optimizer
# ---------------------------------------------------------------------------


def solve_fair_strike_cross_structure(
    structure_a: SupplyStructure,
    structure_b: SupplyStructure,
    pricing_class: type,
    solar: pd.Series,
    load: pd.Series,
    market_prices: pd.Series,
    config: PPAConfig,
    strike_a: float,
    mc_result: "MonteCarloResult | None" = None,
    n_paths: int = 500,
    use_p50: bool = True,
) -> FairStrikeResult:
    """
    Find the strike for structure B that gives equal P50 NPV to structure A at strike_a.

    Makes structural choice legible: "Baseload at €X = PayAsProduced at €52
    in P50 NPV terms."

    The comparison uses a shared set of (solar, price) paths so structural
    differences — not path luck — drive the NPV gap.

    Algorithm
    ---------
    1. Generate n_paths (solar, price) pairs using dedicated seeds.
    2. Compute structure A NPVs at strike_a for all paths → P50_a.
    3. Pre-compute settled volumes for structure B for all paths (no strike
       dependence — volumes depend only on solar and load, not pricing).
    4. For each candidate strike_b: compute all NPVs using pre-computed volumes.
       This is fast (vectorised NPV sum, no structure logic).
    5. brentq finds zero of: f(strike_b) = P50_npv_b(strike_b) - P50_a.

    Performance: with n_paths=500, brentq typically converges in 10-12
    iterations. Each iteration: 500 compute_npv calls ~ 0.5s. Total: ~5-8s.

    Parameters
    ----------
    structure_a : SupplyStructure
        Reference structure (e.g., PayAsProduced).
    structure_b : SupplyStructure
        Target structure (e.g., Baseload) for which we find the fair strike.
    pricing_class : type
        Pricing structure class applied to both A and B (e.g., FixedFlat).
    solar, load, market_prices : pd.Series
        Central scenario data (used only for context; MC paths are generated
        internally with fresh seeds).
    config : PPAConfig
    strike_a : float
        Fixed strike for structure A [EUR/MWh].
    mc_result : MonteCarloResult | None
        If provided and its pricing_structure matches, P50_a is read directly
        from the joint ensemble (faster). If None, P50_a is computed freshly.
    n_paths : int
        Number of paths for the internal MC. 200–500 is sufficient.
    use_p50 : bool
        If True, equate P50 NPVs. If False, equate mean NPVs.

    Returns
    -------
    FairStrikeResult
    """
    from ppa_engine.data.market_prices import (
        _build_timestamps, _layer1_level, _layer2_seasonal,
        _layer3a_demand, _layer3b_wind_supply, _layer4_cannibalisation,
        compute_system_solar_proxy, compute_wind_factor,
    )
    from ppa_engine.data.solar_production import _clearsky_poa

    pct = 50.0
    supply_name_a = type(structure_a).__name__
    pricing_name = pricing_class.__name__

    # Step 1: pre-compute deterministic inputs (pvlib done once)
    times = _build_timestamps(config)
    poa_clearsky = _clearsky_poa(times, config)
    # System-wide solar shape for layer 4 (pvlib NL reference) — deterministic,
    # computed once and reused across all paths.
    system_solar_proxy = compute_system_solar_proxy(times, config)
    start_year = pd.Timestamp(config.deal.start_date).year
    year_offset = times.year.to_numpy() - start_year
    degradation = 1.0 - config.solar.degradation_rate * year_offset
    # Hold wind at the central realisation across all fair-strike paths so
    # structural differences (not path luck) drive the strike gap.
    central_wind = compute_wind_factor(times, config)
    det_price = (
        _layer1_level(times, config)
        + _layer2_seasonal(times, config)
        + _layer3a_demand(times, config)
        + _layer3b_wind_supply(times, config, wind_cf=central_wind)
        + _layer4_cannibalisation(
            times, config, system_solar_proxy=system_solar_proxy,
        )
    )

    # Step 2: generate shared n_paths (solar, price) pairs.
    # Both A and B are evaluated on the SAME paths so structural differences
    # — not path luck — drive the NPV gap.
    solar_paths = [
        _fair_solar_series(times, poa_clearsky, degradation, config, i)
        for i in range(n_paths)
    ]
    price_paths = [
        _fair_price_series(times, det_price, config, i)
        for i in range(n_paths)
    ]

    # Step 3: compute P50_a from the shared paths at strike_a
    pricing_a = _make_pricing(pricing_class, strike_a, {})
    npvs_a = np.array([
        compute_npv(
            structure_a.settled_volume(solar_paths[i], load),
            pricing_a.strike_price(price_paths[i]),
            price_paths[i],
            config,
        )
        for i in range(n_paths)
    ])
    p50_npv_a = float(np.percentile(npvs_a, pct))

    # Step 4: pre-compute settled volumes for structure B (no strike dependence)
    volumes_b = [structure_b.settled_volume(s, load) for s in solar_paths]

    # Step 5: define P50 NPV function for structure B at a given strike.
    # Uses pre-computed volumes — only the NPV step runs inside brentq.
    def p50_npv_b_at_strike(strike_b: float) -> float:
        pricing_b = _make_pricing(pricing_class, strike_b, {})
        npvs = np.array([
            compute_npv(
                volumes_b[i],
                pricing_b.strike_price(price_paths[i]),
                price_paths[i],
                config,
            )
            for i in range(n_paths)
        ])
        return float(np.percentile(npvs, pct))

    # Step 6: solve for fair_strike_b
    def objective(s: float) -> float:
        return p50_npv_b_at_strike(s) - p50_npv_a

    try:
        fair_strike_b = float(brentq(objective, a=0.0, b=300.0, xtol=0.01, rtol=1e-6))
    except ValueError as exc:
        raise ValueError(
            f"Fair-strike solver failed for {type(structure_b).__name__}: {exc}"
        ) from exc

    p50_npv_b = p50_npv_b_at_strike(fair_strike_b)

    return FairStrikeResult(
        structure_a=supply_name_a,
        structure_b=type(structure_b).__name__,
        strike_a=strike_a,
        fair_strike_b=fair_strike_b,
        p50_npv_a=p50_npv_a,
        p50_npv_b=float(p50_npv_b),
        pricing_structure=pricing_name,
        n_paths=n_paths,
    )


# ---------------------------------------------------------------------------
# Tornado chart
# ---------------------------------------------------------------------------

# Default sensitivity parameters: (config_attr_path, label, std_dev)
_DEFAULT_TORNADO_PARAMS: list[tuple[str, str, float]] = [
    ("market.base_price",                  "Base price (EUR/MWh)",        10.0),
    ("market.drift",                       "Price drift (EUR/MWh/yr)",     0.5),
    ("market.ar1_sigma",                   "Price AR(1) sigma",            3.0),
    ("market.cannibalisation_alpha_end",   "Cannib. alpha (end of tenor)", 10.0),
    ("solar.cloud_factor_phi",             "Cloud persistence",            0.05),
    ("solar.degradation_rate",             "Degradation rate",             0.001),
    ("deal.discount_rate",                 "Discount rate",                0.01),
]


def compute_tornado(
    supply_structure: SupplyStructure,
    pricing_class: type,
    base_strike: float,
    solar: pd.Series,
    load: pd.Series,
    market_prices: pd.Series,
    config: PPAConfig,
    parameters: list[tuple[str, str, float]] | None = None,
) -> TornadoResult:
    """
    Rank config parameters by |ΔNPV| when each is varied ±1 std dev.

    For each parameter: vary it by ±std_dev from its base value, regenerate
    affected data series (prices if market param, solar if solar param), and
    compute the resulting NPV. Entries are sorted by abs_swing descending.

    Parameters
    ----------
    parameters : list[tuple[str, str, float]] | None
        List of (config_attr_path, display_label, std_dev). Uses a sensible
        default set covering price level, drift, volatility, cannibalisation,
        cloud persistence, degradation, and discount rate.

    Returns
    -------
    TornadoResult with entries sorted by abs_swing descending.
    """
    from ppa_engine.data.market_prices import generate_market_prices
    from ppa_engine.data.solar_production import generate_solar_production

    if parameters is None:
        parameters = _DEFAULT_TORNADO_PARAMS

    pricing = _make_pricing(pricing_class, base_strike, {})
    npv_base = value_ppa(
        supply_structure, pricing, solar, load, market_prices, config
    ).producer_npv

    entries = []
    for attr_path, label, std_dev in parameters:
        base_val = float(_get_nested(config, attr_path))

        npv_low = _npv_at_perturbed(
            attr_path, base_val - std_dev,
            supply_structure, pricing_class, base_strike,
            solar, load, market_prices, config,
        )
        npv_high = _npv_at_perturbed(
            attr_path, base_val + std_dev,
            supply_structure, pricing_class, base_strike,
            solar, load, market_prices, config,
        )

        delta_low = npv_low - npv_base
        delta_high = npv_high - npv_base

        entries.append(
            TornadoEntry(
                parameter=label,
                base_value=base_val,
                low_value=base_val - std_dev,
                high_value=base_val + std_dev,
                npv_base=npv_base,
                npv_low=npv_low,
                npv_high=npv_high,
                delta_npv_low=delta_low,
                delta_npv_high=delta_high,
                abs_swing=abs(delta_low) + abs(delta_high),
            )
        )

    entries.sort(key=lambda e: e.abs_swing, reverse=True)

    return TornadoResult(
        entries=entries,
        supply_structure=type(supply_structure).__name__,
        pricing_structure=pricing_class.__name__,
        base_strike=base_strike,
    )


def _npv_at_perturbed(
    attr_path: str,
    new_val: float,
    supply_structure: SupplyStructure,
    pricing_class: type,
    base_strike: float,
    solar: pd.Series,
    load: pd.Series,
    market_prices: pd.Series,
    config: PPAConfig,
) -> float:
    """Compute NPV after perturbing one config parameter."""
    from ppa_engine.data.market_prices import generate_market_prices
    from ppa_engine.data.solar_production import generate_solar_production

    cfg_p = deepcopy(config)
    _set_nested(cfg_p, attr_path, new_val)

    if attr_path.startswith("market."):
        prices_p = generate_market_prices(cfg_p)
        solar_p = solar
    elif attr_path.startswith("solar."):
        solar_p = generate_solar_production(cfg_p)
        prices_p = market_prices
    else:
        prices_p = market_prices
        solar_p = solar

    pricing = _make_pricing(pricing_class, base_strike, {})
    return value_ppa(
        supply_structure, pricing, solar_p, load, prices_p, cfg_p
    ).producer_npv


# ---------------------------------------------------------------------------
# Option premium
# ---------------------------------------------------------------------------


def compute_option_premium(
    supply_structure: SupplyStructure,
    uncapped_pricing: PricingStructure,
    capped_pricing: PricingStructure,
    mc_result: "MonteCarloResult",
) -> OptionPremiumResult:
    """
    Compute the incremental value of structural options (floor, cap) via MC paths.

    Reads P50 NPVs from mc_result.paths_df — no new simulation required.
    Both uncapped and capped pricing structures must be present in mc_result.

    Parameters
    ----------
    supply_structure : SupplyStructure
    uncapped_pricing : PricingStructure
        e.g. FixedFlat(strike=65)
    capped_pricing : PricingStructure
        e.g. IndexedWithFloorCap(index_factor=0.95, floor=40, cap=120)
    mc_result : MonteCarloResult
        Must contain joint paths for both pricing structures.

    Returns
    -------
    OptionPremiumResult
        incremental_eur_per_mwh: the per-MWh cost of the option to the producer.
        Positive = capped structure is better for the producer (e.g., floor helps).
        Negative = cap hurts the producer (upside is cut off).
    """
    supply_name = type(supply_structure).__name__
    uncapped_name = type(uncapped_pricing).__name__
    capped_name = type(capped_pricing).__name__

    def _get_p50(pricing_name: str) -> float:
        mask = (
            (mc_result.paths_df.supply_structure == supply_name)
            & (mc_result.paths_df.pricing_structure == pricing_name)
            & (mc_result.paths_df["mode"] == "joint")
        )
        arr = mc_result.paths_df[mask]["producer_npv"].to_numpy()
        if len(arr) == 0:
            raise ValueError(
                f"No joint paths found for {supply_name}/{pricing_name} in mc_result."
            )
        return float(np.percentile(arr, 50.0))

    p50_uncapped = _get_p50(uncapped_name)
    p50_capped = _get_p50(capped_name)
    incremental_npv = p50_capped - p50_uncapped

    central_row = mc_result.central_df[
        mc_result.central_df.supply_structure == supply_name
    ].iloc[0]
    total_volume_mwh = float(central_row.total_volume_mwh)

    incremental_eur_per_mwh = (
        incremental_npv / total_volume_mwh if total_volume_mwh > 0 else 0.0
    )

    return OptionPremiumResult(
        supply_structure=supply_name,
        pricing_structure_uncapped=uncapped_name,
        pricing_structure_capped=capped_name,
        p50_npv_uncapped=p50_uncapped,
        p50_npv_capped=p50_capped,
        incremental_npv=incremental_npv,
        incremental_eur_per_mwh=incremental_eur_per_mwh,
        n_paths=mc_result.n_paths,
    )
