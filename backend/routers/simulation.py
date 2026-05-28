from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.schemas.config import PPAConfigSchema, to_engine_config
from backend.schemas.results import (
    ComboRiskSummarySchema,
    MonteCarloPathRow,
    MonteCarloResponse,
    PathDistributionSchema,
    RiskSummarySchema,
    ValuationRowSchema,
    VarianceDecompositionSchema,
)

router = APIRouter()


class SimulationRequest(BaseModel):
    config: PPAConfigSchema = PPAConfigSchema()
    n_paths: int = 500
    base_strike: float = 65.0
    modes: list[Literal["joint", "price", "volume"]] = ["joint", "price", "volume"]


@router.post("/simulate", response_model=MonteCarloResponse)
def run_simulation(body: SimulationRequest) -> MonteCarloResponse:
    try:
        config = to_engine_config(body.config)
        config.validate()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    from ppa_engine.risk.monte_carlo import run_monte_carlo
    from ppa_engine.risk.metrics import summarise_risk

    mc = run_monte_carlo(
        config=config,
        n_paths=body.n_paths,
        base_strike=body.base_strike,
        modes=list(body.modes),
        verbose=False,
    )
    risk = summarise_risk(mc)

    paths = [MonteCarloPathRow(**row) for row in mc.paths_df.to_dict(orient="records")]
    central_rows = [ValuationRowSchema(**row) for row in mc.central_df.to_dict(orient="records")]

    combo_schemas = [
        ComboRiskSummarySchema(
            supply_structure=c.supply_structure,
            pricing_structure=c.pricing_structure,
            central_producer_npv=c.central_producer_npv,
            central_capture_rate=c.central_capture_rate,
            joint=PathDistributionSchema(**c.joint.__dict__),
            price_only=PathDistributionSchema(**c.price_only.__dict__),
            volume_only=PathDistributionSchema(**c.volume_only.__dict__),
            variance_decomp=VarianceDecompositionSchema(**c.variance_decomp.__dict__),
        )
        for c in risk.combinations
    ]

    return MonteCarloResponse(
        paths=paths,
        central_rows=central_rows,
        risk_summary=RiskSummarySchema(
            combinations=combo_schemas,
            n_paths=risk.n_paths,
            base_strike=risk.base_strike,
        ),
        n_paths=mc.n_paths,
        base_strike=mc.base_strike,
        elapsed_seconds=mc.elapsed_seconds,
    )
