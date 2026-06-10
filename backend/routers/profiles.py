from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.schemas.config import PPAConfigSchema, to_engine_config
from backend.schemas.results import CaptureTimelineResponse, ProfilesResponse

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

    from backend.cache import central_series

    solar, prices, load = central_series(config)

    timestamps = [ts.isoformat() for ts in solar.index]

    return ProfilesResponse(
        timestamps=timestamps,
        solar_mwh=[float(v) for v in solar.to_numpy()],
        market_price_eur_mwh=[float(v) for v in prices.to_numpy()],
        load_mwh=[float(v) for v in load.to_numpy()],
        n_hours=len(timestamps),
        timezone=config.location.tz,
    )


@router.post("/capture-timeline", response_model=CaptureTimelineResponse)
def capture_timeline(body: PPAConfigSchema) -> CaptureTimelineResponse:
    """
    Per-calendar-year capture rate of the central scenario — how the
    production-weighted price compares to the baseload average as
    cannibalisation deepens over the horizon.
    """
    try:
        config = to_engine_config(body)
        config.validate()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    from ppa_engine.valuation.capture import capture_rate

    from backend.cache import central_series

    solar, prices, _load = central_series(config)

    index_years = prices.index.year
    years = sorted(int(y) for y in index_years.unique())
    rates = []
    for year in years:
        mask = index_years == year
        rates.append(round(float(capture_rate(prices[mask], solar[mask])), 4))

    return CaptureTimelineResponse(
        years=years,
        capture_rate=rates,
        horizon_capture_rate=round(float(capture_rate(prices, solar)), 4),
    )
