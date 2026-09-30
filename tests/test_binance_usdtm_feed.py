"""Tests for execution_runtime.binance_usdtm_feed.BinanceUSDTMFeed -- fully offline, no
real network call (spec: "unit tests must NOT hit the real network"). The HTTP boundary is
mocked at the `session.get(...)` call the feed makes internally (a fake session object with
a `.get` that returns a fake response with `.raise_for_status()`/`.json()`), same
dependency-injection idiom the rest of this package already uses.
"""
from __future__ import annotations

import datetime as dt

import pytest

from execution_runtime.binance_usdtm_feed import (
    BTCUSDT_STEP_SIZE,
    BTCUSDT_TICK_SIZE,
    BinanceFeedDataError,
    BinanceFeedRequestError,
    BinanceFeedStaleData,
    BinanceUSDTMFeed,
    CANONICAL_SYMBOL,
    default_symbol_meta,
    fetch_exchange_symbol_meta,
)

M5_MS = 5 * 60 * 1000
H1_MS = 60 * 60 * 1000
BASE_OPEN_MS = 1_800_000_000_000  # arbitrary but fixed anchor, ms since epoch


def _row(open_ms, o, h, l, c, v=100.0, close_offset_ms=None, span_ms=M5_MS):
    close_ms = open_ms + span_ms - 1 if close_offset_ms is None else close_offset_ms
    return [open_ms, str(o), str(h), str(l), str(c), str(v), close_ms, "0", 1, "0", "0", "0"]


def _clean_m5_rows(n=5, start_ms=BASE_OPEN_MS, price=50000.0):
    rows = []
    for i in range(n):
        t = start_ms + i * M5_MS
        rows.append(_row(t, price, price + 10, price - 10, price + 5))
    return rows


class _FakeResponse:
    def __init__(self, payload, status_ok=True):
        self._payload = payload
        self._status_ok = status_ok

    def raise_for_status(self):
        if not self._status_ok:
            import requests
            raise requests.HTTPError("mock HTTP error")

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, payload, status_ok=True):
        self.payload = payload
        self.status_ok = status_ok
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        return _FakeResponse(self.payload, self.status_ok)


def _now_after(rows):
    last_close_ms = rows[-1][6]
    return lambda: dt.datetime.fromtimestamp((last_close_ms + 1) / 1000.0, tz=dt.timezone.utc)


# ------------------------------------------------------------------------------- happy path

def test_returns_closed_candles_oldest_first_utc():
    rows = _clean_m5_rows(5)
    session = _FakeSession(rows)
    feed = BinanceUSDTMFeed(session=session, clock=_now_after(rows))
    candles = feed.get_latest_candles("BTCUSDT", "M5", 5)
    assert len(candles) == 5
    assert candles[0].time < candles[-1].time
    assert candles[0].time.tzinfo == dt.timezone.utc
    assert candles[0].open == 50000.0
    assert candles[0].high == 50010.0


def test_requests_count_plus_one_from_exchange():
    rows = _clean_m5_rows(5)
    session = _FakeSession(rows)
    feed = BinanceUSDTMFeed(session=session, clock=_now_after(rows))
    feed.get_latest_candles("BTCUSDT", "M5", 5)
    _, params, _ = session.calls[0]
    assert params["limit"] == 6
    assert params["interval"] == "5m"
    assert params["symbol"] == "BTCUSDT"


def test_h1_timeframe_maps_to_1h_interval():
    rows = []
    for i in range(3):
        t = BASE_OPEN_MS + i * H1_MS
        rows.append(_row(t, 50000, 50100, 49900, 50050, span_ms=H1_MS))
    session = _FakeSession(rows)
    feed = BinanceUSDTMFeed(session=session, clock=_now_after(rows))
    candles = feed.get_latest_candles("BTCUSDT", "H1", 3)
    assert len(candles) == 3
    assert session.calls[0][1]["interval"] == "1h"


# ------------------------------------------------------------------------- forming candle

def test_drops_unfinished_forming_last_candle():
    rows = _clean_m5_rows(5)
    # "now" is inside the last candle's still-open window -> it must be dropped.
    forming_open = rows[-1][0]
    now = lambda: dt.datetime.fromtimestamp((forming_open + 60_000) / 1000.0, tz=dt.timezone.utc)
    session = _FakeSession(rows)
    feed = BinanceUSDTMFeed(session=session, clock=now)
    candles = feed.get_latest_candles("BTCUSDT", "M5", 4)
    assert len(candles) == 4
    assert candles[-1].time == dt.datetime.fromtimestamp(rows[-2][0] / 1000.0, tz=dt.timezone.utc)


