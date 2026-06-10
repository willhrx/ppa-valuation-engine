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
    # Long-form path rows are several MB at 500 paths; the UI only needs the
    # risk summary (which now carries per-combo NPV arrays for histograms).
    include_paths: bool = False


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

    paths = (
        [MonteCarloPathRow(**row) for row in mc.paths_df.to_dict(orient="records")]
        if body.include_paths
        else []
    )
    central_rows = [ValuationRowSchema(**row) for row in mc.central_df.to_dict(orient="records")]

    # Per-combo NPV arrays for client-side histograms: (mode, supply, pricing)
    # -> sorted-by-path producer NPVs, rounded to whole EUR.
    mode_key = {"joint": "npvs_joint", "price": "npvs_price", "volume": "npvs_volume"}
    npv_arrays: dict[tuple[str, str, str], list[float]] = {}
    grouped = mc.paths_df.sort_values("path").groupby(
        ["mode", "supply_structure", "pricing_structure"], sort=False
    )["producer_npv"]
    for (mode, supply, pricing), series in grouped:
        npv_arrays[(mode, supply, pricing)] = [round(v) for v in series.to_list()]

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
            npvs_joint=npv_arrays.get(("joint", c.supply_structure, c.pricing_structure), []),
            npvs_price=npv_arrays.get(("price", c.supply_structure, c.pricing_structure), []),
            npvs_volume=npv_arrays.get(("volume", c.supply_structure, c.pricing_structure), []),
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
