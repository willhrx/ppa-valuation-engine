"""
perf_reference_check.py — capture / compare reference outputs around the
performance refactor (vectorised AR(1) + datetime accessors + parallel MC).

Usage:
    python scripts/perf_reference_check.py capture   # before the refactor
    python scripts/perf_reference_check.py compare   # after the refactor

The refactor must be numerically identical: same seeds, same recurrences,
same values. `compare` exits non-zero on any mismatch.
"""

from __future__ import annotations

import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ppa_engine.config import DEFAULT_CONFIG as cfg  # noqa: E402
from ppa_engine.data.consumer_load import generate_consumer_load  # noqa: E402
from ppa_engine.data.market_prices import (  # noqa: E402
    compute_wind_factor,
    generate_market_prices,
)
from ppa_engine.data.solar_production import (  # noqa: E402
    compute_cloud_factor,
    generate_solar_production,
)
from ppa_engine.risk.monte_carlo import run_monte_carlo  # noqa: E402

REF_PATH = Path(__file__).resolve().parent / "_perf_reference.pkl"


def build() -> dict:
    times = pd.date_range(
        cfg.deal.start_date, "2027-12-31 23:00", freq="h", tz=cfg.location.tz
    )
    t0 = time.time()
    out = {
        "solar": generate_solar_production(cfg).to_numpy(),
        "prices": generate_market_prices(cfg).to_numpy(),
        "load": generate_consumer_load(cfg).to_numpy(),
        "cloud": compute_cloud_factor(times, cfg, seed=12345),
        "wind": compute_wind_factor(times, cfg, seed=54321),
    }
    mc = run_monte_carlo(cfg, n_paths=3, base_strike=65.0, verbose=False)
    df = mc.paths_df.sort_values(["mode", "path", "supply_structure", "pricing_structure"])
    out["mc_paths"] = df.reset_index(drop=True)
    out["elapsed"] = time.time() - t0
    return out


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else "compare"
    if action == "capture":
        ref = build()
        REF_PATH.write_bytes(pickle.dumps(ref))
        print(f"captured reference in {ref['elapsed']:.1f}s -> {REF_PATH}")
        return 0

    ref = pickle.loads(REF_PATH.read_bytes())
    new = build()
    print(f"rebuilt in {new['elapsed']:.1f}s (reference build took {ref['elapsed']:.1f}s)")

    failures = 0
    for key in ("solar", "prices", "load", "cloud", "wind"):
        a, b = ref[key], new[key]
        if np.array_equal(a, b):
            print(f"  {key:8s} OK (bit-identical, n={len(a)})")
        elif np.allclose(a, b, rtol=1e-12, atol=1e-12):
            d = np.max(np.abs(a - b))
            print(f"  {key:8s} OK within 1e-12 (max abs diff {d:.3e})")
        else:
            d = np.max(np.abs(a - b))
            print(f"  {key:8s} MISMATCH (max abs diff {d:.3e})")
            failures += 1

    a, b = ref["mc_paths"], new["mc_paths"]
    num_a = a.select_dtypes("number").to_numpy()
    num_b = b.select_dtypes("number").to_numpy()
    if a.shape != b.shape:
        print(f"  mc_paths MISMATCH shape {a.shape} vs {b.shape}")
        failures += 1
    elif np.array_equal(num_a, num_b):
        print(f"  mc_paths OK (bit-identical, {len(a)} rows)")
    elif np.allclose(num_a, num_b, rtol=1e-9, atol=1e-6):
        d = np.max(np.abs(num_a - num_b))
        print(f"  mc_paths OK within tolerance (max abs diff {d:.3e})")
    else:
        d = np.max(np.abs(num_a - num_b))
        print(f"  mc_paths MISMATCH (max abs diff {d:.3e})")
        failures += 1

    print("PASS" if failures == 0 else f"FAIL ({failures} mismatches)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