def test_all_candles_forming_raises():
    rows = _clean_m5_rows(1)
    now = lambda: dt.datetime.fromtimestamp(rows[0][0] / 1000.0, tz=dt.timezone.utc)
    session = _FakeSession(rows)
    feed = BinanceUSDTMFeed(session=session, clock=now)
    with pytest.raises(BinanceFeedDataError) as exc:
        feed.get_latest_candles("BTCUSDT", "M5", 1)
    assert exc.value.reason_code == "KLINES_ALL_CANDLES_FORMING"


# --------------------------------------------------------------------------- monotonicity

def test_non_monotonic_timestamps_rejected():
    rows = _clean_m5_rows(3)
    rows[2][0] = rows[0][0]  # third row's open_time goes backward
    rows[2][6] = rows[0][6]
    session = _FakeSession(rows)
    feed = BinanceUSDTMFeed(session=session, clock=_now_after(rows))
    with pytest.raises(BinanceFeedDataError) as exc:
        feed.get_latest_candles("BTCUSDT", "M5", 3)
    assert exc.value.reason_code in ("CANDLE_NON_MONOTONIC", "CANDLE_DUPLICATE_TIMESTAMP")


def test_duplicate_timestamp_rejected():
    rows = _clean_m5_rows(3)
    dup = _row(rows[1][0], 50000, 50010, 49990, 50005)
    rows.insert(2, dup)
    session = _FakeSession(rows)
    feed = BinanceUSDTMFeed(session=session, clock=_now_after(rows))
    with pytest.raises(BinanceFeedDataError) as exc:
        feed.get_latest_candles("BTCUSDT", "M5", 4)
    assert exc.value.reason_code == "CANDLE_DUPLICATE_TIMESTAMP"


def test_missing_candle_gap_rejected():
    rows = _clean_m5_rows(3)
    rows[2][0] += M5_MS  # skip one bar -> gap of 2xM5 instead of 1x
    rows[2][6] += M5_MS
    session = _FakeSession(rows)
    feed = BinanceUSDTMFeed(session=session, clock=_now_after(rows))
    with pytest.raises(BinanceFeedDataError) as exc:
        feed.get_latest_candles("BTCUSDT", "M5", 3)
    assert exc.value.reason_code == "CANDLE_UNEXPECTED_SPACING"


# ------------------------------------------------------------------------------ OHLC / NaN

def test_ohlc_inconsistent_high_rejected():
    rows = _clean_m5_rows(1)
    rows[0][2] = "100"  # high below open/close
    session = _FakeSession(rows)
    feed = BinanceUSDTMFeed(session=session, clock=_now_after(rows))
    with pytest.raises(BinanceFeedDataError) as exc:
        feed.get_latest_candles("BTCUSDT", "M5", 1)
    assert exc.value.reason_code == "CANDLE_OHLC_INCONSISTENT"


def test_ohlc_inconsistent_low_rejected():
    rows = _clean_m5_rows(1)
    rows[0][3] = "999999"  # low above open/close/high
    session = _FakeSession(rows)
    feed = BinanceUSDTMFeed(session=session, clock=_now_after(rows))
    with pytest.raises(BinanceFeedDataError) as exc:
        feed.get_latest_candles("BTCUSDT", "M5", 1)
    assert exc.value.reason_code == "CANDLE_OHLC_INCONSISTENT"


def test_null_field_rejected():
    rows = _clean_m5_rows(1)
    rows[0][1] = None
    session = _FakeSession(rows)
    feed = BinanceUSDTMFeed(session=session, clock=_now_after(rows))
    with pytest.raises(BinanceFeedDataError) as exc:
        feed.get_latest_candles("BTCUSDT", "M5", 1)
    assert exc.value.reason_code == "CANDLE_NULL_FIELD"


def test_nan_field_rejected():
    rows = _clean_m5_rows(1)
    rows[0][1] = "nan"
    session = _FakeSession(rows)
    feed = BinanceUSDTMFeed(session=session, clock=_now_after(rows))
    with pytest.raises(BinanceFeedDataError) as exc:
        feed.get_latest_candles("BTCUSDT", "M5", 1)
    assert exc.value.reason_code == "CANDLE_NAN_FIELD"


