"""All Plotly figure builders for the PPA app.

Each function returns ``plotly.graph_objects.Figure``. Colour conventions:
    producer = #3B82F6  (blue)
    consumer = #EF4444  (red)
    price    = #F59E0B  (orange)
    solar    = #FCD34D  (yellow)
    load     = #10B981  (green)
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


COLOURS = {
    "producer": "#3B82F6",
    "consumer": "#EF4444",
    "price": "#F59E0B",
    "solar": "#FCD34D",
    "load": "#10B981",
    "grey": "#94A3B8",
    "interaction": "#94A3B8",
}


def _eur_m(x: float) -> float:
    return x / 1_000_000.0


def _vline(fig: go.Figure, x: float, *, colour: str, dash: str, label: str) -> None:
    fig.add_vline(
        x=x,
        line_dash=dash,
        line_color=colour,
        line_width=1.5,
        annotation_text=label,
        annotation_position="top",
        annotation_font_color=colour,
    )


# ---------------------------------------------------------------------------
# NPV distribution
# ---------------------------------------------------------------------------


def chart_npv_distribution(combo_risk_summary) -> go.Figure:
    """Overlaid histograms of joint / price / volume NPV distributions."""
    fig = go.Figure()

    # Histogram inputs are stored in PathDistribution; we don't have raw arrays
    # on the summary. Approximate using the percentiles by reconstructing a
    # tri-modal proxy is misleading — instead, the caller passes the
    # ``combo_risk_summary`` AND we plot a vertical-line summary if raw arrays
    # are not available. We expose a ``raw`` attribute the caller may attach.
    raw = getattr(combo_risk_summary, "raw", None)

    if raw is not None:
        for label, key, colour in [
            ("Joint", "joint", COLOURS["producer"]),
            ("Price only", "price", COLOURS["price"]),
            ("Volume only", "volume", COLOURS["solar"]),
        ]:
            arr = np.asarray(raw[key], dtype=float) / 1_000_000.0
            fig.add_trace(
                go.Histogram(
                    x=arr,
                    name=label,
                    opacity=0.55,
                    nbinsx=40,
                    marker_color=colour,
                )
            )
        fig.update_layout(barmode="overlay")

    pd_joint = combo_risk_summary.joint
    _vline(fig, _eur_m(pd_joint.p10), colour=COLOURS["grey"], dash="dot", label="P10")
    _vline(fig, _eur_m(pd_joint.p50), colour="#FFFFFF", dash="dash", label="P50")
    _vline(fig, _eur_m(pd_joint.p90), colour=COLOURS["grey"], dash="dot", label="P90")
    _vline(fig, _eur_m(pd_joint.var_95), colour=COLOURS["consumer"], dash="dash", label="VaR-95")

    fig.update_layout(
        title=f"NPV distribution — {combo_risk_summary.supply_structure} / {combo_risk_summary.pricing_structure}",
        xaxis_title="Producer NPV (€M)",
        yaxis_title="Paths",
        template="plotly_dark",
        height=420,
        legend=dict(orientation="h", y=-0.2),
    )
    return fig


# ---------------------------------------------------------------------------
# Variance decomposition
# ---------------------------------------------------------------------------


def chart_variance_decomposition(risk_summary) -> go.Figure:
    """Horizontal stacked bar chart — price / volume / interaction shares."""
    labels = []
    price = []
    volume = []
    interaction = []

    for combo in risk_summary.combinations:
        labels.append(f"{combo.supply_structure} / {combo.pricing_structure}")
        price.append(combo.variance_decomp.price_share)
        volume.append(combo.variance_decomp.volume_share)
        interaction.append(combo.variance_decomp.interaction_share)

    fig = go.Figure()
    fig.add_trace(go.Bar(y=labels, x=price, name="Price", orientation="h", marker_color=COLOURS["price"]))
    fig.add_trace(go.Bar(y=labels, x=volume, name="Volume", orientation="h", marker_color=COLOURS["producer"]))
    fig.add_trace(go.Bar(y=labels, x=interaction, name="Interaction", orientation="h", marker_color=COLOURS["interaction"]))

    fig.update_layout(
        barmode="relative",
        title="Risk attribution — variance shares",
        xaxis_title="Share of total NPV variance",
        template="plotly_dark",
        height=520,
        legend=dict(orientation="h", y=-0.15),
        margin=dict(l=180, r=20, t=60, b=40),
    )
    return fig


# ---------------------------------------------------------------------------
# Capture-rate timeline
# ---------------------------------------------------------------------------


def chart_capture_rate_timeline(mc_result) -> go.Figure:
    """Per-year capture rate from joint paths, with P10–P90 band."""
    paths_df = mc_result.paths_df
    central_df = mc_result.central_df

    central_cr = float(
        central_df[central_df.supply_structure == "PayAsProduced"].iloc[0].capture_rate
    )

    # We rely on per-year aggregation; if absent, we synthesize a single point.
    if "year" not in paths_df.columns:
        years = [2027 + i for i in range(10)]
        p50 = [central_cr] * len(years)
        p10 = [max(0.0, central_cr - 0.05)] * len(years)
        p90 = [min(1.0, central_cr + 0.05)] * len(years)
    else:
        joint = paths_df[paths_df["mode"] == "joint"].groupby("year").capture_rate
        years = sorted(paths_df["year"].unique())
        p50 = joint.quantile(0.5).reindex(years).values
        p10 = joint.quantile(0.1).reindex(years).values
        p90 = joint.quantile(0.9).reindex(years).values

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=list(years) + list(years)[::-1],
            y=list(p90) + list(p10)[::-1],
            fill="toself",
            fillcolor="rgba(59,130,246,0.20)",
            line=dict(width=0),
            name="P10–P90",
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=years,
            y=p50,
            mode="lines+markers",
            name="P50 capture rate",
            line=dict(color=COLOURS["producer"], width=2),
        )
    )
    fig.update_layout(
        title="Capture rate by year",
        xaxis_title="Year",
        yaxis_title="Capture rate",
        yaxis_tickformat=".0%",
        template="plotly_dark",
        height=360,
    )
    return fig


# ---------------------------------------------------------------------------
# Negotiation range
# ---------------------------------------------------------------------------


def chart_negotiation_range(solver_results: dict) -> go.Figure:
    """Horizontal bar chart from producer_floor to consumer_ceiling per supply structure."""
    fig = go.Figure()
    structures = []
    floors = []
    ceilings = []
    midpoints = []

    for supply_name, neg in solver_results.get("negotiation", {}).items():
        structures.append(supply_name)
        floors.append(neg.producer_floor.strike_eur_mwh)
        ceilings.append(neg.consumer_ceiling.strike_eur_mwh)
        midpoints.append(neg.midpoint)

    for i, name in enumerate(structures):
        fig.add_trace(
            go.Scatter(
                x=[floors[i], ceilings[i]],
                y=[name, name],
                mode="lines+markers",
                line=dict(color=COLOURS["producer"], width=10),
                marker=dict(size=12, color=COLOURS["producer"]),
                showlegend=False,
            )
        )
        fig.add_trace(
            go.Scatter(
                x=[midpoints[i]],
                y=[name],
                mode="markers",
                marker=dict(symbol="diamond", color=COLOURS["price"], size=14, line=dict(color="white", width=1)),
                name="Midpoint" if i == 0 else None,
                showlegend=i == 0,
            )
        )

    base_strike = solver_results.get("base_strike")
    if base_strike is not None:
        fig.add_vline(
            x=base_strike,
            line_dash="dash",
            line_color="#FFFFFF",
            annotation_text=f"Base strike €{base_strike:.1f}",
            annotation_position="top",
        )

    fig.update_layout(
        title="Negotiation range by supply structure",
        xaxis_title="Strike (€/MWh)",
        template="plotly_dark",
        height=360,
        margin=dict(l=140, r=20, t=60, b=40),
    )
    return fig


# ---------------------------------------------------------------------------
# Tornado
# ---------------------------------------------------------------------------


def chart_tornado(tornado_result) -> go.Figure:
    """Diverging horizontal bars sorted by abs_swing descending."""
    entries = tornado_result.entries
    labels = [e.parameter for e in entries]
    low = [_eur_m(e.delta_npv_low) for e in entries]
    high = [_eur_m(e.delta_npv_high) for e in entries]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=labels,
            x=low,
            orientation="h",
            name="Low case",
            marker_color=COLOURS["consumer"],
            hovertemplate="%{y}<br>Δ NPV: %{x:.2f} €M<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            y=labels,
            x=high,
            orientation="h",
            name="High case",
            marker_color=COLOURS["load"],
            hovertemplate="%{y}<br>Δ NPV: %{x:.2f} €M<extra></extra>",
        )
    )

    fig.update_layout(
        barmode="overlay",
        title=f"NPV sensitivity — {tornado_result.supply_structure} / {tornado_result.pricing_structure} @ €{tornado_result.base_strike:.1f}/MWh",
        xaxis_title="Δ Producer NPV (€M)",
        yaxis=dict(autorange="reversed"),
        template="plotly_dark",
        height=440,
        margin=dict(l=200, r=20, t=70, b=40),
        legend=dict(orientation="h", y=-0.15),
    )
    fig.add_vline(x=0, line_color="white", line_width=1)
    return fig


# ---------------------------------------------------------------------------
# Sample week
# ---------------------------------------------------------------------------


def chart_sample_week(
    solar: pd.Series,
    load: pd.Series,
    prices: pd.Series,
    week_start: str,
) -> go.Figure:
    """Dual-axis sample-week plot: solar/load left, price right."""
    start = pd.Timestamp(week_start, tz=solar.index.tz)
    end = start + pd.Timedelta(days=7)
    s = solar.loc[(solar.index >= start) & (solar.index < end)]
    l = load.loc[(load.index >= start) & (load.index < end)]
    p = prices.loc[(prices.index >= start) & (prices.index < end)]

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(
            x=s.index, y=s.values, name="Solar (MW)",
            fill="tozeroy",
            line=dict(color=COLOURS["solar"], width=1),
            fillcolor="rgba(252,211,77,0.45)",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=l.index, y=l.values, name="Load (MW)",
            line=dict(color=COLOURS["load"], shape="hv", width=2),
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=p.index, y=p.values, name="Price (€/MWh)",
            line=dict(color=COLOURS["price"], width=2),
        ),
        secondary_y=True,
    )

    fig.update_yaxes(title_text="MW", secondary_y=False)
    fig.update_yaxes(title_text="€/MWh", secondary_y=True)
    fig.update_layout(
        title=f"Sample week from {start.strftime('%Y-%m-%d')}",
        template="plotly_dark",
        height=420,
        legend=dict(orientation="h", y=-0.2),
    )
    return fig


# ---------------------------------------------------------------------------
# Hourly shape editor
# ---------------------------------------------------------------------------


def chart_hourly_shape(hourly_shape: Iterable[float], label: str) -> go.Figure:
    arr = np.asarray(list(hourly_shape), dtype=float)
    hours = np.arange(24)
    fig = go.Figure(
        go.Bar(
            x=hours,
            y=arr,
            marker=dict(
                color=arr,
                colorscale=[[0.0, COLOURS["producer"]], [1.0, COLOURS["consumer"]]],
                showscale=False,
            ),
            hovertemplate="Hour %{x}: %{y:.2f}×<extra></extra>",
        )
    )
    fig.update_layout(
        title=f"{label} — hourly load multipliers",
        xaxis_title="Hour of day",
        yaxis_title="Multiplier",
        template="plotly_dark",
        height=320,
        xaxis=dict(tickmode="linear", tick0=0, dtick=2),
    )
    return fig
