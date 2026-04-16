"""
solver.py — Break-even price solver (Phase 4).

Uses ``scipy.optimize.brentq`` to find the fixed strike price that makes the
PPA NPV exactly zero — i.e., the price at which the producer is indifferent
between the PPA and selling at spot.

The break-even price is the central output of the pricing conversation:
  - Producer's floor: they need at least this much to cover LCOE.
  - Offtaker's ceiling: they compare it to their next-best alternative.
  - The negotiated price lives somewhere in between.

The solver also supports computing break-even under different Monte Carlo
scenario sets (P10/P50/P90) for a risk-aware pricing range.
"""

from __future__ import annotations

# TODO (Phase 4): implement break-even solver using scipy.optimize.brentq


def breakeven_strike(*args, **kwargs):  # type: ignore[return]
    """Find the fixed strike price at which PPA NPV = 0. (Phase 4)"""
    raise NotImplementedError("Break-even solver will be implemented in Phase 4.")