def test_non_numeric_field_rejected():
    rows = _clean_m5_rows(1)
    rows[0][1] = "not-a-number"
    session = _FakeSession(rows)
    feed = BinanceUSDTMFeed(session=session, clock=_now_after(rows))
    with pytest.raises(BinanceFeedDataError) as exc:
        feed.get_latest_candles("BTCUSDT", "M5", 1)
    assert exc.value.reason_code == "CANDLE_NON_NUMERIC_FIELD"


def test_impossible_non_positive_price_rejected():
    rows = _clean_m5_rows(1)
    rows[0][1] = "0"
    session = _FakeSession(rows)
    feed = BinanceUSDTMFeed(session=session, clock=_now_after(rows))
    with pytest.raises(BinanceFeedDataError) as exc:
        feed.get_latest_candles("BTCUSDT", "M5", 1)
    assert exc.value.reason_code == "CANDLE_NON_POSITIVE_PRICE"


def test_negative_price_rejected():
    rows = _clean_m5_rows(1)
    rows[0][3] = "-5"
    session = _FakeSession(rows)
    feed = BinanceUSDTMFeed(session=session, clock=_now_after(rows))
    with pytest.raises(BinanceFeedDataError) as exc:
        feed.get_latest_candles("BTCUSDT", "M5", 1)
    assert exc.value.reason_code in ("CANDLE_NON_POSITIVE_PRICE", "CANDLE_OHLC_INCONSISTENT")


def test_negative_volume_rejected():
    rows = _clean_m5_rows(1)
    rows[0][5] = "-1.0"
    session = _FakeSession(rows)
    feed = BinanceUSDTMFeed(session=session, clock=_now_after(rows))
    with pytest.raises(BinanceFeedDataError) as exc:
        feed.get_latest_candles("BTCUSDT", "M5", 1)
    assert exc.value.reason_code == "CANDLE_NEGATIVE_VOLUME"


def test_zero_volume_is_valid():
    rows = _clean_m5_rows(1)
    rows[0][5] = "0"
    session = _FakeSession(rows)
    feed = BinanceUSDTMFeed(session=session, clock=_now_after(rows))
    candles = feed.get_latest_candles("BTCUSDT", "M5", 1)
    assert candles[0].volume == 0.0


def test_malformed_open_timestamp_normalized_not_leaked():
    rows = _clean_m5_rows(1)
    rows[0][0] = "not-a-timestamp"
    session = _FakeSession(rows)
    feed = BinanceUSDTMFeed(session=session, clock=lambda: dt.datetime.now(dt.timezone.utc))
    with pytest.raises(BinanceFeedDataError) as exc:
        feed.get_latest_candles("BTCUSDT", "M5", 1)
    assert exc.value.reason_code == "CANDLE_MALFORMED_TIMESTAMP"
    assert "not-a-timestamp" in str(exc.value)


def test_null_close_timestamp_normalized_not_leaked():
    rows = _clean_m5_rows(1)
    rows[0][6] = None
    session = _FakeSession(rows)
    feed = BinanceUSDTMFeed(session=session, clock=lambda: dt.datetime.now(dt.timezone.utc))
    with pytest.raises(BinanceFeedDataError) as exc:
        feed.get_latest_candles("BTCUSDT", "M5", 1)
    assert exc.value.reason_code == "CANDLE_NULL_TIMESTAMP"


def test_out_of_range_open_timestamp_normalized_not_leaked():
    # A numerically valid but astronomically out-of-range epoch-ms can never reach this
    # point through get_latest_candles's own pipeline (it always trips the forming-candle
    # or staleness gate first, both of which compare against "now" and reject it earlier)
    # -- so this exercises _to_candles's own OverflowError/OSError normalization directly,
    # as the internal defense-in-depth it is (spec: "malformed exchange timestamps must
    # not leak arbitrary low-level exceptions" -- true regardless of which gate a given
    # bad value happens to be caught by first).
    from execution_runtime.binance_usdtm_feed import _to_candles
    parsed = [{"open_time_ms": 10**18, "close_time_ms": 10**18, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}]
    with pytest.raises(BinanceFeedDataError) as exc:
        _to_candles(parsed, "BTCUSDT", "M5")
    assert exc.value.reason_code == "CANDLE_TIMESTAMP_OUT_OF_RANGE"


# ---------------------------------------------------------------------------------- stale

def test_stale_data_rejected():
    rows = _clean_m5_rows(3)
    far_future = lambda: dt.datetime.fromtimestamp(
        (rows[-1][6] + M5_MS * 10) / 1000.0, tz=dt.timezone.utc
    )
    session = _FakeSession(rows)
    feed = BinanceUSDTMFeed(session=session, clock=far_future)
    with pytest.raises(BinanceFeedStaleData) as exc:
        feed.get_latest_candles("BTCUSDT", "M5", 3)
    assert exc.value.reason_code == "KLINES_STALE_DATA"


