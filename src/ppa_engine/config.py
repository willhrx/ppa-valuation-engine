"""
config.py — All model assumptions as dataclasses.

Every forward-looking number in this engine is an explicit, named assumption.
Swapping assumptions and re-running is the core workflow.  Nothing is hardcoded
in functions; all parameters flow from a PPAConfig instance.

Primary scenario (see PPA_PROJECT_BRIEF.md):
  - 50 MW solar PV, Utrecht, NL
  - Offtaker: 100 GWh/year industrial consumer
  - Horizon: 2027-01-01 to 2036-12-31
  - Market: EPEX NL day-ahead, EUR/MWh
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


# ---------------------------------------------------------------------------
# Sub-configs
# ---------------------------------------------------------------------------


@dataclass
class LocationConfig:
    """Geographic location of the solar asset."""

    lat: float = 52.1          # decimal degrees N
    lon: float = 5.1           # decimal degrees E
    tz: str = "Europe/Amsterdam"
    altitude: float = 10.0     # metres above sea level


@dataclass
class SolarConfig:
    """
    Solar PV asset parameters and cloud-factor assumptions.

    Cloud factor is the fraction of clear-sky GHI actually reaching the panel,
    modelled as an AR(1) process in logit-space so the value stays in (0, 1).
    Monthly means reflect Dutch climatology: cloudier in winter, less so in
    summer, but still considerably cloudier than southern Europe.

    Reasonable ranges:
      - performance_ratio: 0.75 – 0.85 (reflects soiling, inverter losses, etc.)
      - degradation_rate: 0.004 – 0.007 per year
      - cloud_factor_phi: 0.80 – 0.95 (higher = more persistent weather systems)
      - monthly_cloud_means: 0.3–0.4 winter, 0.55–0.70 summer (NL climatology)
    """

    capacity_mw: float = 50.0
    tilt_deg: float = 35.0
    azimuth_deg: float = 180.0      # 180° = south-facing
    performance_ratio: float = 0.80
    degradation_rate: float = 0.005  # fraction per year (linear)
    cloud_factor_phi: float = 0.90   # AR(1) autocorrelation (hour-to-hour)
    cloud_factor_logit_scale: float = 0.7  # spread of AR(1) in logit-space
    # Monthly cloud factor means, index 0 = January, 11 = December
    monthly_cloud_means: List[float] = field(default_factory=lambda: [
        0.38, 0.42, 0.50, 0.57, 0.63, 0.68,
        0.68, 0.65, 0.58, 0.50, 0.42, 0.36,
    ])
    seed: int = 42


@dataclass
class MarketPriceConfig:
    """
    Dutch day-ahead wholesale electricity price assumptions (EPEX NL).

    Prices are built as a sum of additive layers (all in EUR/MWh):
      1.  Long-term level + drift         — highest uncertainty, flag in reports
      2.  Seasonal shape                  — winter high, summer low
      3a. Demand intra-day shape          — bimodal weekday/weekend demand, no
                                            embedded midday dip (deterministic)
      3b. Wind supply suppression          — stochastic AR(1) wind capacity
                                            factor; suppresses prices when wind
                                            generation is above its monthly mean
      4.  Solar cannibalisation (buildout) — growing midday discount, modulated
                                            by the asset's cloud factor (ρ)
      5.  AR(1) autocorrelated noise      — realistic price clustering

    Layer 3 used to be a single hand-coded 24-element hourly adder that baked a
    midday "dip" into what should have been a demand shape. It is now split:
    layer 3a is the demand shape (no midday dip — the noon plateau lies on the
    envelope between the morning and afternoon peaks), and layer 3b is a wind
    supply proxy that suppresses prices when realised Dutch wind output is
    above its monthly climatological mean. Together with layer 4 (solar
    cannibalisation), layer 3b completes the renewable-supply picture; demand
    is now isolated in layer 3a.

    Calibration targets (central scenario):
      - Annual average: ~80 EUR/MWh in 2027, declining to ~60 EUR/MWh by 2036
      - Peak hours (17:00–20:00, winter weekdays): 120–150 EUR/MWh
      - Solar peak (12:00–14:00, summer): 40–50 EUR/MWh in 2027,
        occasionally negative by 2034
      - Weekend nights (summer): 30–50 EUR/MWh
      - Capture rate for the solar asset: 0.65–0.85, declining over horizon

    Reasonable ranges:
      - base_price: 60 – 100 EUR/MWh
      - drift: -3 to 0 EUR/MWh/year
      - ar1_phi: 0.5 – 0.9
      - ar1_sigma: 5 – 15 EUR/MWh
      - beta_wind_2027 / beta_wind_2036: 20 – 80 EUR/MWh per unit-CF deviation
    """

    # Layer 1
    base_price: float = 83.0       # EUR/MWh, long-run level in 2027
    drift: float = -1.5            # EUR/MWh per year

    # Layer 2
    seasonal_amplitude: float = 15.0   # EUR/MWh peak-to-trough / 2
    seasonal_peak_day: int = 15        # day-of-year with highest prices (mid-Jan)

    # ---- Layer 3a — demand intra-day shape (deterministic) ----------------
    # Two 24-element vectors of EUR/MWh demand-driven adders. Indexed 00–23.
    # Weekday: bimodal industrial+residential pattern with a morning peak
    # around 08:00 and a steeper evening peak around 18:00. The midday plateau
    # (11:00–14:00) sits on the linear envelope between the two peaks — no
    # local minimum at noon. Weekend: flatter, lower overall.
    demand_weekday_shape: List[float] = field(default_factory=lambda: [
        -10, -12, -14, -14, -12, -10,   # 00–05  night trough
         -8,   8,  20,  18,  15,  13,   # 06–11  morning ramp + peak, holds
         11,  10,  10,  12,  18,  35,   # 12–17  plateau → afternoon ramp → peak
         30,  22,  14,   5,   0,  -8,   # 18–23  evening peak → decline
    ])
    demand_weekend_shape: List[float] = field(default_factory=lambda: [
        -12, -14, -16, -16, -14, -12,   # 00–05
        -10,  -5,   2,   5,   8,   9,   # 06–11
          9,   8,   8,   8,   9,  10,   # 12–17  flat midday plateau
         12,  10,   6,   2,  -2, -10,   # 18–23
    ])
    # Mild winter uplift on the demand shape (heating demand).
    demand_winter_uplift: float = 0.15        # fractional amplitude
    demand_peak_day: int = 15                 # day-of-year of peak demand (mid-Jan)

    # ---- Layer 3b — wind supply suppression (stochastic) ------------------
    # The wind capacity factor is an AR(1) process in logit-space (analogous
    # to the cloud factor), so values stay in (0, 1).  φ ≈ 0.95 reflects
    # multi-day persistence of synoptic wind systems over the NL grid.
    # Dutch wind climatology: higher in winter, lower in summer.
    monthly_wind_means: List[float] = field(default_factory=lambda: [
        0.42, 0.40, 0.38, 0.33, 0.28, 0.25,   # Jan–Jun
        0.24, 0.25, 0.30, 0.36, 0.40, 0.43,   # Jul–Dec
    ])
    # Small diurnal adder in logit-space; positive overnight, negative around
    # mid-afternoon (onshore wind is mildly anti-correlated with solar).
    wind_diurnal_logit_adder: List[float] = field(default_factory=lambda: [
         0.10,  0.10,  0.10,  0.10,  0.10,  0.08,  # 00–05
         0.05,  0.02, -0.02, -0.05, -0.07, -0.09,  # 06–11
        -0.10, -0.10, -0.09, -0.07, -0.05, -0.02,  # 12–17
         0.02,  0.05,  0.07,  0.08,  0.10,  0.10,  # 18–23
    ])
    wind_cf_phi: float = 0.95               # AR(1) autocorrelation
    wind_cf_logit_scale: float = 0.60       # spread of latent AR(1) in logit
    wind_reference_cf: float = 0.33         # subtract from CF before scaling
    # beta_wind grows linearly 2027→2036, reflecting NL offshore-wind buildout.
    # Calibrated as a free knob so that combined (3b + 4) reproduces the
    # capture-rate envelope 0.65–0.85 declining.
    beta_wind_2027: float = 35.0            # EUR/MWh per unit-CF deviation
    beta_wind_2036: float = 75.0            # grows to this by 2036
    wind_seed: int = 43                     # separate from other seeds

    # Layer 4 — cannibalisation (solar buildout suppressing midday prices)
    # Calibrated to achieve capture rate ~0.84 in 2027 declining to ~0.63 by 2036.
    # Re-tuned downward (was 70→115) after layer 4's proxy switched from the
    # legacy sin(hour)×sin(doy) synthetic to a pvlib clear-sky shape: with both
    # the asset and the system proxy sharing real solar geometry, the dip and
    # the production peak align hour-by-hour, so each unit of α now lands with
    # much more force.
    cannibalisation_alpha_2027: float = 40.0   # EUR/MWh at full solar proxy
    cannibalisation_alpha_2036: float = 60.0   # grows linearly to this by 2036

    # Layer 4 system-reference solar location (NL system-wide solar proxy).
    # The proxy shape is computed via pvlib clear-sky POA at this location,
    # normalised to peak = 1.0, replacing the legacy synthetic sin(hour)×sin(doy)
    # product. Defaults sit in the Noord-Brabant solar cluster (Den Bosch /
    # Eindhoven area) — the largest installed-capacity centroid in the NL grid.
    # Kept distinct from the asset location so the system proxy represents
    # nationwide solar, not the asset's own panels.
    system_solar_lat: float = 51.6
    system_solar_lon: float = 5.3
    system_solar_tz: str = "Europe/Amsterdam"
    system_solar_altitude: float = 10.0
    system_solar_tilt_deg: float = 30.0
    system_solar_azimuth_deg: float = 180.0

    # Production–cannibalisation correlation (ρ ∈ [0, 1])
    # Dutch solar generation is geographically correlated: when our asset has
    # clear skies, so does most of NL, which deepens the midday price dip.
    # ρ = 0  → original behaviour, layer-4 dip is purely diurnal/seasonal.
    # ρ = 1  → midday dip scales linearly with the asset's own cloud factor.
    # Empirical Dutch sky-correlation across the country sits around 0.6–0.75.
    # NB: ρ modulates only layer 4 (solar). Layer 3b (wind) uses an
    # independent AR(1) realisation in v1.
    production_cannibalisation_correlation: float = 0.65

    # Layer 5 — AR(1) noise
    ar1_phi: float = 0.70
    ar1_sigma: float = 8.0    # EUR/MWh, stationary standard deviation

    seed: int = 42


@dataclass
class ConsumerLoadConfig:
    """
    Industrial offtaker load profile assumptions.

    Shape: bimodal weekday profile (morning ~10:00, afternoon ~18:00),
    seasonal uplift in winter (space heating), stochastic noise layer.

    Reasonable ranges:
      - annual_consumption_gwh: 80 – 120 GWh
      - seasonal_amplitude: 0.10 – 0.20
      - noise_sigma: 0.03 – 0.10 (fraction of hourly mean)
    """

    annual_consumption_gwh: float = 100.0
    seasonal_amplitude: float = 0.15   # fractional winter uplift
    seasonal_peak_day: int = 15        # coldest day (matches price seasonal peak)
    # Normalised hourly multipliers for weekday (should roughly average to 1.0)
    weekday_hourly_shape: List[float] = field(default_factory=lambda: [
        0.55, 0.50, 0.48, 0.48, 0.52, 0.62,   # 00–05
        0.78, 0.90, 0.98, 1.02, 1.10, 1.06,   # 06–11  morning peak ~10:00
        1.00, 1.02, 1.00, 1.02, 1.05, 1.08,   # 12–17
        1.10, 1.04, 0.92, 0.80, 0.70, 0.60,   # 18–23  afternoon peak ~18:00
    ])
    weekend_hourly_shape: List[float] = field(default_factory=lambda: [
        0.55, 0.50, 0.48, 0.48, 0.50, 0.58,   # 00–05
        0.68, 0.78, 0.85, 0.90, 0.92, 0.90,   # 06–11
        0.88, 0.85, 0.83, 0.83, 0.85, 0.88,   # 12–17
        0.88, 0.83, 0.75, 0.68, 0.62, 0.58,   # 18–23
    ])
    noise_sigma: float = 0.05   # fraction of hourly value (log-normal noise)
    seed: int = 42


@dataclass
class DealConfig:
    """PPA deal-level parameters."""

    start_date: str = "2027-01-01"
    end_date: str = "2036-12-31"
    currency: str = "EUR"
    discount_rate: float = 0.06   # annual, for NPV calculations (Phase 2)


# ---------------------------------------------------------------------------
# Top-level config
# ---------------------------------------------------------------------------


@dataclass
class PPAConfig:
    """
    Root configuration object.  Pass an instance of this to every generator
    and calculator in the engine.  To create a sensitivity scenario, replace
    individual fields:

        cfg = PPAConfig()
        cfg.market.base_price = 90.0   # bull-case
        prices = generate_market_prices(cfg)
    """

    location: LocationConfig = field(default_factory=LocationConfig)
    solar: SolarConfig = field(default_factory=SolarConfig)
    market: MarketPriceConfig = field(default_factory=MarketPriceConfig)
    load: ConsumerLoadConfig = field(default_factory=ConsumerLoadConfig)
    deal: DealConfig = field(default_factory=DealConfig)

    def validate(self) -> None:
        """Validate config values, raising ValueError on any bad input.

        Checks every constraint the engine relies on. Call before any
        downstream generator if input may be user-edited.
        """
        import pandas as pd

        try:
            start = pd.Timestamp(self.deal.start_date)
            end = pd.Timestamp(self.deal.end_date)
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"Invalid deal dates: start={self.deal.start_date!r}, "
                f"end={self.deal.end_date!r}"
            ) from exc
        if start >= end:
            raise ValueError(
                f"deal.start_date ({self.deal.start_date}) must be strictly "
                f"before deal.end_date ({self.deal.end_date})."
            )

        if self.solar.capacity_mw <= 0:
            raise ValueError(
                f"solar.capacity_mw must be > 0 (got {self.solar.capacity_mw})."
            )

        if not (0.0 < self.solar.performance_ratio < 1.0):
            raise ValueError(
                f"solar.performance_ratio must be in (0, 1) "
                f"(got {self.solar.performance_ratio})."
            )

        if not (0.0 < self.solar.degradation_rate < 0.02):
            raise ValueError(
                f"solar.degradation_rate must be in (0, 0.02) "
                f"(got {self.solar.degradation_rate})."
            )

        if not (0.0 < self.deal.discount_rate < 0.30):
            raise ValueError(
                f"deal.discount_rate must be in (0, 0.30) "
                f"(got {self.deal.discount_rate})."
            )

        if self.load.annual_consumption_gwh <= 0:
            raise ValueError(
                f"load.annual_consumption_gwh must be > 0 "
                f"(got {self.load.annual_consumption_gwh})."
            )

        if len(self.solar.monthly_cloud_means) != 12:
            raise ValueError(
                f"solar.monthly_cloud_means must have length 12 "
                f"(got {len(self.solar.monthly_cloud_means)})."
            )

        if len(self.market.demand_weekday_shape) != 24:
            raise ValueError(
                f"market.demand_weekday_shape must have length 24 "
                f"(got {len(self.market.demand_weekday_shape)})."
            )
        if len(self.market.demand_weekend_shape) != 24:
            raise ValueError(
                f"market.demand_weekend_shape must have length 24 "
                f"(got {len(self.market.demand_weekend_shape)})."
            )

        if len(self.market.monthly_wind_means) != 12:
            raise ValueError(
                f"market.monthly_wind_means must have length 12 "
                f"(got {len(self.market.monthly_wind_means)})."
            )
        if not all(0.0 < m < 1.0 for m in self.market.monthly_wind_means):
            raise ValueError(
                "market.monthly_wind_means entries must all be in (0, 1)."
            )
        if len(self.market.wind_diurnal_logit_adder) != 24:
            raise ValueError(
                f"market.wind_diurnal_logit_adder must have length 24 "
                f"(got {len(self.market.wind_diurnal_logit_adder)})."
            )
        if not (0.0 <= self.market.wind_cf_phi < 1.0):
            raise ValueError(
                f"market.wind_cf_phi must be in [0, 1) "
                f"(got {self.market.wind_cf_phi})."
            )
        if not (0.0 < self.market.wind_reference_cf < 1.0):
            raise ValueError(
                f"market.wind_reference_cf must be in (0, 1) "
                f"(got {self.market.wind_reference_cf})."
            )

        rho = self.market.production_cannibalisation_correlation
        if not (0.0 <= rho <= 1.0):
            raise ValueError(
                f"market.production_cannibalisation_correlation must be in "
                f"[0, 1] (got {rho})."
            )

        if not (50.0 <= self.market.system_solar_lat <= 54.0):
            raise ValueError(
                f"market.system_solar_lat must be in [50, 54] "
                f"(got {self.market.system_solar_lat})."
            )
        if not (3.0 <= self.market.system_solar_lon <= 8.0):
            raise ValueError(
                f"market.system_solar_lon must be in [3, 8] "
                f"(got {self.market.system_solar_lon})."
            )
        if not (0.0 <= self.market.system_solar_tilt_deg <= 90.0):
            raise ValueError(
                f"market.system_solar_tilt_deg must be in [0, 90] "
                f"(got {self.market.system_solar_tilt_deg})."
            )
        if not (0.0 <= self.market.system_solar_azimuth_deg <= 360.0):
            raise ValueError(
                f"market.system_solar_azimuth_deg must be in [0, 360] "
                f"(got {self.market.system_solar_azimuth_deg})."
            )


# Convenience: a ready-to-use default config instance
DEFAULT_CONFIG = PPAConfig()
