"""TD-8: unit tests for historical_replay/dataset_identity.py (ReplayDatasetIdentity,
compute_candle_series_fingerprint, build_dataset_identity) and the additive
HistoricalCandleStore changes (W1 support, naive-datetime rejection,
dataset_identity() accessor). See tests/test_topdown_composer_replay.py for the
end-to-end, real-detector proof of the same collision-safety properties through the
full six-tier composer.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from historical_replay.candle_store import HistoricalCandleStore, HistoricalDataError, TIMEFRAME_MINUTES
from historical_replay.dataset_identity import build_dataset_identity, compute_candle_series_fingerprint
from strategy_engine.session import Candle

UTC = timezone.utc


def _candles(n=3, start=None, base=1.1000, step=0.0005):
    start = start or datetime(2026, 1, 6, 0, 0, tzinfo=UTC)
    out = []
    for i in range(n):
        t = start + timedelta(minutes=5 * i)
        out.append(Candle(time=t, open=base, high=base + step, low=base - step, close=base + step / 2, volume=10.0))
        base += step
    return out


# --------------------------------------------------------------------------- W1 support (additive)

def test_w1_added_to_timeframe_minutes():
    assert TIMEFRAME_MINUTES["W1"] == 10080


def test_store_accepts_w1_series():
    store = HistoricalCandleStore()
    candles = _candles(3, step=0)  # doesn't matter for this test
    store.load_series("EURUSD", "W1", candles)
    result = store.closed_candles("EURUSD", "W1", candles[-1].time + timedelta(minutes=10080), 1)
    assert result[0].time == candles[-1].time


# --------------------------------------------------------------------------- naive-datetime rejection (additive)

def test_closed_candles_rejects_naive_as_of():
    store = HistoricalCandleStore()
    store.load_series("EURUSD", "M5", _candles())
    with pytest.raises(HistoricalDataError) as exc_info:
        store.closed_candles("EURUSD", "M5", datetime(2026, 1, 6, 1, 0), 1)  # no tzinfo
    assert exc_info.value.reason_code == "NAIVE_DATETIME_REJECTED"


def test_last_closed_price_rejects_naive_as_of():
    store = HistoricalCandleStore()
    store.load_series("EURUSD", "M5", _candles())
    with pytest.raises(HistoricalDataError) as exc_info:
        store.last_closed_price("EURUSD", "M5", datetime(2026, 1, 6, 1, 0))
    assert exc_info.value.reason_code == "NAIVE_DATETIME_REJECTED"


def test_aware_as_of_still_works_after_naive_guard_added():
    """Regression: the new guard must not affect any existing, already-tz-aware
    caller (every existing production/test usage)."""
    store = HistoricalCandleStore()
    candles = _candles(3)
    store.load_series("EURUSD", "M5", candles)
    result = store.closed_candles("EURUSD", "M5", candles[-1].time + timedelta(minutes=5), 1)
    assert result[0].time == candles[-1].time


# --------------------------------------------------------------------------- dataset_identity() accessor (additive)

def test_dataset_identity_is_none_when_never_loaded():
    store = HistoricalCandleStore()
    assert store.dataset_identity("EURUSD", "M5") is None


def test_dataset_identity_present_after_load_series_with_no_explicit_label():
    """Backward compatibility: every pre-TD-8 call site never passed dataset_id/source
    -- confirms an identity is still computed automatically, not None."""
    store = HistoricalCandleStore()
    store.load_series("EURUSD", "M5", _candles())
    identity = store.dataset_identity("EURUSD", "M5")
    assert identity is not None
    assert identity.symbol == "EURUSD" and identity.timeframe == "M5"
    assert identity.fingerprint.startswith("sha256:")


def test_dataset_identity_uses_explicit_label_when_supplied():
    store = HistoricalCandleStore()
    store.load_series("EURUSD", "M5", _candles(), dataset_id="MY_DATASET", source="VENDOR_X")
    identity = store.dataset_identity("EURUSD", "M5")
    assert identity.dataset_id == "MY_DATASET"
    assert identity.source == "VENDOR_X"


def test_dataset_identity_coverage_reflects_actual_candle_span():
    candles = _candles(5)
    store = HistoricalCandleStore()
    store.load_series("EURUSD", "M5", candles)
    identity = store.dataset_identity("EURUSD", "M5")
    assert identity.coverage_start == candles[0].time
    assert identity.coverage_end == candles[-1].time


# --------------------------------------------------------------------------- compute_candle_series_fingerprint

def test_fingerprint_is_deterministic():
    candles = _candles(5)
    assert compute_candle_series_fingerprint("EURUSD", "M5", candles) == compute_candle_series_fingerprint("EURUSD", "M5", candles)


def test_fingerprint_independent_of_input_order():
    candles = _candles(5)
    reversed_candles = list(reversed(candles))
    assert compute_candle_series_fingerprint("EURUSD", "M5", candles) == compute_candle_series_fingerprint("EURUSD", "M5", reversed_candles)


def test_fingerprint_differs_for_different_content_same_timestamps():
    """The exact TD-8 dataset-collision scenario: same symbol/timeframe/timestamps,
    different OHLC content -- must never fingerprint the same."""
    start = datetime(2026, 1, 6, 0, 0, tzinfo=UTC)
    candles_a = _candles(5, start=start, base=1.1000)
    candles_b = _candles(5, start=start, base=1.3000)
    assert [c.time for c in candles_a] == [c.time for c in candles_b]
    assert compute_candle_series_fingerprint("EURUSD", "M5", candles_a) != compute_candle_series_fingerprint("EURUSD", "M5", candles_b)


def test_fingerprint_differs_for_different_symbol_same_candles():
    candles = _candles(3)
    assert compute_candle_series_fingerprint("EURUSD", "M5", candles) != compute_candle_series_fingerprint("GBPUSD", "M5", candles)


def test_fingerprint_differs_for_different_timeframe_same_candles():
    candles = _candles(3)
    assert compute_candle_series_fingerprint("EURUSD", "M5", candles) != compute_candle_series_fingerprint("EURUSD", "M15", candles)


# --------------------------------------------------------------------------- build_dataset_identity

def test_build_dataset_identity_rejects_empty_candles():
    with pytest.raises(ValueError):
        build_dataset_identity(symbol="EURUSD", timeframe="M5", candles=[])


def test_build_dataset_identity_auto_generates_a_dataset_id_when_omitted():
    candles = _candles(3)
    identity = build_dataset_identity(symbol="EURUSD", timeframe="M5", candles=candles)
    assert identity.dataset_id.startswith("EURUSD:M5:")
    assert identity.source == "REPLAY"  # documented default


def test_as_composed_identity_token_is_deterministic_and_content_sensitive():
    start = datetime(2026, 1, 6, 0, 0, tzinfo=UTC)
    candles_a = _candles(3, start=start, base=1.1000)
    candles_b = _candles(3, start=start, base=1.3000)
    identity_a = build_dataset_identity(symbol="EURUSD", timeframe="M5", candles=candles_a, dataset_id="X", source="S")
    identity_b = build_dataset_identity(symbol="EURUSD", timeframe="M5", candles=candles_b, dataset_id="X", source="S")
    assert identity_a.as_composed_identity_token() != identity_b.as_composed_identity_token()
    identity_a_again = build_dataset_identity(symbol="EURUSD", timeframe="M5", candles=candles_a, dataset_id="X", source="S")
    assert identity_a.as_composed_identity_token() == identity_a_again.as_composed_identity_token()
