"""TD-6, Layer A: tests for the raw closed-candle cache wired directly into
mt5.market_data.get_latest_candles(). All deterministic/unit -- mocks
mt5.copy_rates_from_pos (the actual MT5 SDK boundary), no live terminal needed.

This supersedes an earlier draft that wrapped get_latest_candles externally (in a
separate shared_cache.raw_candle_cache module) -- that approach was found, during
this same work package, to break historical_replay/data_source_patch.py's existing
replay-substitution mechanism (which monkeypatches get_latest_candles's own bound
name per consumer module; an external wrapper calling a fixed, already-resolved
reference to the real function bypasses that patch entirely). Caching directly inside
get_latest_candles's own body is immune to that problem by construction: when
replay patches the function's name, the ENTIRE function (cache included) is replaced.
See tests/test_mt5_market_data_replay_patch_compatibility.py for that specific proof.
"""
from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

import mt5.market_data as market_data
from mt5.market_data import MarketDataError, get_latest_candles

UTC = dt.timezone.utc


@pytest.fixture(autouse=True)
def _clean_cache():
    market_data.clear_raw_candle_cache()
    yield
    market_data.clear_raw_candle_cache()


def _rates(n, start_epoch=None, step_seconds=300):
    """Builds a numpy structured array shaped like what mt5.copy_rates_from_pos
    returns (time/open/high/low/close/tick_volume fields), anchored to real
    wall-clock now (minus enough span that the LAST rate's own close is still safely
    in the future -- see test_shared_cache_raw_candle_cache.py's historical note on
    why a hardcoded past date would make every cache entry born-expired)."""
    if start_epoch is None:
        import time
        start_epoch = int(time.time()) - step_seconds * (n - 1)
    dtype = [("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8"), ("tick_volume", "i8")]
    rows = [
        (start_epoch + step_seconds * i, 1.10, 1.1015, 1.0985, 1.10, 50)
        for i in range(n)
    ]
    return np.array(rows, dtype=dtype)


@pytest.fixture(autouse=True)
def _patch_connection_guards():
    with patch("mt5.market_data._require_connected", return_value=None), \
         patch("mt5.market_data._require_symbol", return_value=None), \
         patch("mt5.market_data._broker_offset_hours", return_value=0):
        yield


# --------------------------------------------------------------------------- 1/6. identical request -> hit

def test_identical_request_is_a_cache_hit_no_second_provider_call():
    rates = _rates(5)
    with patch("mt5.market_data.mt5.copy_rates_from_pos", return_value=rates) as mock_copy:
        first = get_latest_candles("EURUSD", "M5", 5)
        second = get_latest_candles("EURUSD", "M5", 5)

    mock_copy.assert_called_once()
    assert len(first) == 5
    assert first == second
    diag = market_data.raw_candle_cache_diagnostics()
    assert diag["hits"] == 1
    assert diag["misses"] == 1


# --------------------------------------------------------------------------- 3/4/5. different request shape -> miss

def test_different_symbol_is_a_miss():
    with patch("mt5.market_data.mt5.copy_rates_from_pos", return_value=_rates(5)) as mock_copy:
        get_latest_candles("EURUSD", "M5", 5)
        get_latest_candles("GBPUSD", "M5", 5)
    assert mock_copy.call_count == 2


def test_different_timeframe_is_a_miss():
    with patch("mt5.market_data.mt5.copy_rates_from_pos", return_value=_rates(5)) as mock_copy:
        get_latest_candles("EURUSD", "M5", 5)
        get_latest_candles("EURUSD", "H1", 5)
    assert mock_copy.call_count == 2


def test_different_count_is_a_miss_never_merged():
    def _fake_copy(symbol, timeframe, pos, count):
        return _rates(count)

    with patch("mt5.market_data.mt5.copy_rates_from_pos", side_effect=_fake_copy) as mock_copy:
        get_latest_candles("EURUSD", "M5", 5)
        get_latest_candles("EURUSD", "M5", 10)  # different requested count -- must NOT reuse
    assert mock_copy.call_count == 2


# --------------------------------------------------------------------------- 2. changed closed-bar identity -> miss

def test_stale_entry_beyond_its_own_bar_period_is_a_miss():
    import time
    old_rates = _rates(5, start_epoch=int(time.time()) - 3600 * 24 * 30)  # 30 days old -> already stale
    new_rates = _rates(5)
    with patch("mt5.market_data.mt5.copy_rates_from_pos", side_effect=[old_rates, new_rates]) as mock_copy:
        first = get_latest_candles("EURUSD", "M5", 5)
        second = get_latest_candles("EURUSD", "M5", 5)
    assert mock_copy.call_count == 2
    assert first != second


# --------------------------------------------------------------------------- 10. failed calculation not cached

def test_data_missing_error_is_never_cached_and_propagates():
    with patch("mt5.market_data.mt5.copy_rates_from_pos", return_value=None), \
         patch("mt5.market_data.mt5.last_error", return_value=(1, "no data")):
        with pytest.raises(MarketDataError):
            get_latest_candles("EURUSD", "M5", 5)
    diag = market_data.raw_candle_cache_diagnostics()
    assert diag["size"] == 0


def test_failure_then_success_recovers_normally():
    rates = _rates(5)
    with patch("mt5.market_data.mt5.copy_rates_from_pos", side_effect=[None, rates]), \
         patch("mt5.market_data.mt5.last_error", return_value=(1, "no data")):
        with pytest.raises(MarketDataError):
            get_latest_candles("EURUSD", "M5", 5)
        result = get_latest_candles("EURUSD", "M5", 5)
    assert len(result) == 5


# --------------------------------------------------------------------------- 12. mutation isolation

def test_returned_list_mutation_does_not_corrupt_cached_entry():
    with patch("mt5.market_data.mt5.copy_rates_from_pos", return_value=_rates(5)):
        first = get_latest_candles("EURUSD", "M5", 5)
        first.append("garbage")
        second = get_latest_candles("EURUSD", "M5", 5)
    assert "garbage" not in second
    assert len(second) == 5


# --------------------------------------------------------------------------- diagnostics

def test_diagnostics_reset_by_clear_cache():
    with patch("mt5.market_data.mt5.copy_rates_from_pos", return_value=_rates(5)):
        get_latest_candles("EURUSD", "M5", 5)
    market_data.clear_raw_candle_cache()
    diag = market_data.raw_candle_cache_diagnostics()
    assert diag == {"hits": 0, "misses": 0, "evictions": 0, "puts": 0, "size": 0}


# --------------------------------------------------------------------------- unaffected guards

def test_existing_guards_still_enforced_on_a_miss():
    """UNSUPPORTED_TIMEFRAME/DATA_MISSING/INSUFFICIENT_CANDLES guards must remain
    exactly as before -- caching only wraps around them, never bypasses them."""
    with pytest.raises(MarketDataError) as exc_info:
        get_latest_candles("EURUSD", "M2", 5)
    assert exc_info.value.reason_code == "UNSUPPORTED_TIMEFRAME"
