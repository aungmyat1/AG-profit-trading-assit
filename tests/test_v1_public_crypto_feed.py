"""AG V1 T6/T8: Bybit-primary / Binance-fallback public crypto feed. The HTTP boundary is
mocked; there are no network calls. Fixture timestamps end before 2025-09-14."""
from __future__ import annotations

import datetime as dt

import pytest
import requests

from execution_runtime.public_crypto_feed import (
    FALLBACK_SOURCE, PRIMARY_SOURCE, FallbackPublicCryptoFeed, PrefetchedFeed, PublicCryptoFeedUnavailable,
)

M5_MS, H1_MS = 5 * 60 * 1000, 60 * 60 * 1000
END = int(dt.datetime(2025, 9, 1, 12, 0, tzinfo=dt.timezone.utc).timestamp() * 1000)  # every series ends here
N = 6


def _bybit_payload(symbol, span, price):
    start = END - N * span
    rows = [[str(start + i * span), str(price), str(price + 1), str(price - 1), str(price + 0.5), "10", "0"]
            for i in range(N)]
    return {"retCode": 0, "retMsg": "OK", "result": {"category": "linear", "symbol": symbol, "list": rows[::-1]}}


def _binance_payload(span, price):
    start = END - N * span
    return [[start + i * span, str(price), str(price + 1), str(price - 1), str(price + 0.5), "10",
             start + i * span + span - 1, "0", 1, "0", "0", "0"] for i in range(N)]


class _Resp:
    def __init__(self, payload, status):
        self.payload, self.status = payload, status

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError(f"{self.status} Client Error")

    def json(self):
        return self.payload


class _Router:
    """Routes by venue host. `bybit_status`/`binance_status` simulate e.g. 403/451."""

    def __init__(self, symbol, bybit_status=200, binance_status=200, bybit_fail_tf=None):
        self.symbol, self.bybit_status, self.binance_status, self.bybit_fail_tf = symbol, bybit_status, binance_status, bybit_fail_tf
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(url)
        if "bybit" in url:
            span = M5_MS if params["interval"] == "5" else H1_MS
            status = 403 if params["interval"] == self.bybit_fail_tf else self.bybit_status
            return _Resp(_bybit_payload(params["symbol"], span, 100.0), status)
        span = M5_MS if params["interval"] == "5m" else H1_MS
        return _Resp(_binance_payload(span, 100.0), self.binance_status)


def _m5_clock():
    return dt.datetime.fromtimestamp(END / 1000, tz=dt.timezone.utc)


@pytest.mark.parametrize("symbol", ["BTCUSDT", "ETHUSDT"])
def test_primary_bybit_serves_bundle_and_source_is_recorded(symbol):
    feed = FallbackPublicCryptoFeed(session=_Router(symbol), clock=_m5_clock)
    b = feed.fetch_bundle(symbol, [("M5", 5)])
    assert b.source == PRIMARY_SOURCE == "BYBIT_LINEAR_PERP" and b.primary_failure_reason is None
    assert len(b.candles["M5"]) == 5 and all(c.time.tzinfo for c in b.candles["M5"])


@pytest.mark.parametrize("symbol", ["BTCUSDT", "ETHUSDT"])
def test_http_403_on_bybit_falls_back_to_binance(symbol):
    feed = FallbackPublicCryptoFeed(session=_Router(symbol, bybit_status=403), clock=_m5_clock)
    b = feed.fetch_bundle(symbol, [("M5", 5)])
    assert b.source == FALLBACK_SOURCE == "BINANCE_USDT_M_PERP"
    assert b.primary_failure_reason == "KLINES_REQUEST_FAILED"


def test_partial_primary_failure_refetches_whole_bundle_from_fallback_no_mixing():
    router = _Router("ETHUSDT", bybit_fail_tf="60")   # Bybit M5 fine, Bybit H1 -> 403
    feed = FallbackPublicCryptoFeed(session=router, clock=_m5_clock)
    b = feed.fetch_bundle("ETHUSDT", [("M5", 5), ("H1", 5)])
    assert b.source == FALLBACK_SOURCE and set(b.candles) == {"M5", "H1"}
    binance_calls = [u for u in router.calls if "binance" in u]
    assert len(binance_calls) == 2          # BOTH timeframes refetched from the fallback venue


def test_both_venues_fail_closed_with_both_reasons():
    feed = FallbackPublicCryptoFeed(session=_Router("BTCUSDT", bybit_status=403, binance_status=451), clock=_m5_clock)
    with pytest.raises(PublicCryptoFeedUnavailable) as exc:
        feed.fetch_bundle("BTCUSDT", [("M5", 5)])
    assert exc.value.primary_reason == "KLINES_REQUEST_FAILED"
    assert exc.value.fallback_reason == "KLINES_REQUEST_FAILED"


def test_stale_primary_falls_back_and_stale_fallback_fails_closed():
    late = lambda: _m5_clock() + dt.timedelta(hours=2)  # noqa: E731
    feed = FallbackPublicCryptoFeed(session=_Router("ETHUSDT"), clock=late)
    with pytest.raises(PublicCryptoFeedUnavailable) as exc:
        feed.fetch_bundle("ETHUSDT", [("M5", 5)])
    assert exc.value.primary_reason == "KLINES_STALE_DATA" and exc.value.fallback_reason == "KLINES_STALE_DATA"


def test_bybit_symbol_mismatch_is_rejected_then_fallback():
    class Mismatch(_Router):
        def get(self, url, params=None, timeout=None):
            r = super().get(url, params, timeout)
            if "bybit" in url:
                r.payload["result"]["symbol"] = "BTCUSDT"
            return r
    b = FallbackPublicCryptoFeed(session=Mismatch("ETHUSDT"), clock=_m5_clock).fetch_bundle("ETHUSDT", [("M5", 5)])
    assert b.source == FALLBACK_SOURCE and b.primary_failure_reason == "KLINES_SYMBOL_MISMATCH"


def test_unsupported_symbol_and_prefetched_feed_scope():
    with pytest.raises(ValueError):
        FallbackPublicCryptoFeed(session=_Router("SOLUSDT")).fetch_bundle("SOLUSDT", [("M5", 5)])
    b = FallbackPublicCryptoFeed(session=_Router("BTCUSDT"), clock=_m5_clock).fetch_bundle("BTCUSDT", [("M5", 5)])
    pf = PrefetchedFeed(b)
    assert len(pf.get_latest_candles("BTCUSDT", "M5", 3)) == 3
    with pytest.raises(ValueError):
        pf.get_latest_candles("ETHUSDT", "M5", 3)


def test_feed_module_uses_public_endpoints_only():
    import inspect

    import execution_runtime.public_crypto_feed as mod
    src = inspect.getsource(mod)
    for forbidden in ("api_key", "X-BAPI-SIGN", "signature", "/v5/order", "/fapi/v1/order", "/v5/position", "secret"):
        assert forbidden not in src
