from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.schemas.config import PPAConfigSchema, to_engine_config
from backend.schemas.results import ProfilesResponse

router = APIRouter()


@router.post("/profiles", response_model=ProfilesResponse)
def central_profiles(body: PPAConfigSchema) -> ProfilesResponse:
    """
    Generate the central-scenario hourly profiles over the full deal horizon.

    Returns three aligned series (solar production, market price, consumer load)
    at the seeds configured in `config.solar.seed` and `config.market.seed`.

    Payload size at default config: ~87,600 hourly rows × 3 series.
    """
    try:
        config = to_engine_config(body)
        config.validate()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    from ppa_engine.data.consumer_load import generate_consumer_load
    from ppa_engine.data.market_prices import generate_market_prices
    from ppa_engine.data.solar_production import generate_solar_production

    solar = generate_solar_production(config)
    prices = generate_market_prices(config)
    load = generate_consumer_load(config)

    timestamps = [ts.isoformat() for ts in solar.index]

    return ProfilesResponse(
        timestamps=timestamps,
        solar_mwh=[float(v) for v in solar.to_numpy()],
        market_price_eur_mwh=[float(v) for v in prices.to_numpy()],
        load_mwh=[float(v) for v in load.to_numpy()],
        n_hours=len(timestamps),
        timezone=config.location.tz,
    )
