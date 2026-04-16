"""
production_scenarios.py — Solar production P10/P50/P90 scenarios (Phase 3).

P50 is the central (median) production scenario — what we expect half the time.
P90 is the conservative case: production exceeds this only 90 % of years.
P10 is the optimistic case: production exceeds this 10 % of years.

The spread between P10 and P90 reflects volume risk (interannual variability
of solar irradiance).  For NL utility-scale solar, P90/P50 ≈ 0.88–0.93.

Modelling approach: re-run the cloud factor simulation N times with different
seeds, compute annual totals, and read off the percentiles.  This propagates
cloud autocorrelation correctly into the annual production distribution.
"""

from __future__ import annotations

# TODO (Phase 3): implement production scenario generator


def generate_production_scenarios(*args, **kwargs):  # type: ignore[return]
    """Generate P10/P50/P90 production paths via cloud factor resampling. (Phase 3)"""
    raise NotImplementedError(
        "Production scenario generator will be implemented in Phase 3."
    )
