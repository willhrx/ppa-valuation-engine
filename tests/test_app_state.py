"""Validation tests for the default PPAConfig used by the Streamlit app.

The SessionState class itself wraps ``st.session_state`` and so is not
exercised without a running Streamlit session. The default-config validation
checks here cover the equivalent invariants.
"""

from __future__ import annotations

import pytest

from ppa_engine.config import PPAConfig


def test_default_state_has_valid_config() -> None:
    cfg = PPAConfig()
    cfg.validate()  # must not raise


def test_config_validation_catches_bad_dates() -> None:
    cfg = PPAConfig()
    cfg.deal.start_date = "2030-01-01"
    cfg.deal.end_date = "2027-01-01"
    with pytest.raises(ValueError, match="start_date"):
        cfg.validate()


def test_config_validation_catches_bad_pr() -> None:
    cfg = PPAConfig()
    cfg.solar.performance_ratio = 1.5
    with pytest.raises(ValueError, match="performance_ratio"):
        cfg.validate()
