from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.schemas.config import PPAConfigSchema, to_engine_config
from backend.schemas.results import (
    FairStrikeResultSchema,
    NegotiationRangeResponse,
    NegotiationRangeSchema,
    SolverResultSchema,
    TornadoEntrySchema,
    TornadoResultSchema,
)

router = APIRouter()

SupplyKey = Literal["pay_as_produced", "pay_as_nominated", "baseload"]
PricingKey = Literal["fixed_flat", "fixed_escalated", "indexed_with_floor_cap", "floating"]


def _supply_instance(key: SupplyKey):
    from ppa_engine.structures.pay_as_produced import PayAsProduced
    from ppa_engine.structures.pay_as_nominated import PayAsNominated
    from ppa_engine.structures.baseload import Baseload

    return {
        "pay_as_produced": PayAsProduced,
        "pay_as_nominated": PayAsNominated,
        "baseload": Baseload,
    }[key]()


def _pricing_class(key: PricingKey):
    from ppa_engine.pricing.fixed import FixedFlat, FixedEscalated
    from ppa_engine.pricing.indexed import IndexedWithFloorCap
    from ppa_engine.pricing.floating import Floating

    return {
        "fixed_flat": FixedFlat,
        "fixed_escalated": FixedEscalated,
        "indexed_with_floor_cap": IndexedWithFloorCap,
        "floating": Floating,
    }[key]


def _central_series(config):
    from ppa_engine.data.solar_production import generate_solar_production
    from ppa_engine.data.market_prices import generate_market_prices
    from ppa_engine.data.consumer_load import generate_consumer_load

    return (
        generate_solar_production(config),
        generate_market_prices(config),
        generate_consumer_load(config),
    )


# ---------------------------------------------------------------------------
# Negotiation range
# ---------------------------------------------------------------------------


class NegotiationRangeRequest(BaseModel):
    config: PPAConfigSchema = PPAConfigSchema()
    target_producer_npv: float = 0.0


@router.post("/negotiation-range", response_model=NegotiationRangeResponse)
def negotiation_range(body: NegotiationRangeRequest) -> NegotiationRangeResponse:
    try:
        config = to_engine_config(body.config)
        config.validate()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    from ppa_engine.valuation.solver import solve_negotiation_range

    solar, prices, load = _central_series(config)

    ranges = []
    for key in ("pay_as_produced", "pay_as_nominated", "baseload"):
        supply = _supply_instance(key)  # type: ignore[arg-type]
        result = solve_negotiation_range(supply, solar, load, prices, config, body.target_producer_npv)
        ranges.append(
            NegotiationRangeSchema(
                supply_structure=result.supply_structure,
                producer_floor=SolverResultSchema(**result.producer_floor.__dict__),
                consumer_ceiling=SolverResultSchema(**result.consumer_ceiling.__dict__),
                midpoint=result.midpoint,
                spread_eur_mwh=result.spread_eur_mwh,
            )
        )

    return NegotiationRangeResponse(ranges=ranges)


# ---------------------------------------------------------------------------
# Tornado sensitivity
# ---------------------------------------------------------------------------


class TornadoRequest(BaseModel):
    config: PPAConfigSchema = PPAConfigSchema()
    supply_structure: SupplyKey = "pay_as_produced"
    pricing_structure: PricingKey = "fixed_flat"
    base_strike: float = 65.0


@router.post("/tornado", response_model=TornadoResultSchema)
def tornado(body: TornadoRequest) -> TornadoResultSchema:
    try:
        config = to_engine_config(body.config)
        config.validate()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    from ppa_engine.valuation.solver import compute_tornado

    solar, prices, load = _central_series(config)
    supply = _supply_instance(body.supply_structure)
    pcls = _pricing_class(body.pricing_structure)

    result = compute_tornado(supply, pcls, body.base_strike, solar, load, prices, config)

    return TornadoResultSchema(
        entries=[TornadoEntrySchema(**e.__dict__) for e in result.entries],
        supply_structure=result.supply_structure,
        pricing_structure=result.pricing_structure,
        base_strike=result.base_strike,
    )


# ---------------------------------------------------------------------------
# Fair-strike cross-structure
# ---------------------------------------------------------------------------


class FairStrikeRequest(BaseModel):
    config: PPAConfigSchema = PPAConfigSchema()
    structure_a: SupplyKey = "pay_as_produced"
    structure_b: SupplyKey = "baseload"
    pricing_structure: Literal["fixed_flat", "fixed_escalated"] = "fixed_flat"
    strike_a: float = 65.0
    n_paths: int = 200


@router.post("/fair-strike", response_model=FairStrikeResultSchema)
def fair_strike(body: FairStrikeRequest) -> FairStrikeResultSchema:
    try:
        config = to_engine_config(body.config)
        config.validate()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    from ppa_engine.valuation.solver import solve_fair_strike_cross_structure

    solar, prices, load = _central_series(config)
    supply_a = _supply_instance(body.structure_a)
    supply_b = _supply_instance(body.structure_b)
    pcls = _pricing_class(body.pricing_structure)

    result = solve_fair_strike_cross_structure(
        supply_a,
        supply_b,
        pcls,
        solar,
        load,
        prices,
        config,
        strike_a=body.strike_a,
        n_paths=body.n_paths,
    )

    return FairStrikeResultSchema(**result.__dict__)
