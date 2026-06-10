from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.schemas.config import PPAConfigSchema, to_engine_config
from backend.schemas.results import ValuationMatrixResponse, ValuationRowSchema

router = APIRouter()


class ValuationMatrixRequest(BaseModel):
    config: PPAConfigSchema = PPAConfigSchema()
    base_strike: float = 65.0


@router.post("/matrix", response_model=ValuationMatrixResponse)
def valuation_matrix(body: ValuationMatrixRequest) -> ValuationMatrixResponse:
    try:
        config = to_engine_config(body.config)
        config.validate()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    from ppa_engine.valuation.engine import value_all_combinations

    from backend.cache import central_series

    solar, prices, load = central_series(config)

    df = value_all_combinations(solar, load, prices, config, base_strike=body.base_strike)
    rows = [ValuationRowSchema(**row) for row in df.to_dict(orient="records")]

    return ValuationMatrixResponse(rows=rows, base_strike=body.base_strike)
