from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.schemas.config import PPAConfigSchema, to_engine_config

router = APIRouter()


@router.get("/defaults", response_model=PPAConfigSchema)
def config_defaults() -> PPAConfigSchema:
    """Return a fresh PPAConfig with engine defaults, used to seed the UI form."""
    return PPAConfigSchema()


@router.post("/validate", response_model=PPAConfigSchema)
def config_validate(body: PPAConfigSchema) -> PPAConfigSchema:
    """
    Run the engine's domain validation on the submitted config.

    Pydantic handles per-field bounds at parse time; this endpoint additionally
    runs `PPAConfig.validate()` which checks cross-field invariants (e.g. that
    deal.start_date is strictly before deal.end_date).

    Returns the validated config unchanged on success; 422 with the engine's
    error message on failure.
    """
    try:
        engine_config = to_engine_config(body)
        engine_config.validate()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return body
