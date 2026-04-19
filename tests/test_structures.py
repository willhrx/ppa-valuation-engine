"""
Tests for supply structure implementations.

Checks the core contract of each SupplyStructure subclass:
- Returns a pd.Series with the same index as inputs
- Values are non-negative where expected
- PayAsProduced: settled == solar
- Baseload: settled is constant
"""

import numpy as np
import pandas as pd
import pytest

from ppa_engine.structures.pay_as_produced import PayAsProduced
from ppa_engine.structures.pay_as_nominated import PayAsNominated
from ppa_engine.structures.baseload import Baseload


@pytest.fixture()
def sample_data():
    idx = pd.date_range("2027-01-01", periods=48, freq="h", tz="Europe/Amsterdam")
    solar = pd.Series(
        np.abs(np.sin(np.linspace(0, 4 * np.pi, 48))) * 30,
        index=idx,
        name="solar_production_mwh",
    )
    load = pd.Series(
        np.ones(48) * 11.4,
        index=idx,
        name="consumer_load_mwh",
    )
    return solar, load


def test_pay_as_produced_equals_solar(sample_data):
    solar, load = sample_data
    structure = PayAsProduced()
    vol = structure.settled_volume(solar, load)
    pd.testing.assert_series_equal(vol, solar, check_names=False)


def test_pay_as_produced_same_index(sample_data):
    solar, load = sample_data
    vol = PayAsProduced().settled_volume(solar, load)
    assert vol.index.equals(solar.index)


def test_baseload_constant(sample_data):
    solar, load = sample_data
    flat = 5.0
    vol = Baseload(flat_volume_mwh=flat).settled_volume(solar, load)
    assert (vol == flat).all()


def test_baseload_defaults_to_solar_mean(sample_data):
    solar, load = sample_data
    vol = Baseload().settled_volume(solar, load)
    assert (vol == solar.mean()).all()


def test_pay_as_nominated_positive(sample_data):
    solar, load = sample_data
    vol = PayAsNominated().settled_volume(solar, load)
    assert (vol >= 0).all()


def test_pay_as_nominated_same_index(sample_data):
    solar, load = sample_data
    vol = PayAsNominated().settled_volume(solar, load)
    assert vol.index.equals(solar.index)
