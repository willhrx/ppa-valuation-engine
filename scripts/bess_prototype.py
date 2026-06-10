"""
bess_prototype.py — throwaway exploration: does a co-located battery help a
solar PPA, particularly the baseload structure?

Reads the quant core (src/ppa_engine) strictly read-only — no engine changes.

Framing
-------
In this engine the producer's total economics under a baseload PPA are

    NPV_total = disc( delivered(t) x spot(t) )            # physical sales
              + disc( flat x (strike - spot(t)) )         # the CfD swap

The swap leg is independent of the battery; a co-located BESS changes only
`delivered(t)` by moving PV energy from cheap/surplus hours into expensive/
shortfall hours. So:

    BESS value  = disc(delivered_bess x spot) - disc(production x spot)
    BESS risk   = std / P10 of NPV_total across weather+price paths,
                  with vs without the battery.

Dispatch heuristic (v0, perfect day-ahead foresight)
----------------------------------------------------
Greedy per calendar day, SOC carried across days:
  - charge from PV *surplus above the flat obligation* in the cheapest
    surplus hours (co-located, no grid charging),
  - discharge into the most expensive hours of the day (these are usually
    shortfall hours given solar's midday peak vs evening price peak),
  - respect power, energy, round-trip efficiency and a daily cycle cap.

Run:  python scripts/bess_prototype.py
"""

from __future__ import annotations

import copy
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ppa_engine.config import DEFAULT_CONFIG, PPAConfig  # noqa: E402
from ppa_engine.data.market_prices import generate_market_prices  # noqa: E402
from ppa_engine.data.solar_production import generate_solar_production  # noqa: E402


@dataclass
class BatteryConfig:
    power_mw: float
    energy_mwh: float
    round_trip_efficiency: float = 0.88
    max_cycles_per_day: float = 1.5

    @property
    def label(self) -> str:
        return f"{self.power_mw:g}MW/{self.energy_mwh:g}MWh"


def _discount_factors(index: pd.DatetimeIndex, rate: float) -> np.ndarray:
    hours = (index - index[0]).total_seconds() / 3600.0
    return np.asarray((1 + rate) ** (-hours / 8760))


def dispatch(
    production: np.ndarray,
    prices: np.ndarray,
    flat: float,
    bat: BatteryConfig,
    hours_per_day: int = 24,
) -> np.ndarray:
    """Greedy day-ahead dispatch. Returns delivered(t) = production - charge + discharge."""
    n = len(production)
    delivered = production.copy()
    eff = np.sqrt(bat.round_trip_efficiency)  # split losses charge/discharge
    soc = 0.0
    n_days = n // hours_per_day

    for d in range(n_days):
        lo = d * hours_per_day
        day_prod = production[lo : lo + hours_per_day]
        day_price = prices[lo : lo + hours_per_day]
        surplus = np.maximum(day_prod - flat, 0.0)

        throughput_cap = bat.max_cycles_per_day * bat.energy_mwh
        charged = 0.0
        discharged = 0.0

        # Charge from surplus in the cheapest surplus hours.
        for h in np.argsort(day_price):
            if surplus[h] <= 0:
                continue
            room = bat.energy_mwh - soc
            take = min(surplus[h], bat.power_mw, room / eff, throughput_cap - charged)
            if take <= 1e-9:
                continue
            soc += take * eff
            charged += take
            delivered[lo + h] -= take

        # Discharge into the most expensive hours.
        for h in np.argsort(day_price)[::-1]:
            if soc <= 1e-9 or discharged >= throughput_cap:
                break
            give = min(bat.power_mw, soc * eff, throughput_cap - discharged)
            if give <= 1e-9:
                continue
            soc -= give / eff
            discharged += give
            delivered[lo + h] += give

    return delivered


