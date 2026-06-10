from __future__ import annotations

from pydantic import BaseModel


class ProfilesResponse(BaseModel):
    """
    Full-horizon raw hourly series (column-oriented).

    All four lists have identical length (n_hours over the deal horizon).
    timestamps are ISO 8601 with timezone (Europe/Amsterdam).
    """

    timestamps: list[str]
    solar_mwh: list[float]
    market_price_eur_mwh: list[float]
    load_mwh: list[float]
    n_hours: int
    timezone: str


class CaptureTimelineResponse(BaseModel):
    """Per-calendar-year capture rate of the central scenario."""

    years: list[int]
    capture_rate: list[float]
    horizon_capture_rate: float


class ValuationRowSchema(BaseModel):
    supply_structure: str
    pricing_structure: str
    producer_npv: float
    consumer_npv: float
    total_volume_mwh: float
    average_strike_eur_mwh: float
    capture_rate: float
    volume_value: float
    profile_value: float


class ValuationMatrixResponse(BaseModel):
    rows: list[ValuationRowSchema]
    base_strike: float


class PathDistributionSchema(BaseModel):
    mean: float
    std: float
    p10: float
    p50: float
    p90: float
    var_95: float
    es_95: float
    prob_negative: float


class VarianceDecompositionSchema(BaseModel):
    total_variance: float
    price_share: float
    volume_share: float
    interaction_share: float


class ComboRiskSummarySchema(BaseModel):
    supply_structure: str
    pricing_structure: str
    central_producer_npv: float
    central_capture_rate: float
    joint: PathDistributionSchema
    price_only: PathDistributionSchema
    volume_only: PathDistributionSchema
    variance_decomp: VarianceDecompositionSchema
    # Per-path producer NPVs (rounded to whole EUR) for client-side
    # histograms. One entry per simulated path; empty when the mode was
    # not part of the run.
    npvs_joint: list[float] = []
    npvs_price: list[float] = []
    npvs_volume: list[float] = []


class RiskSummarySchema(BaseModel):
    combinations: list[ComboRiskSummarySchema]
    n_paths: int
    base_strike: float


class MonteCarloPathRow(BaseModel):
    mode: str
    path: int
    supply_structure: str
    pricing_structure: str
    producer_npv: float
    consumer_npv: float
    total_volume_mwh: float
    average_strike_eur_mwh: float
    capture_rate: float
    volume_value: float
    profile_value: float


class MonteCarloResponse(BaseModel):
    # Full long-form path rows are several MB at 500 paths and unused by the
    # frontend; they are only populated when the request sets include_paths.
    paths: list[MonteCarloPathRow] = []
    central_rows: list[ValuationRowSchema]
    risk_summary: RiskSummarySchema
    n_paths: int
    base_strike: float
    elapsed_seconds: float


class SolverResultSchema(BaseModel):
    strike_eur_mwh: float
    achieved_npv: float
    target_npv: float
    n_iterations: int
    converged: bool
    supply_structure: str
    pricing_structure: str


class NegotiationRangeSchema(BaseModel):
    supply_structure: str
    producer_floor: SolverResultSchema
    consumer_ceiling: SolverResultSchema
    midpoint: float
    spread_eur_mwh: float


class NegotiationRangeResponse(BaseModel):
    ranges: list[NegotiationRangeSchema]


class TornadoEntrySchema(BaseModel):
    parameter: str
    base_value: float
    low_value: float
    high_value: float
    npv_base: float
    npv_low: float
    npv_high: float
    delta_npv_low: float
    delta_npv_high: float
    abs_swing: float


class TornadoResultSchema(BaseModel):
    entries: list[TornadoEntrySchema]
    supply_structure: str
    pricing_structure: str
    base_strike: float


class FairStrikeResultSchema(BaseModel):
    structure_a: str
    structure_b: str
    strike_a: float
    fair_strike_b: float
    p50_npv_a: float
    p50_npv_b: float
    pricing_structure: str
    n_paths: int
