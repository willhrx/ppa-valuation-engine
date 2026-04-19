"""
run_monte_carlo.py — Standalone Monte Carlo driver for the PPA valuation engine.

The Phase 3 modules under ``ppa_engine.risk`` are stubbed, so this script
implements a lean MC orchestrator that reuses the existing Phase 2 building
blocks (data generators, supply/pricing structures, valuation engine) without
modifying the library.

Design
------
Deterministic inputs are computed once and cached:
  * Clear-sky POA irradiance (pvlib call is expensive)
  * Deterministic price layers 1–4 (level, seasonal, intra-day, cannibalisation)
  * Consumer load (treated as deterministic for risk decomposition)

For each MC path only the stochastic layers are redrawn:
  * Solar cloud factor   — AR(1) in logit space, reseeded per path
  * Price AR(1) noise    — reseeded per path

Three ensembles are run to support variance decomposition:
  * ``volume`` mode — redraw solar only, hold prices at central scenario
  * ``price``  mode — redraw price noise only, hold solar at central scenario
  * ``joint``  mode — redraw both independently

Each ensemble runs N_PATHS paths across all 12 (supply × pricing) combinations.

Outputs (written to reports/)
-----------------------------
  * monte_carlo_paths.csv     — long form (mode, path, supply, pricing, NPVs)
  * monte_carlo_summary.json  — central scenario + per-combination risk stats
"""

from __future__ import annotations

import json
import time
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import expit, logit

from ppa_engine.config import PPAConfig
from ppa_engine.data.consumer_load import generate_consumer_load
from ppa_engine.data.market_prices import (
    _build_timestamps,
    _layer1_level,
    _layer2_seasonal,
    _layer3_intraday,
    _layer4_cannibalisation,
)
from ppa_engine.data.solar_production import _clearsky_poa
from ppa_engine.valuation.engine import value_all_combinations

# --- Run configuration --------------------------------------------------------
N_PATHS = 150                # paths per ensemble (3 ensembles → 450 total)
BASE_STRIKE = 65.0           # strike price for fixed/escalated pricing
REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# --- Fast stochastic helpers --------------------------------------------------
def _ar1_path(n: int, phi: float, sigma_stationary: float, seed: int) -> np.ndarray:
    """Stationary AR(1) with stationary std = sigma_stationary."""
    rng = np.random.default_rng(seed)
    sigma_innov = sigma_stationary * np.sqrt(1.0 - phi * phi)
    eps = rng.standard_normal(n)
    out = np.empty(n)
    out[0] = sigma_stationary * eps[0]
    for t in range(1, n):
        out[t] = phi * out[t - 1] + sigma_innov * eps[t]
    return out


def _ar1_path_standardised(n: int, phi: float, seed: int) -> np.ndarray:
    """Stationary AR(1) with marginal std = 1 (for cloud factor)."""
    rng = np.random.default_rng(seed)
    sigma_innov = np.sqrt(1.0 - phi * phi)
    eps = rng.standard_normal(n)
    out = np.empty(n)
    out[0] = eps[0]
    for t in range(1, n):
        out[t] = phi * out[t - 1] + sigma_innov * eps[t]
    return out


def solar_path(times, poa_clearsky, degradation, cfg, seed) -> pd.Series:
    sc = cfg.solar
    z = _ar1_path_standardised(len(times), sc.cloud_factor_phi, seed)
    monthly_logit = np.array([logit(m) for m in sc.monthly_cloud_means])
    hour_logit_mean = monthly_logit[np.array([t.month - 1 for t in times])]
    cloud = expit(hour_logit_mean + sc.cloud_factor_logit_scale * z)
    out = sc.capacity_mw * sc.performance_ratio * (poa_clearsky * cloud / 1000.0) * degradation
    return pd.Series(out, index=times, name="solar_production_mwh")


def price_path(times, deterministic_layers, cfg, seed) -> pd.Series:
    mc = cfg.market
    noise = _ar1_path(len(times), mc.ar1_phi, mc.ar1_sigma, seed)
    return pd.Series(deterministic_layers + noise, index=times,
                     name="market_price_eur_mwh")


