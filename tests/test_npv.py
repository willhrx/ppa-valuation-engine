"""
Tests for the NPV calculator (Phase 2).

Placeholder: the NPV function raises NotImplementedError until Phase 2.
This file will be expanded when compute_npv is implemented.
"""

import pytest

from ppa_engine.valuation.npv import compute_npv


def test_npv_raises_not_implemented():
    """Phase 1: NPV is not yet implemented — verify the stub raises correctly."""
    with pytest.raises(NotImplementedError):
        compute_npv(None, None, None)
