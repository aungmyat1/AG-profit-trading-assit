"""TD-6 regression guard: proves get_latest_candles()'s new Layer A raw-candle cache
does NOT break historical_replay/data_source_patch.py's existing replay-substitution
mechanism, which works by monkeypatching each consumer module's own bound name of
get_latest_candles (e.g. `market_structure.analyzer.get_latest_candles`) via
unittest.mock.patch.

This guard exists because an earlier draft of TD-6 (Layer A implemented as an
external wrapper in a separate module, imported under a new name by each consumer)
broke exactly this mechanism: renaming the imported symbol in market_structure/
analyzer.py etc. made `unittest.mock.patch("market_structure.analyzer.get_latest_candles",
...)` raise AttributeError, since that attribute no longer existed. This was caught
by tests/test_session_sweep_continuation_h1_bias.py and others failing during this
same work package, and fixed by moving the cache directly inside
mt5.market_data.get_latest_candles's own body instead. This file proves the fix
holds and prevents the same regression from being reintroduced.
"""
from __future__ import annotations

from unittest.mock import patch

import market_structure.analyzer as ms_analyzer
import mt5.market_data as market_data
import supply_demand.analyzer as sd_analyzer
import supply_demand.native_zones as native_zones
import liquidity.analyzer as liquidity_analyzer


def test_market_structure_analyzer_get_latest_candles_is_still_patchable():
    """The exact attribute historical_replay/data_source_patch.py patches
    (market_structure.analyzer.get_latest_candles) must still exist and be swappable."""
    assert hasattr(ms_analyzer, "get_latest_candles")
    sentinel_called = []

    def fake(symbol, timeframe, count):
        sentinel_called.append((symbol, timeframe, count))
        return []

    with patch.object(ms_analyzer, "get_latest_candles", fake):
        assert ms_analyzer.get_latest_candles("EURUSD", "H1", 5) == []
    assert sentinel_called == [("EURUSD", "H1", 5)]


def test_supply_demand_analyzer_get_latest_candles_is_still_patchable():
    assert hasattr(sd_analyzer, "get_latest_candles")
    with patch.object(sd_analyzer, "get_latest_candles", lambda s, tf, c: ["X"]):
        assert sd_analyzer.get_latest_candles("EURUSD", "H1", 5) == ["X"]


def test_supply_demand_native_zones_get_latest_candles_is_still_patchable():
    assert hasattr(native_zones, "get_latest_candles")
    with patch.object(native_zones, "get_latest_candles", lambda s, tf, c: ["X"]):
        assert native_zones.get_latest_candles("EURUSD", "D1", 1) == ["X"]


def test_liquidity_analyzer_get_latest_candles_is_still_patchable():
    assert hasattr(liquidity_analyzer, "get_latest_candles")
    with patch.object(liquidity_analyzer, "get_latest_candles", lambda s, tf, c: ["X"]):
        assert liquidity_analyzer.get_latest_candles("EURUSD", "H1", 5) == ["X"]


def test_mt5_market_data_get_latest_candles_itself_is_still_patchable():
    """Covers liquidity/affinity.py's per-call local import path (`from mt5.market_data
    import get_latest_candles` inside a function body, re-resolved on every call) --
    patching the source attribute must still work."""
    assert hasattr(market_data, "get_latest_candles")
    with patch.object(market_data, "get_latest_candles", lambda s, tf, c: ["X"]):
        assert market_data.get_latest_candles("EURUSD", "H1", 5) == ["X"]


def test_patch_target_list_in_data_source_patch_matches_reality():
    """Static proof that every string in historical_replay's own
    _PATCHED_CANDLE_TARGETS list still resolves to a real, patchable attribute --
    would have caught the exact regression found during this work package before it
    ever reached a live test run."""
    import importlib

    from historical_replay.data_source_patch import _PATCHED_CANDLE_TARGETS

    for dotted in _PATCHED_CANDLE_TARGETS:
        module_path, attr = dotted.rsplit(".", 1)
        module = importlib.import_module(module_path)
        assert hasattr(module, attr), f"{dotted} no longer resolves -- historical_replay's patch target is stale"
