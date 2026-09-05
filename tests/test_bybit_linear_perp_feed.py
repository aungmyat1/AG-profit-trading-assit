"""Tests for execution_runtime.bybit_linear_perp_feed.BybitLinearPerpFeed -- fully
offline, no real network call. The HTTP boundary is mocked at the `session.get(...)`
call, same dependency-injection idiom as test_binance_usdtm_feed.py. Bybit-specific
differences exercised here (not present in the Binance adapter): the retCode/retMsg
envelope, the descending-order kline list (reversed by the adapter), and derived
(not provider-supplied) close timestamps.
"""
from __future__ import annotations

import datetime as dt

import pytest

from execution_runtime.bybit_linear_perp_feed import (
    BTCUSDT_STEP_SIZE,
    BTCUSDT_TICK_SIZE,
    BybitFeedDataError,
    BybitFeedRequestError,
    BybitFeedStaleData,
    BybitLinearPerpFeed,
    CANONICAL_SYMBOL,
    default_symbol_meta,
    fetch_exchange_symbol_meta,
)

M5_MS = 5 * 60 * 1000
H1_MS = 60 * 60 * 1000
BASE_OPEN_MS = 1_800_000_000_000  # arbitrary but fixed anchor, ms since epoch


def _row(open_ms, o, h, l, c, v=100.0):
    return [str(open_ms), str(o), str(h), str(l), str(c), str(v), "0"]


def _clean_m5_rows_ascending(n=5, start_ms=BASE_OPEN_MS, price=50000.0):
    """Builds candles oldest-first for test readability, then callers reverse them
    before handing to the fake session -- real Bybit always returns newest-first."""
    rows = []
    for i in range(n):
        t = start_ms + i * M5_MS
        rows.append(_row(t, price, price + 10, price - 10, price + 5))
    return rows


def _envelope(rows_ascending, ret_code=0, ret_msg="OK"):
    return {
        "retCode": ret_code, "retMsg": ret_msg,
        "result": {"category": "linear", "symbol": CANONICAL_SYMBOL, "list": list(reversed(rows_ascending))},
        "time": 0,
    }


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


def _now_after(rows_ascending, span_ms=M5_MS):
    last_open_ms = int(rows_ascending[-1][0])
    last_close_ms = last_open_ms + span_ms - 1
    return lambda: dt.datetime.fromtimestamp((last_close_ms + 1) / 1000.0, tz=dt.timezone.utc)


# ------------------------------------------------------------------------------- happy path

def test_returns_closed_candles_oldest_first_utc_from_descending_provider_order():
    rows = _clean_m5_rows_ascending(5)
    session = _FakeSession(_envelope(rows))
    feed = BybitLinearPerpFeed(session=session, clock=_now_after(rows))
    candles = feed.get_latest_candles(CANONICAL_SYMBOL, "M5", 5)
    assert len(candles) == 5
    assert candles[0].time < candles[-1].time  # oldest-first despite Bybit's descending wire order
    assert candles[0].time.tzinfo == dt.timezone.utc
    assert candles[0].open == 50000.0
    assert candles[0].high == 50010.0


def test_requests_category_linear_and_limit_plus_one():
    rows = _clean_m5_rows_ascending(5)
    session = _FakeSession(_envelope(rows))
    feed = BybitLinearPerpFeed(session=session, clock=_now_after(rows))
    feed.get_latest_candles(CANONICAL_SYMBOL, "M5", 5)
    _, params, _ = session.calls[0]
    assert params["category"] == "linear"
    assert params["limit"] == 6
    assert params["interval"] == "5"
    assert params["symbol"] == CANONICAL_SYMBOL


def test_h1_timeframe_maps_to_interval_60():
    rows = []
    for i in range(3):
        t = BASE_OPEN_MS + i * H1_MS
        rows.append(_row(t, 50000, 50100, 49900, 50050))
    session = _FakeSession(_envelope(rows))
    feed = BybitLinearPerpFeed(session=session, clock=_now_after(rows, span_ms=H1_MS))
    candles = feed.get_latest_candles(CANONICAL_SYMBOL, "H1", 3)
    assert len(candles) == 3
    assert session.calls[0][1]["interval"] == "60"


# ---------------------------------------------------------------------------- envelope/retCode

def test_non_zero_ret_code_raises_request_error():
    payload = {"retCode": 10001, "retMsg": "params error", "result": {}, "time": 0}
    session = _FakeSession(payload)
    feed = BybitLinearPerpFeed(session=session, clock=lambda: dt.datetime.now(dt.timezone.utc))
    with pytest.raises(BybitFeedRequestError) as exc:
        feed.get_latest_candles(CANONICAL_SYMBOL, "M5", 5)
    assert exc.value.reason_code == "KLINES_NON_ZERO_RET_CODE"


def test_missing_result_list_raises_data_error():
    payload = {"retCode": 0, "retMsg": "OK", "result": {}, "time": 0}
    session = _FakeSession(payload)
    feed = BybitLinearPerpFeed(session=session, clock=lambda: dt.datetime.now(dt.timezone.utc))
    with pytest.raises(BybitFeedDataError) as exc:
        feed.get_latest_candles(CANONICAL_SYMBOL, "M5", 5)
    assert exc.value.reason_code == "KLINES_MALFORMED_RESPONSE"


