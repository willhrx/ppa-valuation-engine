from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, HTTPException

from backend.schemas.config import PPAConfigSchema, to_engine_config
from backend.schemas.results import PreviewResponse, TimeSeriesPoint

router = APIRouter()


def _to_ts_list(series: pd.Series, mask: pd.Series) -> list[TimeSeriesPoint]:
    sub = series[mask]
    return [
        TimeSeriesPoint(timestamp=idx.isoformat(), value=round(float(v), 4))
        for idx, v in sub.items()
    ]


@router.post("/preview", response_model=PreviewResponse)
def preview_central_scenario(body: PPAConfigSchema) -> PreviewResponse:
    try:
        config = to_engine_config(body)
        config.validate()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    from ppa_engine.data.solar_production import generate_solar_production
    from ppa_engine.data.market_prices import generate_market_prices
    from ppa_engine.data.consumer_load import generate_consumer_load
    from ppa_engine.valuation.capture import capture_rate

    solar = generate_solar_production(config)
    prices = generate_market_prices(config)
    load = generate_consumer_load(config)

    start = pd.Timestamp(config.deal.start_date)
    end = pd.Timestamp(config.deal.end_date)
    n_years = (end - start).days / 365.25

    solar_total_gwh = float(solar.sum() / 1000)
    solar_annual_yield = float(solar.sum() / config.solar.capacity_mw / n_years)
    avg_price = float(prices.mean())
    total_load_gwh = float(load.sum() / 1000)
    hedge_ratio = float(solar.sum() / load.sum())
    cap_rate = float(capture_rate(prices, solar))

    # Sample week: first full week of July 2027 (168 hourly points)
    week_start = pd.Timestamp("2027-07-07", tz=config.location.tz)
    week_end = pd.Timestamp("2027-07-14", tz=config.location.tz)
    mask = (solar.index >= week_start) & (solar.index < week_end)

    return PreviewResponse(
        solar_annual_yield_kwh_per_kwp=round(solar_annual_yield, 1),
        solar_total_gwh=round(solar_total_gwh, 1),
        avg_price_eur_mwh=round(avg_price, 2),
        total_load_gwh=round(total_load_gwh, 1),
        hedge_ratio=round(hedge_ratio, 3),
        capture_rate=round(cap_rate, 4),
        sample_week_solar=_to_ts_list(solar, mask),
        sample_week_prices=_to_ts_list(prices, mask),
        sample_week_load=_to_ts_list(load, mask),
    )
