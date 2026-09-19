"""TD-6: deterministic, offline proof of the D1 duplicate raw-fetch reduction target
TD-5 quantified, through the REAL, unmodified market_structure/liquidity code path
(mocked only at the mt5.market_data.mt5.copy_rates_from_pos boundary -- the actual
MT5 SDK call).

NOTE on scope (see docs/status/TD6_EVENT_DRIVEN_SEMANTIC_CACHE_STATUS.md for the full
reasoning): TD-6 wires Layer A (raw candle cache) into production
(mt5.market_data.get_latest_candles itself). Layer B (derived-fact cache, e.g. for
market_structure.analyze_structure()'s own StructureResult) is built and unit-tested
as a correct, collision-safe MECHANISM (see test_shared_cache_derived_fact_cache.py)
but is deliberately NOT wired into analyze_structure() in production this pass -- an
earlier draft of this file tested that exact integration and had to be reverted after
discovering it (a) broke historical_replay's replay-substitution mechanism and (b)
would have introduced an unrelated correctness risk: two different candle sets
(different replay datasets, different hand-built test fixtures) sharing a timestamp
would return a stale/wrong cached StructureResult, since analyze_structure() has no
way to know which "dataset" it is really answering for. Resolving that safely needs a
replay/dataset-scoped identity, out of TD-6's explicit scope. So this file proves
ONLY the raw-fetch (Layer A) reduction, not a derived-compute reduction -- the H1
duplicate-COMPUTE elimination named in the mission is therefore not yet achieved in
production; only H1/D1's duplicate raw I/O is.
"""
from __future__ import annotations

import time
from unittest.mock import patch

import numpy as np
import pytest

import mt5.market_data as market_data
from liquidity import liquidity_result
from market_structure import analyze_structure
from market_structure.models import MarketStructureConfig
from mt5.symbol_resolver import SymbolMetaError
from supply_demand.native_zones import previous_day_high_low, previous_week_high_low

_SMALL_CONFIG = MarketStructureConfig(swing_length=5, close_break=True, default_analysis_count=20)


@pytest.fixture(autouse=True)
def _clean_cache():
    market_data.clear_raw_candle_cache()
    yield
    market_data.clear_raw_candle_cache()


@pytest.fixture(autouse=True)
def _patch_connection_guards():
    with patch("mt5.market_data._require_connected", return_value=None), \
         patch("mt5.market_data._require_symbol", return_value=None), \
         patch("mt5.market_data._broker_offset_hours", return_value=0):
        yield


def _rates(n, step_seconds=86400):
    start_epoch = int(time.time()) - step_seconds * (n - 1)
    dtype = [("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8"), ("tick_volume", "i8")]
    price = 1.10
    rows = []
    for i in range(n):
        rows.append((start_epoch + step_seconds * i, price, price + 0.0015, price - 0.0012, price, 50))
    return np.array(rows, dtype=dtype)


def _fake_copy_rates_from_pos(call_log):
    def _fake(symbol, mt5_timeframe, pos, count):
        call_log.append(count)
        return _rates(count)
    return _fake


# --------------------------------------------------------------------------- D1 duplicate raw-fetch target

def test_d1_analyze_structure_called_directly_and_again_inside_liquidity_result_dedupes_raw_fetch():
    """Simulates the specific overlap inside TD-5's D1 finding: build_daily_context()
    calls analyze_structure(D1) directly, AND liquidity_result(D1) calls
    analyze_structure(D1) again internally (liquidity/analyzer.py::_structural_levels)
    with the SAME fetch_count -- these two raw fetches now collapse into one real MT5
    call, transparently, with zero change to either caller. liquidity_result's own
    separate candles fetch (a different requested count) remains its own distinct,
    non-merged fetch."""
    call_log = []

    with patch("mt5.market_data.mt5.copy_rates_from_pos", side_effect=_fake_copy_rates_from_pos(call_log)), \
         patch("liquidity.analyzer.load_liquidity_config") as mock_liq_config, \
         patch("liquidity.analyzer.get_tick", side_effect=market_data.MarketDataError("DATA_MISSING", "no live tick in this deterministic test")), \
         patch("liquidity.analyzer.get_symbol_meta", side_effect=SymbolMetaError("no symbol meta needed for this proof")):
        mock_liq_config.return_value.lookback_bars = 100  # deliberately a DIFFERENT count than analyze_structure's 120
        mock_liq_config.return_value.equal_level_tolerance_points = 5
        mock_liq_config.return_value.local_extremum_window = 2

        direct_result = analyze_structure("EURUSD", "D1", config=_SMALL_CONFIG)  # fetch_count = 20+100 = 120
        liquidity_result("EURUSD", "D1")  # internally calls analyze_structure("EURUSD","D1") again, same fetch_count

    # analyze_structure's own fetch_count (120) was requested twice but only fetched
    # from MT5 once -- the second, identical request was served from Layer A.
    assert call_log.count(120) == 1
    # liquidity_result's own 100-count candle fetch is a genuinely different request
    # shape and is NOT merged with the 120-count request.
    assert 100 in call_log
    assert direct_result.status == "VALID"


def test_d1_different_requested_counts_are_never_incorrectly_merged():
    """Explicit negative proof: previous_day_high_low(count=1) and
    previous_week_high_low(count=15) must never collapse into the same cache entry as
    each other or as analyze_structure's own fetch, even though all three target the
    same symbol/timeframe."""
    call_log = []

    with patch("mt5.market_data.mt5.copy_rates_from_pos", side_effect=_fake_copy_rates_from_pos(call_log)), \
         patch("supply_demand.native_zones.get_tick", side_effect=market_data.MarketDataError("DATA_MISSING", "no live tick in this deterministic test")):
        previous_day_high_low("EURUSD")
        previous_week_high_low("EURUSD")

    assert call_log == [1, 15]  # two distinct, never-merged requests


def test_h1_duplicate_raw_fetch_is_eliminated_even_though_compute_is_not_yet_cached():
    """H1 analogue of the D1 proof above -- analyze_structure(H1) called twice with
    identical parameters performs only ONE real MT5 fetch (Layer A), even though the
    smc computation itself still re-runs both times (Layer B not wired to production
    this pass -- see module docstring)."""
    call_log = []
    with patch("mt5.market_data.mt5.copy_rates_from_pos", side_effect=_fake_copy_rates_from_pos(call_log)):
        result_1 = analyze_structure("EURUSD", "H1", config=_SMALL_CONFIG)
        result_2 = analyze_structure("EURUSD", "H1", config=_SMALL_CONFIG)

    assert len(call_log) == 1  # raw fetch deduplicated
    assert result_1.status == "VALID"
    assert result_2.status == "VALID"
    assert result_1 == result_2  # same computed values (dataclass equality)
    # NOT the same object -- proves the smc computation genuinely ran twice (Layer B
    # is not active here); this documents current, honest production behavior rather
    # than overclaiming a compute-level dedup that isn't wired in.
    assert result_1 is not result_2
