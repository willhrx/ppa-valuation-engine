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

    Prices are built as a sum of five additive layers (all in EUR/MWh):
      1. Long-term level + drift         — highest uncertainty, flag in reports
      2. Seasonal shape                  — winter high, summer low
      3. Intra-day shape                 — morning/evening peaks, weekday/weekend
      4. Cannibalisation (solar buildout) — growing midday discount
      5. AR(1) autocorrelated noise      — realistic price clustering

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
    """

    # Layer 1
    base_price: float = 80.0       # EUR/MWh, long-run level in 2027
    drift: float = -1.5            # EUR/MWh per year

    # Layer 2
    seasonal_amplitude: float = 15.0   # EUR/MWh peak-to-trough / 2
    seasonal_peak_day: int = 15        # day-of-year with highest prices (mid-Jan)

    # Layer 3 — intra-day adders (EUR/MWh) relative to daily level
    # Indexed 00–23.  Weekday: industrial demand pattern with morning + evening peak.
    # Weekend: flatter, lower overall.
    weekday_hourly_adder: List[float] = field(default_factory=lambda: [
        -10, -12, -14, -14, -12, -10,   # 00–05  night
         -8,   8,  20,  14,   8,   2,   # 06–11  morning ramp + peak
         -5,  -5,   0,   8,  15,  35,   # 12–17  midday dip → evening ramp
         30,  22,  14,   5,   0,  -8,   # 18–23  evening peak → decline
    ])
    weekend_hourly_adder: List[float] = field(default_factory=lambda: [
        -12, -14, -16, -16, -14, -12,   # 00–05
        -10,  -5,   2,   5,   8,   8,   # 06–11
          2,   2,   2,   4,   6,  10,   # 12–17
         12,  10,   6,   2,  -2, -10,   # 18–23
    ])

    # Layer 4 — cannibalisation (solar buildout suppressing midday prices)
    cannibalisation_alpha_2027: float = 12.0   # EUR/MWh at full solar proxy
    cannibalisation_alpha_2036: float = 37.0   # grows linearly to this by 2036

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


# Convenience: a ready-to-use default config instance
DEFAULT_CONFIG = PPAConfig()