def evaluate(
    solar: pd.Series,
    prices: pd.Series,
    bat: BatteryConfig | None,
    discount_rate: float,
) -> dict:
    prod = solar.to_numpy()
    px = prices.to_numpy()
    flat = float(prod.mean())
    disc = _discount_factors(solar.index, discount_rate)

    delivered = prod if bat is None else dispatch(prod, px, flat, bat)
    spot_npv = float((delivered * px * disc).sum())

    shortfall = np.maximum(flat - prod, 0.0)
    shift = delivered - prod  # +discharge / -charge
    covered = float(np.minimum(np.maximum(shift, 0.0), shortfall).sum())
    total_short = float(shortfall.sum())

    capture = float((delivered * px).sum() / max(delivered.sum(), 1e-9) / px.mean())

    return {
        "spot_npv": spot_npv,
        "shortfall_coverage": covered / total_short if total_short else 0.0,
        "capture_rate": capture,
        "throughput_mwh": float(np.maximum(shift, 0.0).sum()),
    }


def main() -> None:
    config = DEFAULT_CONFIG
    rate = config.deal.discount_rate

    print("Generating central scenario...")
    solar = generate_solar_production(config)
    prices = generate_market_prices(config)
    base = evaluate(solar, prices, None, rate)
    years = (solar.index[-1] - solar.index[0]).days / 365.25

    print(
        f"\nBase (no BESS): spot NPV {base['spot_npv'] / 1e6:8.2f} M€   "
        f"capture {base['capture_rate']:.3f}\n"
    )

    header = (
        f"{'battery':>14} {'dNPV (M€)':>10} {'capture':>8} {'short cov.':>10} "
        f"{'cycles/day':>10} {'breakeven capex':>16}"
    )
    print(header)
    print("-" * len(header))

    best: tuple[float, BatteryConfig] | None = None
    for power in (5.0, 10.0, 20.0):
        for duration in (1.0, 2.0, 4.0):
            bat = BatteryConfig(power_mw=power, energy_mwh=power * duration)
            r = evaluate(solar, prices, bat, rate)
            d_npv = r["spot_npv"] - base["spot_npv"]
            cyc = r["throughput_mwh"] / bat.energy_mwh / (years * 365.25)
            # Capex the uplift would pay back over the horizon (no O&M, no
            # degradation, central scenario only — an upper bound).
            breakeven = d_npv / (bat.energy_mwh * 1000.0)
            print(
                f"{bat.label:>14} {d_npv / 1e6:10.2f} {r['capture_rate']:8.3f} "
                f"{r['shortfall_coverage']:10.1%} {cyc:10.2f} "
                f"{breakeven:12.0f} €/kWh"
            )
            if best is None or d_npv > best[0]:
                best = (d_npv, bat)

    # ------------------------------------------------------------------
    # Risk view: small joint Monte Carlo (weather + price reseeded) for the
    # best battery — does the BESS narrow the baseload producer's NPV
    # distribution, not just raise its mean?
    # ------------------------------------------------------------------
    assert best is not None
    bat = best[1]
    n_paths = 15
    base_strike = 65.0
    print(f"\nRisk check on {bat.label}: {n_paths} joint paths (weather+price reseeded)")

    totals_no, totals_with = [], []
    t0 = time.time()
    for i in range(n_paths):
        cfg: PPAConfig = copy.deepcopy(config)
        cfg.solar.seed = 7_000 + i * 101
        cfg.market.seed = 8_000 + i * 101
        cfg.market.wind_seed = 9_000 + i * 101
        s = generate_solar_production(cfg)
        p = generate_market_prices(cfg)
        prod, px = s.to_numpy(), p.to_numpy()
        flat = float(prod.mean())
        disc = _discount_factors(s.index, rate)
        swap = float((flat * (base_strike - px) * disc).sum())
        totals_no.append(float((prod * px * disc).sum()) + swap)
        delivered = dispatch(prod, px, flat, bat)
        totals_with.append(float((delivered * px * disc).sum()) + swap)
    elapsed = time.time() - t0

    a, b = np.array(totals_no), np.array(totals_with)
    print(
        f"  no BESS : mean {a.mean() / 1e6:7.2f} M€  std {a.std(ddof=1) / 1e6:6.2f}  "
        f"P10 {np.percentile(a, 10) / 1e6:7.2f}"
    )
    print(
        f"  with    : mean {b.mean() / 1e6:7.2f} M€  std {b.std(ddof=1) / 1e6:6.2f}  "
        f"P10 {np.percentile(b, 10) / 1e6:7.2f}   ({elapsed:.0f}s)"
    )


if __name__ == "__main__":
    main()
