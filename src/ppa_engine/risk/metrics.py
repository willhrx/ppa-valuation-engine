"""
metrics.py — Risk metrics for the Monte Carlo NPV distribution (Phase 3).

Metrics implemented:
  - VaR(α)   : Value-at-Risk at confidence level α (e.g., 95 %)
                The NPV that is not exceeded in the worst (1-α) % of paths.
  - ES(α)    : Expected Shortfall (CVaR) — mean NPV in the worst (1-α) % of paths.
                More coherent than VaR; preferred for capital allocation.
  - P10/P50/P90 NPV: percentile NPVs for deal-sheet reporting.
  - Risk decomposition: variance attribution across price risk, volume risk,
    and their interaction (the correlation term).

All metrics are expressed from the *producer's* perspective. A negative NPV
tail means the PPA locked in a price below what the spot market would have paid.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class PathDistribution:
    """Distribution statistics for a single NPV sample (producer perspective)."""

    mean: float
    std: float
    p10: float
    p50: float
    p90: float
    var_95: float        # 5th percentile — loss not exceeded in 95 % of paths
    es_95: float         # mean of paths at or below VaR — always <= var_95
    prob_negative: float # fraction of paths with NPV < 0


@dataclass
class VarianceDecomposition:
    """
    Variance attribution from the three-ensemble method.

    total_variance : Var(joint_npvs)
    price_share    : Var(price_only) / Var(joint)
    volume_share   : Var(volume_only) / Var(joint)
    interaction_share : 1 - price_share - volume_share

    The interaction term can be negative (diversification: price and volume
    risks partially offset each other, e.g., when high solar suppresses prices
    and thus reduces producer revenue — a self-reinforcing effect).
    """

    total_variance: float
    price_share: float
    volume_share: float
    interaction_share: float


@dataclass
class ComboRiskSummary:
    """Full risk summary for one supply × pricing combination."""

    supply_structure: str
    pricing_structure: str
    central_producer_npv: float
    central_capture_rate: float
    joint: PathDistribution
    price_only: PathDistribution
    volume_only: PathDistribution
    variance_decomp: VarianceDecomposition


@dataclass
class RiskSummary:
    """Aggregated risk summary for all 12 supply × pricing combinations."""

    combinations: list[ComboRiskSummary]
    n_paths: int
    base_strike: float


# ---------------------------------------------------------------------------
# Core metric functions
# ---------------------------------------------------------------------------


def value_at_risk(npv_array: np.ndarray, confidence: float = 0.95) -> float:
    """
    Value-at-Risk at the given confidence level.

    VaR(95%) = 5th percentile of the NPV distribution. From the producer's
    perspective: the NPV not exceeded in 95 % of paths. More negative = more
    downside risk.

    Parameters
    ----------
    npv_array : np.ndarray
        1D array of NPV realisations (producer perspective).
    confidence : float
        e.g. 0.95 for 95 % confidence.

    Returns
    -------
    float
        VaR value. Negative if the distribution has significant downside.
    """
    return float(np.percentile(npv_array, 100.0 * (1.0 - confidence)))


def expected_shortfall(npv_array: np.ndarray, confidence: float = 0.95) -> float:
    """
    Expected Shortfall (CVaR) at the given confidence level.

    ES(95%) = mean NPV of the worst 5 % of paths (those at or below VaR).
    Always <= VaR by construction. More coherent than VaR for risk capital.

    Parameters
    ----------
    npv_array : np.ndarray
    confidence : float

    Returns
    -------
    float
        ES value. Always <= var_95 for the same confidence level.
    """
    var = value_at_risk(npv_array, confidence)
    tail = npv_array[npv_array <= var]
    return float(tail.mean()) if len(tail) > 0 else var


def _path_distribution(npv_array: np.ndarray) -> PathDistribution:
    """Compute PathDistribution from a 1D NPV array."""
    p10, p50, p90 = np.percentile(npv_array, [10.0, 50.0, 90.0])
    return PathDistribution(
        mean=float(npv_array.mean()),
        std=float(npv_array.std(ddof=1)),
        p10=float(p10),
        p50=float(p50),
        p90=float(p90),
        var_95=value_at_risk(npv_array),
        es_95=expected_shortfall(npv_array),
        prob_negative=float((npv_array < 0).mean()),
    )


def decompose_risk(
    joint_npvs: np.ndarray,
    price_npvs: np.ndarray,
    volume_npvs: np.ndarray,
) -> VarianceDecomposition:
    """
    Attribute NPV variance to price risk, volume risk, and their interaction.

    Method: three-ensemble variance decomposition.
        V_joint   = Var(joint_npvs)
        V_price   = Var(price_only_npvs)
        V_volume  = Var(volume_only_npvs)
        share_price       = V_price  / V_joint
        share_volume      = V_volume / V_joint
        share_interaction = 1 - share_price - share_volume

    The interaction term is non-zero because joint variance is not simply
    V_price + V_volume. It includes the covariance between price and volume
    movements (cannibalisation: high solar → lower prices → compounding effect
    on pay-as-produced producer revenue).

    Parameters
    ----------
    joint_npvs, price_npvs, volume_npvs : np.ndarray
        1D arrays from the three respective ensembles. All same length.

    Returns
    -------
    VarianceDecomposition
    """
    v_joint = float(np.var(joint_npvs, ddof=1))
    v_price = float(np.var(price_npvs, ddof=1))
    v_volume = float(np.var(volume_npvs, ddof=1))

    if v_joint > 0:
        share_price = v_price / v_joint
        share_volume = v_volume / v_joint
        share_interaction = 1.0 - share_price - share_volume
    else:
        share_price = share_volume = share_interaction = 0.0

    return VarianceDecomposition(
        total_variance=v_joint,
        price_share=float(share_price),
        volume_share=float(share_volume),
        interaction_share=float(share_interaction),
    )


# ---------------------------------------------------------------------------
# Aggregation functions
# ---------------------------------------------------------------------------


def summarise_risk(mc_result: object) -> RiskSummary:
    """
    Compute full risk summary from a MonteCarloResult.

    Iterates over all 12 supply × pricing combinations, extracting
    joint/price/volume NPV arrays and computing full statistics for each.

    Parameters
    ----------
    mc_result : MonteCarloResult
        Output of run_monte_carlo(). Must contain paths_df and central_df.

    Returns
    -------
    RiskSummary
    """
    paths_df: pd.DataFrame = mc_result.paths_df  # type: ignore[attr-defined]
    central_df: pd.DataFrame = mc_result.central_df  # type: ignore[attr-defined]

    combos = (
        paths_df[["supply_structure", "pricing_structure"]]
        .drop_duplicates()
        .values.tolist()
    )

    combo_summaries = []
    for supply, pricing in combos:
        mask_base = (
            (paths_df.supply_structure == supply)
            & (paths_df.pricing_structure == pricing)
        )
        joint_arr = paths_df[mask_base & (paths_df["mode"] == "joint")][
            "producer_npv"
        ].to_numpy()
        price_arr = paths_df[mask_base & (paths_df["mode"] == "price")][
            "producer_npv"
        ].to_numpy()
        vol_arr = paths_df[mask_base & (paths_df["mode"] == "volume")][
            "producer_npv"
        ].to_numpy()

        central_row = central_df[
            (central_df.supply_structure == supply)
            & (central_df.pricing_structure == pricing)
        ].iloc[0]

        combo_summaries.append(
            ComboRiskSummary(
                supply_structure=supply,
                pricing_structure=pricing,
                central_producer_npv=float(central_row.producer_npv),
                central_capture_rate=float(central_row.capture_rate),
                joint=_path_distribution(joint_arr),
                price_only=_path_distribution(price_arr),
                volume_only=_path_distribution(vol_arr),
                variance_decomp=decompose_risk(joint_arr, price_arr, vol_arr),
            )
        )

    return RiskSummary(
        combinations=combo_summaries,
        n_paths=mc_result.n_paths,  # type: ignore[attr-defined]
        base_strike=mc_result.base_strike,  # type: ignore[attr-defined]
    )


def risk_by_supply_structure(risk_summary: RiskSummary) -> pd.DataFrame:
    """
    Aggregate risk metrics grouped by supply structure.

    Returns a DataFrame indexed by supply_structure showing mean metrics
    across all pricing structures. Confirms the structural pattern:
    pay-as-produced has higher volume_share; baseload has higher price_share.
    """
    supply_groups: dict[str, list[ComboRiskSummary]] = {}
    for c in risk_summary.combinations:
        supply_groups.setdefault(c.supply_structure, []).append(c)

    rows = []
    for supply, combos in supply_groups.items():
        rows.append(
            {
                "supply_structure": supply,
                "mean_p50_npv": float(np.mean([c.joint.p50 for c in combos])),
                "mean_var_95": float(np.mean([c.joint.var_95 for c in combos])),
                "mean_es_95": float(np.mean([c.joint.es_95 for c in combos])),
                "mean_price_share": float(
                    np.mean([c.variance_decomp.price_share for c in combos])
                ),
                "mean_volume_share": float(
                    np.mean([c.variance_decomp.volume_share for c in combos])
                ),
                "mean_interaction_share": float(
                    np.mean([c.variance_decomp.interaction_share for c in combos])
                ),
            }
        )

    return pd.DataFrame(rows).set_index("supply_structure")
