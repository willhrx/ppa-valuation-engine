from __future__ import annotations

from pydantic import BaseModel, Field


class LocationConfigSchema(BaseModel):
    lat: float = 52.1
    lon: float = 5.1
    tz: str = "Europe/Amsterdam"
    altitude: float = 10.0


class SolarConfigSchema(BaseModel):
    capacity_mw: float = Field(default=50.0, gt=0)
    tilt_deg: float = 35.0
    azimuth_deg: float = 180.0
    performance_ratio: float = Field(default=0.80, gt=0, lt=1)
    degradation_rate: float = Field(default=0.005, gt=0, lt=0.02)
    cloud_factor_phi: float = Field(default=0.90, ge=0, le=1)
    cloud_factor_logit_scale: float = 0.7
    monthly_cloud_means: list[float] = Field(
        default=[0.38, 0.42, 0.50, 0.57, 0.63, 0.68, 0.68, 0.65, 0.58, 0.50, 0.42, 0.36],
        min_length=12,
        max_length=12,
    )
    seed: int = 42


class MarketPriceConfigSchema(BaseModel):
    base_price: float = 83.0
    drift: float = -1.5
    seasonal_amplitude: float = 15.0
    seasonal_peak_day: int = 15

    # Layer 3a — demand intra-day shape (deterministic, no midday dip)
    demand_weekday_shape: list[float] = Field(
        default=[
            -10, -12, -14, -14, -12, -10,
             -8,   8,  20,  18,  15,  13,
             11,  10,  10,  12,  18,  35,
             30,  22,  14,   5,   0,  -8,
        ],
        min_length=24,
        max_length=24,
    )
    demand_weekend_shape: list[float] = Field(
        default=[
            -12, -14, -16, -16, -14, -12,
            -10,  -5,   2,   5,   8,   9,
              9,   8,   8,   8,   9,  10,
             12,  10,   6,   2,  -2, -10,
        ],
        min_length=24,
        max_length=24,
    )
    demand_winter_uplift: float = 0.15
    demand_peak_day: int = 15

    # Layer 3b — Dutch system wind capacity factor (stochastic AR(1) in logit-space)
    monthly_wind_means: list[float] = Field(
        default=[0.42, 0.40, 0.38, 0.33, 0.28, 0.25,
                 0.24, 0.25, 0.30, 0.36, 0.40, 0.43],
        min_length=12,
        max_length=12,
    )
    wind_diurnal_logit_adder: list[float] = Field(
        default=[
             0.10,  0.10,  0.10,  0.10,  0.10,  0.08,
             0.05,  0.02, -0.02, -0.05, -0.07, -0.09,
            -0.10, -0.10, -0.09, -0.07, -0.05, -0.02,
             0.02,  0.05,  0.07,  0.08,  0.10,  0.10,
        ],
        min_length=24,
        max_length=24,
    )
    wind_cf_phi: float = Field(default=0.95, ge=0.0, lt=1.0)
    wind_cf_logit_scale: float = 0.60
    wind_reference_cf: float = Field(default=0.33, gt=0.0, lt=1.0)
    # Contract-relative ramp anchors: *_start applies in the first contract
    # year, *_end in the last; the engine interpolates linearly between them.
    beta_wind_start: float = 35.0
    beta_wind_end: float = 75.0
    wind_seed: int = 43

    cannibalisation_alpha_start: float = 40.0
    cannibalisation_alpha_end: float = 60.0
    # ρ ∈ [0, 1]. Couples layer-4 (cannibalisation) depth to the realised
    # asset cloud factor: high-irradiance days get a deeper midday dip,
    # overcast days a shallower one. ρ = 0 reproduces the legacy purely
    # diurnal layer 4. UI default matches the engine default (0.65).
    production_cannibalisation_correlation: float = Field(
        default=0.65, ge=0.0, le=1.0
    )

    # Layer 4 system-reference location: pvlib clear-sky POA computed here
    # provides the NL system-wide solar proxy shape (normalised peak = 1.0).
    # Defaults sit in the Noord-Brabant solar cluster — different from the
    # asset (Utrecht) so the proxy represents nationwide solar.
    system_solar_lat: float = Field(default=51.6, ge=50.0, le=54.0)
    system_solar_lon: float = Field(default=5.3, ge=3.0, le=8.0)
    system_solar_tz: str = "Europe/Amsterdam"
    system_solar_altitude: float = 10.0
    system_solar_tilt_deg: float = Field(default=30.0, ge=0.0, le=90.0)
    system_solar_azimuth_deg: float = Field(default=180.0, ge=0.0, le=360.0)
    ar1_phi: float = 0.70
    ar1_sigma: float = 8.0
    seed: int = 42


class ConsumerLoadConfigSchema(BaseModel):
    annual_consumption_gwh: float = Field(default=100.0, gt=0)
    seasonal_amplitude: float = 0.15
    seasonal_peak_day: int = 15
    weekday_hourly_shape: list[float] = Field(
        default=[
            0.55, 0.50, 0.48, 0.48, 0.52, 0.62,
            0.78, 0.90, 0.98, 1.02, 1.10, 1.06,
            1.00, 1.02, 1.00, 1.02, 1.05, 1.08,
            1.10, 1.04, 0.92, 0.80, 0.70, 0.60,
        ],
        min_length=24,
        max_length=24,
    )
    weekend_hourly_shape: list[float] = Field(
        default=[
            0.55, 0.50, 0.48, 0.48, 0.50, 0.58,
            0.68, 0.78, 0.85, 0.90, 0.92, 0.90,
            0.88, 0.85, 0.83, 0.83, 0.85, 0.88,
            0.88, 0.83, 0.75, 0.68, 0.62, 0.58,
        ],
        min_length=24,
        max_length=24,
    )
    noise_sigma: float = 0.05
    seed: int = 42


class DealConfigSchema(BaseModel):
    start_date: str = "2027-01-01"
    end_date: str = "2036-12-31"
    currency: str = "EUR"
    discount_rate: float = Field(default=0.06, gt=0, lt=0.30)


class PPAConfigSchema(BaseModel):
    location: LocationConfigSchema = Field(default_factory=LocationConfigSchema)
    solar: SolarConfigSchema = Field(default_factory=SolarConfigSchema)
    market: MarketPriceConfigSchema = Field(default_factory=MarketPriceConfigSchema)
    load: ConsumerLoadConfigSchema = Field(default_factory=ConsumerLoadConfigSchema)
    deal: DealConfigSchema = Field(default_factory=DealConfigSchema)


def to_engine_config(schema: PPAConfigSchema):
    """Convert Pydantic schema to ppa_engine dataclass hierarchy."""
    from ppa_engine.config import (
        PPAConfig,
        LocationConfig,
        SolarConfig,
        MarketPriceConfig,
        ConsumerLoadConfig,
        DealConfig,
    )

    return PPAConfig(
        location=LocationConfig(**schema.location.model_dump()),
        solar=SolarConfig(**schema.solar.model_dump()),
        market=MarketPriceConfig(**schema.market.model_dump()),
        load=ConsumerLoadConfig(**schema.load.model_dump()),
        deal=DealConfig(**schema.deal.model_dump()),
    )