# --- Run a full ensemble ------------------------------------------------------
def run_ensemble(
    mode: str,
    times: pd.DatetimeIndex,
    poa_clearsky: np.ndarray,
    degradation: np.ndarray,
    deterministic_price: np.ndarray,
    load: pd.Series,
    base_cfg: PPAConfig,
    n_paths: int,
    central_solar: pd.Series,
    central_prices: pd.Series,
) -> pd.DataFrame:
    """Run N_PATHS paths for the given decomposition mode.

    ``mode`` in {'volume', 'price', 'joint'}.
    In 'volume' mode only the solar seed is perturbed.
    In 'price'  mode only the market noise seed is perturbed.
    In 'joint'  mode both solar and market seeds are perturbed independently.
    """
    print(f"\n[{mode}] running {n_paths} paths...")
    rng = np.random.default_rng({"volume": 101, "price": 202, "joint": 303}[mode])
    # Draw independent integer seeds for each path
    solar_seeds = rng.integers(1, 10_000_000, size=n_paths)
    price_seeds = rng.integers(1, 10_000_000, size=n_paths)

    rows: list[dict] = []
    t0 = time.time()
    for i in range(n_paths):
        if mode == "volume":
            solar = solar_path(times, poa_clearsky, degradation, base_cfg,
                               int(solar_seeds[i]))
            prices = central_prices
        elif mode == "price":
            solar = central_solar
            prices = price_path(times, deterministic_price, base_cfg,
                                int(price_seeds[i]))
        else:  # joint
            solar = solar_path(times, poa_clearsky, degradation, base_cfg,
                               int(solar_seeds[i]))
            prices = price_path(times, deterministic_price, base_cfg,
                                int(price_seeds[i]))

        combo = value_all_combinations(solar, load, prices, base_cfg,
                                       base_strike=BASE_STRIKE)
        combo["path"] = i
        combo["mode"] = mode
        rows.append(combo)

        if (i + 1) % 25 == 0 or i == n_paths - 1:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (n_paths - i - 1) / rate
            print(f"  path {i + 1:>4}/{n_paths}  "
                  f"elapsed={elapsed:6.1f}s  rate={rate:4.1f} p/s  eta={eta:5.1f}s")

    return pd.concat(rows, ignore_index=True)


# --- Risk metrics -------------------------------------------------------------
def summarise(df_paths: pd.DataFrame, central: pd.DataFrame) -> dict:
    """Compute per-combination risk metrics and variance decomposition."""
    combos = (df_paths[["supply_structure", "pricing_structure"]]
              .drop_duplicates().values.tolist())

    per_combo: list[dict] = []
    for supply, pricing in combos:
        entry: dict = {"supply_structure": supply, "pricing_structure": pricing}
        # central scenario NPV
        c = central[(central.supply_structure == supply)
                    & (central.pricing_structure == pricing)].iloc[0]
        entry["central_producer_npv"] = float(c.producer_npv)
        entry["central_capture_rate"] = float(c.capture_rate)
        entry["central_volume_mwh"] = float(c.total_volume_mwh)
        entry["central_avg_strike"] = float(c.average_strike_eur_mwh)
        entry["central_volume_value"] = float(c.volume_value)
        entry["central_profile_value"] = float(c.profile_value)

        # per-mode stats
        for mode in ("joint", "price", "volume"):
            sub = df_paths[(df_paths.supply_structure == supply)
                           & (df_paths.pricing_structure == pricing)
                           & (df_paths["mode"] == mode)]["producer_npv"]
            if len(sub) == 0:
                continue
            arr = sub.to_numpy()
            p10, p50, p90 = np.percentile(arr, [10, 50, 90])
            var95 = float(np.percentile(arr, 5))                 # 5th pct loss
            es95 = float(arr[arr <= var95].mean()) if (arr <= var95).any() else var95
            entry[f"{mode}_mean"] = float(arr.mean())
            entry[f"{mode}_std"] = float(arr.std(ddof=1))
            entry[f"{mode}_p10"] = float(p10)
            entry[f"{mode}_p50"] = float(p50)
            entry[f"{mode}_p90"] = float(p90)
            entry[f"{mode}_var95"] = var95
            entry[f"{mode}_es95"] = es95
            entry[f"{mode}_prob_negative"] = float((arr < 0).mean())

        # variance decomposition (variance shares of joint)
        v_j = entry.get("joint_std", 0.0) ** 2
        v_p = entry.get("price_std", 0.0) ** 2
        v_v = entry.get("volume_std", 0.0) ** 2
        if v_j > 0:
            share_price = v_p / v_j
            share_volume = v_v / v_j
            share_interaction = 1.0 - share_price - share_volume
        else:
            share_price = share_volume = share_interaction = 0.0
        entry["var_share_price"] = float(share_price)
        entry["var_share_volume"] = float(share_volume)
        entry["var_share_interaction"] = float(share_interaction)

        per_combo.append(entry)

    return {"combinations": per_combo}


