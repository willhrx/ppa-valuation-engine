"""Statistical sanity tests for the shared AR(1) helpers."""

from __future__ import annotations

import numpy as np

from ppa_engine.utils.ar1 import ar1_logit_process, ar1_process


def test_ar1_stationary_variance() -> None:
    """ar1_process must produce a series with marginal std ≈ sigma_stationary."""
    sigma = 8.0
    out = ar1_process(n=100_000, phi=0.70, sigma_stationary=sigma, seed=1)
    assert out.shape == (100_000,)
    assert abs(np.std(out) - sigma) / sigma < 0.02


def test_ar1_logit_values_in_range() -> None:
    """ar1_logit_process must remain strictly in (0, 1) at every step."""
    n = 50_000
    monthly_logit_means = np.full(n, 0.5)
    out = ar1_logit_process(
        n=n,
        phi=0.9,
        logit_scale=0.7,
        monthly_logit_means=monthly_logit_means,
        seed=42,
    )
    assert out.shape == (n,)
    assert np.all((out > 0.0) & (out < 1.0))