def test_empty_result_list_raises_data_error():
    session = _FakeSession(_envelope([]))
    feed = BybitLinearPerpFeed(session=session, clock=lambda: dt.datetime.now(dt.timezone.utc))
    with pytest.raises(BybitFeedDataError) as exc:
        feed.get_latest_candles(CANONICAL_SYMBOL, "M5", 5)
    assert exc.value.reason_code == "KLINES_EMPTY_RESPONSE"


# ------------------------------------------------------------------------------- forming candle

def test_drops_unfinished_forming_last_candle():
    rows = _clean_m5_rows_ascending(5)
    forming_open_ms = int(rows[-1][0])
    now = lambda: dt.datetime.fromtimestamp((forming_open_ms + 60_000) / 1000.0, tz=dt.timezone.utc)
    session = _FakeSession(_envelope(rows))
    feed = BybitLinearPerpFeed(session=session, clock=now)
    candles = feed.get_latest_candles(CANONICAL_SYMBOL, "M5", 4)
    assert len(candles) == 4
    assert candles[-1].time == dt.datetime.fromtimestamp(int(rows[-2][0]) / 1000.0, tz=dt.timezone.utc)


def test_all_candles_forming_raises():
    rows = _clean_m5_rows_ascending(1)
    now = lambda: dt.datetime.fromtimestamp(int(rows[0][0]) / 1000.0, tz=dt.timezone.utc)
    session = _FakeSession(_envelope(rows))
    feed = BybitLinearPerpFeed(session=session, clock=now)
    with pytest.raises(BybitFeedDataError) as exc:
        feed.get_latest_candles(CANONICAL_SYMBOL, "M5", 1)
    assert exc.value.reason_code == "KLINES_ALL_CANDLES_FORMING"


# --------------------------------------------------------------------------------- staleness

def test_stale_data_rejected():
    rows = _clean_m5_rows_ascending(3)
    last_open_ms = int(rows[-1][0])
    far_future = lambda: dt.datetime.fromtimestamp((last_open_ms + M5_MS * 10) / 1000.0, tz=dt.timezone.utc)
    session = _FakeSession(_envelope(rows))
    feed = BybitLinearPerpFeed(session=session, clock=far_future)
    with pytest.raises(BybitFeedStaleData) as exc:
        feed.get_latest_candles(CANONICAL_SYMBOL, "M5", 3)
    assert exc.value.reason_code == "KLINES_STALE_DATA"


# --------------------------------------------------------------------------------- monotonicity

def test_non_monotonic_timestamps_rejected():
    rows = _clean_m5_rows_ascending(3)
    rows[2][0] = rows[0][0]  # third row's open_time goes backward
    session = _FakeSession(_envelope(rows))
    feed = BybitLinearPerpFeed(session=session, clock=_now_after(rows))
    with pytest.raises(BybitFeedDataError) as exc:
        feed.get_latest_candles(CANONICAL_SYMBOL, "M5", 3)
    assert exc.value.reason_code in ("CANDLE_NON_MONOTONIC", "CANDLE_DUPLICATE_TIMESTAMP")


def test_duplicate_timestamp_rejected():
    rows = _clean_m5_rows_ascending(3)
    dup = _row(rows[1][0], 50000, 50010, 49990, 50005)
    rows.insert(2, dup)
    session = _FakeSession(_envelope(rows))
    feed = BybitLinearPerpFeed(session=session, clock=_now_after(rows))
    with pytest.raises(BybitFeedDataError) as exc:
        feed.get_latest_candles(CANONICAL_SYMBOL, "M5", 4)
    assert exc.value.reason_code == "CANDLE_DUPLICATE_TIMESTAMP"


def test_missing_candle_gap_rejected():
    rows = _clean_m5_rows_ascending(3)
    rows[2][0] = str(int(rows[2][0]) + M5_MS)  # skip one bar
    session = _FakeSession(_envelope(rows))
    feed = BybitLinearPerpFeed(session=session, clock=_now_after(rows))
    with pytest.raises(BybitFeedDataError) as exc:
        feed.get_latest_candles(CANONICAL_SYMBOL, "M5", 3)
    assert exc.value.reason_code == "CANDLE_UNEXPECTED_SPACING"


# ------------------------------------------------------------------------------- OHLC / NaN

def test_ohlc_inconsistent_high_rejected():
    rows = _clean_m5_rows_ascending(1)
    rows[0][2] = "100"  # high below open/close
    session = _FakeSession(_envelope(rows))
    feed = BybitLinearPerpFeed(session=session, clock=_now_after(rows))
    with pytest.raises(BybitFeedDataError) as exc:
        feed.get_latest_candles(CANONICAL_SYMBOL, "M5", 1)
    assert exc.value.reason_code == "CANDLE_OHLC_INCONSISTENT"


