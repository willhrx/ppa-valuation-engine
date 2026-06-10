"""
cache.py — process-local LRU cache for the central scenario series.

Every endpoint that needs the central (deterministic-seed) scenario was
regenerating the full ~87,600-hour solar / price / load triple from scratch
(~5s of pvlib + AR(1) work) on every call, even when the config had not
changed. This module caches the triple keyed by a hash of the canonical
config JSON.

Not wired into /api/simulate: run_monte_carlo computes its own central
scenario internally (src/ppa_engine is the protected quant core), so the
cache covers /api/valuation/matrix, /api/profiles and /api/solver/*.

Thread safety: FastAPI runs sync endpoints in a threadpool, so access is
guarded by a lock. Returned series are copies — callers can mutate them
without poisoning the cache.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections import OrderedDict
from dataclasses import asdict
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from ppa_engine.config import PPAConfig

# Each entry holds three ~87k-hour float64 Series (~2 MB total).
_MAX_ENTRIES = 8

_lock = threading.Lock()
_store: OrderedDict[str, tuple[pd.Series, pd.Series, pd.Series]] = OrderedDict()


def _config_key(config: "PPAConfig") -> str:
    payload = json.dumps(asdict(config), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def central_series(
    config: "PPAConfig",
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (solar, prices, load) for the central scenario, cached."""
    key = _config_key(config)

    with _lock:
        cached = _store.get(key)
        if cached is not None:
            _store.move_to_end(key)
            solar, prices, load = cached
            return solar.copy(), prices.copy(), load.copy()

    from ppa_engine.data.consumer_load import generate_consumer_load
    from ppa_engine.data.market_prices import generate_market_prices
    from ppa_engine.data.solar_production import generate_solar_production

    solar = generate_solar_production(config)
    prices = generate_market_prices(config)
    load = generate_consumer_load(config)

    with _lock:
        _store[key] = (solar, prices, load)
        _store.move_to_end(key)
        while len(_store) > _MAX_ENTRIES:
            _store.popitem(last=False)

    return solar.copy(), prices.copy(), load.copy()