# --- Main ---------------------------------------------------------------------
def main() -> None:
    print("=" * 70)
    print("PPA Monte Carlo Simulation")
    print("=" * 70)

    cfg = PPAConfig()
    times = _build_timestamps(cfg)
    print(f"Horizon: {times[0]} → {times[-1]}  ({len(times):,} hours)")

    # ---- deterministic pieces cached once -----------------------------------
    print("\n[1/4] Caching deterministic inputs...")
    t0 = time.time()
    poa_clearsky = _clearsky_poa(times, cfg)
    print(f"       pvlib clear-sky POA: {time.time() - t0:.1f}s")

    start_year = pd.Timestamp(cfg.deal.start_date).year
    year_offset = np.array([t.year - start_year for t in times])
    degradation = 1.0 - cfg.solar.degradation_rate * year_offset

    deterministic_price = (
        _layer1_level(times, cfg)
        + _layer2_seasonal(times, cfg)
        + _layer3_intraday(times, cfg)
        + _layer4_cannibalisation(times, cfg)
    )
    load = generate_consumer_load(cfg)

    # ---- central scenario ---------------------------------------------------
    print("\n[2/4] Central scenario (base seeds)...")
    central_solar = solar_path(times, poa_clearsky, degradation, cfg,
                               cfg.solar.seed)
    central_prices = price_path(times, deterministic_price, cfg,
                                cfg.market.seed)
    central_df = value_all_combinations(central_solar, load, central_prices, cfg,
                                        base_strike=BASE_STRIKE)
    print(central_df[["supply_structure", "pricing_structure",
                      "producer_npv", "average_strike_eur_mwh", "capture_rate"]]
          .to_string(index=False))

    # ---- three ensembles ----------------------------------------------------
    print(f"\n[3/4] Running MC ensembles ({N_PATHS} paths × 3 modes × 12 combos)...")
    frames = []
    for mode in ("joint", "price", "volume"):
        frames.append(run_ensemble(
            mode, times, poa_clearsky, degradation, deterministic_price,
            load, cfg, N_PATHS, central_solar, central_prices,
        ))
    paths_df = pd.concat(frames, ignore_index=True)
    paths_df["label"] = (paths_df["supply_structure"] + " / "
                         + paths_df["pricing_structure"])

    # ---- persist ------------------------------------------------------------
    print("\n[4/4] Writing outputs...")
    paths_path = REPORTS_DIR / "monte_carlo_paths.csv"
    paths_df.to_csv(paths_path, index=False)
    print(f"       paths   → {paths_path}  ({len(paths_df):,} rows)")

    summary = summarise(paths_df, central_df)
    summary["meta"] = {
        "n_paths_per_mode": N_PATHS,
        "modes": ["joint", "price", "volume"],
        "base_strike": BASE_STRIKE,
        "horizon_start": str(times[0]),
        "horizon_end": str(times[-1]),
        "n_hours": int(len(times)),
        "discount_rate": cfg.deal.discount_rate,
        "capacity_mw": cfg.solar.capacity_mw,
        "annual_consumption_gwh": cfg.load.annual_consumption_gwh,
        "location": {"lat": cfg.location.lat, "lon": cfg.location.lon,
                     "tz": cfg.location.tz},
    }
    # Also embed a compact per-path NPV table (joint mode only) to enable
    # histograms in the dashboard without shipping the full parquet.
    joint_paths = paths_df[paths_df["mode"] == "joint"]
    joint_compact = (
        joint_paths.groupby(["supply_structure", "pricing_structure"])["producer_npv"]
        .apply(lambda s: s.tolist()).reset_index()
        .rename(columns={"producer_npv": "paths"})
    )
    summary["joint_paths"] = joint_compact.to_dict(orient="records")

    summary_path = REPORTS_DIR / "monte_carlo_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, default=float)
    print(f"       summary → {summary_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