# ------------------------------------------------------------------------- transport/shape

def test_http_error_raises_request_error():
    session = _FakeSession([], status_ok=False)
    feed = BinanceUSDTMFeed(session=session, clock=lambda: dt.datetime.now(dt.timezone.utc))
    with pytest.raises(BinanceFeedRequestError) as exc:
        feed.get_latest_candles("BTCUSDT", "M5", 3)
    assert exc.value.reason_code == "KLINES_REQUEST_FAILED"


def test_empty_response_rejected():
    session = _FakeSession([])
    feed = BinanceUSDTMFeed(session=session, clock=lambda: dt.datetime.now(dt.timezone.utc))
    with pytest.raises(BinanceFeedDataError) as exc:
        feed.get_latest_candles("BTCUSDT", "M5", 3)
    assert exc.value.reason_code == "KLINES_EMPTY_RESPONSE"


def test_malformed_response_shape_rejected():
    session = _FakeSession({"not": "a list"})
    feed = BinanceUSDTMFeed(session=session, clock=lambda: dt.datetime.now(dt.timezone.utc))
    with pytest.raises(BinanceFeedDataError) as exc:
        feed.get_latest_candles("BTCUSDT", "M5", 3)
    assert exc.value.reason_code == "KLINES_MALFORMED_RESPONSE"


def test_wrong_symbol_rejected():
    session = _FakeSession(_clean_m5_rows(1))
    feed = BinanceUSDTMFeed(session=session, clock=lambda: dt.datetime.now(dt.timezone.utc))
    with pytest.raises(ValueError):
        feed.get_latest_candles("ETHUSDT", "M5", 1)


def test_unsupported_timeframe_rejected():
    session = _FakeSession(_clean_m5_rows(1))
    feed = BinanceUSDTMFeed(session=session, clock=lambda: dt.datetime.now(dt.timezone.utc))
    with pytest.raises(ValueError):
        feed.get_latest_candles("BTCUSDT", "M15", 1)


# ------------------------------------------------------------------------------ symbol meta

def test_default_symbol_meta_matches_crypto_symbols_assumption():
    from strategy_engine.sweep_retest.crypto_symbols import CRYPTO_TICK_SIZE
    meta = default_symbol_meta("BTCUSDT")
    assert meta.tick_size == BTCUSDT_TICK_SIZE == CRYPTO_TICK_SIZE["BTCUSDT"]
    assert meta.step_size == BTCUSDT_STEP_SIZE == 0.001
    assert meta.exchange == "BINANCE_USDT_M_PERP"
    assert meta.canonical_symbol == CANONICAL_SYMBOL


def test_default_symbol_meta_rejects_other_symbol():
    with pytest.raises(ValueError):
        default_symbol_meta("ETHUSDT")


def test_fetch_exchange_symbol_meta_parses_live_shape():
    payload = {
        "symbols": [
            {
                "symbol": "BTCUSDT", "marginAsset": "USDT", "contractType": "PERPETUAL",
                "pricePrecision": 1, "quantityPrecision": 3,
                "filters": [
                    {"filterType": "PRICE_FILTER", "tickSize": "0.10", "maxPrice": "1000000", "minPrice": "0.1"},
                    {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001", "maxQty": "1000"},
                ],
            }
        ]
    }
    session = _FakeSession(payload)
    meta = fetch_exchange_symbol_meta("BTCUSDT", session=session)
    assert meta.tick_size == 0.1
    assert meta.step_size == 0.001
    assert meta.source == "LIVE_EXCHANGE_INFO"
    assert meta.fetched_at is not None


def test_fetch_exchange_symbol_meta_symbol_not_found():
    session = _FakeSession({"symbols": [{"symbol": "ETHUSDT", "filters": []}]})
    with pytest.raises(BinanceFeedDataError) as exc:
        fetch_exchange_symbol_meta("BTCUSDT", session=session)
    assert exc.value.reason_code == "EXCHANGE_INFO_SYMBOL_NOT_FOUND"


# ------------------------------------------------------------------- optional network smoke

@pytest.mark.skipif(True, reason="live network smoke test -- run manually, not part of default offline suite")
def test_live_smoke_fetch_real_btcusdt_klines():
    import requests as real_requests
    feed = BinanceUSDTMFeed(session=real_requests)
    candles = feed.get_latest_candles("BTCUSDT", "M5", 5)
    assert len(candles) == 5