def test_non_positive_price_rejected():
    rows = _clean_m5_rows_ascending(1)
    rows[0][1] = "0"
    session = _FakeSession(_envelope(rows))
    feed = BybitLinearPerpFeed(session=session, clock=_now_after(rows))
    with pytest.raises(BybitFeedDataError) as exc:
        feed.get_latest_candles(CANONICAL_SYMBOL, "M5", 1)
    assert exc.value.reason_code == "CANDLE_NON_POSITIVE_PRICE"


def test_negative_volume_rejected():
    rows = _clean_m5_rows_ascending(1)
    rows[0][5] = "-1"
    session = _FakeSession(_envelope(rows))
    feed = BybitLinearPerpFeed(session=session, clock=_now_after(rows))
    with pytest.raises(BybitFeedDataError) as exc:
        feed.get_latest_candles(CANONICAL_SYMBOL, "M5", 1)
    assert exc.value.reason_code == "CANDLE_NEGATIVE_VOLUME"


def test_nan_field_rejected():
    rows = _clean_m5_rows_ascending(1)
    rows[0][1] = "nan"
    session = _FakeSession(_envelope(rows))
    feed = BybitLinearPerpFeed(session=session, clock=_now_after(rows))
    with pytest.raises(BybitFeedDataError) as exc:
        feed.get_latest_candles(CANONICAL_SYMBOL, "M5", 1)
    assert exc.value.reason_code == "CANDLE_NAN_FIELD"


def test_non_numeric_field_rejected():
    rows = _clean_m5_rows_ascending(1)
    rows[0][1] = "not-a-number"
    session = _FakeSession(_envelope(rows))
    feed = BybitLinearPerpFeed(session=session, clock=_now_after(rows))
    with pytest.raises(BybitFeedDataError) as exc:
        feed.get_latest_candles(CANONICAL_SYMBOL, "M5", 1)
    assert exc.value.reason_code == "CANDLE_NON_NUMERIC_FIELD"


def test_symbol_scope_enforced():
    session = _FakeSession(_envelope(_clean_m5_rows_ascending(1)))
    feed = BybitLinearPerpFeed(session=session, clock=lambda: dt.datetime.now(dt.timezone.utc))
    with pytest.raises(ValueError):
        feed.get_latest_candles("ETHUSDT", "M5", 1)


def test_unsupported_timeframe_rejected():
    session = _FakeSession(_envelope(_clean_m5_rows_ascending(1)))
    feed = BybitLinearPerpFeed(session=session, clock=lambda: dt.datetime.now(dt.timezone.utc))
    with pytest.raises(ValueError):
        feed.get_latest_candles(CANONICAL_SYMBOL, "M15", 1)


# ------------------------------------------------------------------------- no auth / public only

def test_no_authentication_headers_or_credentials_sent():
    """The adapter must never construct or send any API key/secret/signature -- proves
    it structurally: get_latest_candles never receives or uses headers/auth kwargs."""
    rows = _clean_m5_rows_ascending(1)
    session = _FakeSession(_envelope(rows))
    feed = BybitLinearPerpFeed(session=session, clock=_now_after(rows))
    feed.get_latest_candles(CANONICAL_SYMBOL, "M5", 1)
    url, params, _ = session.calls[0]
    assert "sign" not in params and "api_key" not in params and "timestamp" not in params
    assert "/v5/market/kline" in url


# --------------------------------------------------------------------------- symbol metadata

def test_default_symbol_meta_offline_no_network():
    meta = default_symbol_meta(CANONICAL_SYMBOL)
    assert meta.tick_size == BTCUSDT_TICK_SIZE
    assert meta.step_size == BTCUSDT_STEP_SIZE
    assert meta.source.startswith("DOCUMENTED_CONSTANT")


def test_fetch_exchange_symbol_meta_parses_live_shape():
    payload = {
        "retCode": 0, "retMsg": "OK",
        "result": {"category": "linear", "list": [{
            "symbol": "BTCUSDT", "contractType": "LinearPerpetual", "settleCoin": "USDT",
            "priceFilter": {"tickSize": "0.10"},
            "lotSizeFilter": {"qtyStep": "0.001", "minOrderQty": "0.001"},
        }]},
        "time": 0,
    }
    session = _FakeSession(payload)
    meta = fetch_exchange_symbol_meta(CANONICAL_SYMBOL, session=session)
    assert meta.tick_size == 0.1
    assert meta.step_size == 0.001
    assert meta.source == "LIVE_INSTRUMENTS_INFO"
    assert meta.contract_type == "LinearPerpetual"


def test_fetch_exchange_symbol_meta_missing_filters_raises():
    payload = {"retCode": 0, "retMsg": "OK",
              "result": {"list": [{"symbol": "BTCUSDT"}]}, "time": 0}
    session = _FakeSession(payload)
    with pytest.raises(BybitFeedDataError) as exc:
        fetch_exchange_symbol_meta(CANONICAL_SYMBOL, session=session)
    assert exc.value.reason_code == "INSTRUMENTS_INFO_FILTERS_MISSING"


def test_wrong_symbol_scope_rejected_for_meta_fetch():
    with pytest.raises(ValueError):
        fetch_exchange_symbol_meta("ETHUSDT")
