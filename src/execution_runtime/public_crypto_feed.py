"""AG V1 D5: public crypto candles with Bybit as primary and Binance as fallback. Read-only.

- Bybit V5 linear-perpetual public klines are the primary source. Binance USDT-M public
  klines are the fallback. There are no API keys, no private endpoints and no order or
  wallet paths.
- BTCUSDT goes through the existing audited adapters unchanged (BybitLinearPerpFeed,
  BinanceUSDTMFeed). ETHUSDT (a symbol of the frozen ST_LIQUIDITY_SWEEP_RETEST_V1@2.0.0
  CRYPTO_PERP profile) runs the same fail-closed pipeline. It reuses each venue module's
  own parser, series validator, forming-candle drop and staleness rule, with the symbol
  as a parameter. Only the symbol scope differs.
- fetch_bundle() fetches every timeframe of one evaluation from ONE venue. If the primary
  fails on any timeframe (HTTP 403/451, network, malformed, stale), the whole bundle is
  refetched from the fallback, so a ticket never mixes venues. The source that served
  the bundle and the primary failure reason are returned for printing on the ticket.
- If both venues fail, PublicCryptoFeedUnavailable carries both reason codes. There is
  never a partial or invented result.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import requests

from execution_runtime import binance_usdtm_feed as BN
from execution_runtime import bybit_linear_perp_feed as BY
from strategy_engine.session import Candle

SUPPORTED_SYMBOLS = ("BTCUSDT", "ETHUSDT")
PRIMARY_SOURCE = BY.EXCHANGE_ID
FALLBACK_SOURCE = BN.EXCHANGE_ID


class PublicCryptoFeedUnavailable(RuntimeError):
    def __init__(self, primary_reason: str, fallback_reason: str):
        super().__init__(f"PRIMARY:{primary_reason};FALLBACK:{fallback_reason}")
        self.primary_reason = primary_reason
        self.fallback_reason = fallback_reason


@dataclass(frozen=True)
class CandleBundle:
    symbol: str
    source: str                          # exchange id that served EVERY timeframe of this bundle
    candles: Dict[str, List[Candle]]
    primary_failure_reason: Optional[str]


def _now_ms(clock) -> int:
    return int(clock().astimezone(timezone.utc).timestamp() * 1000)


def _finish(parsed, now_ms, timeframe, symbol, count, mod, data_err, stale_err) -> List[Candle]:
    mod._validate_series(parsed, timeframe)
    parsed = mod._drop_forming_candle(parsed, now_ms)
    if not parsed:
        raise data_err("KLINES_ALL_CANDLES_FORMING", f"no closed candle available for {symbol}/{timeframe}")
    spacing = mod._TIMEFRAME_MS[timeframe]
    if now_ms - parsed[-1]["close_time_ms"] > spacing * mod._STALE_MULTIPLE:
        raise stale_err("KLINES_STALE_DATA", f"freshest closed candle for {symbol}/{timeframe} is stale")
    return mod._to_candles(parsed[-count:], symbol, timeframe)


def _bybit_scoped(http, clock, base_url, timeout, symbol, timeframe, count) -> List[Candle]:
    interval = BY._TIMEFRAME_TO_BYBIT_INTERVAL.get(timeframe)
    if interval is None or count <= 0:
        raise ValueError(f"unsupported timeframe/count {timeframe!r}/{count}")
    params = {"category": BY.CATEGORY, "symbol": symbol, "interval": interval, "limit": count + 1}
    payload = BY._get_json(http, f"{base_url}{BY.KLINE_PATH}", params, timeout, "KLINES")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise BY.BybitFeedDataError("KLINES_MALFORMED_RESPONSE", "'result' must be an object")
    if result.get("category") != BY.CATEGORY:
        raise BY.BybitFeedDataError("KLINES_CATEGORY_MISMATCH", f"category {result.get('category')!r}")
    if result.get("symbol") != symbol:
        raise BY.BybitFeedDataError("KLINES_SYMBOL_MISMATCH", f"requested {symbol!r}, got {result.get('symbol')!r}")
    raw_desc = result.get("list")
    if not raw_desc:
        raise BY.BybitFeedDataError("KLINES_EMPTY_RESPONSE", f"no candles returned for {symbol}/{timeframe}")
    parsed = BY._parse_klines(list(reversed(raw_desc)), timeframe)
    return _finish(parsed, _now_ms(clock), timeframe, symbol, count, BY, BY.BybitFeedDataError, BY.BybitFeedStaleData)


def _binance_scoped(http, clock, base_url, timeout, symbol, timeframe, count) -> List[Candle]:
    interval = BN._TIMEFRAME_TO_BINANCE_INTERVAL.get(timeframe)
    if interval is None or count <= 0:
        raise ValueError(f"unsupported timeframe/count {timeframe!r}/{count}")
    try:
        resp = http.get(f"{base_url}{BN.KLINES_PATH}", params={"symbol": symbol, "interval": interval,
                                                               "limit": count + 1}, timeout=timeout)
        resp.raise_for_status()
        raw = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise BN.BinanceFeedRequestError("KLINES_REQUEST_FAILED", str(exc)) from exc
    if not isinstance(raw, list) or not raw:
        raise BN.BinanceFeedDataError("KLINES_EMPTY_RESPONSE", f"no candles returned for {symbol}/{timeframe}")
    parsed = BN._parse_klines(raw, timeframe)
    return _finish(parsed, _now_ms(clock), timeframe, symbol, count, BN, BN.BinanceFeedDataError, BN.BinanceFeedStaleData)


class FallbackPublicCryptoFeed:
    """`session`/`clock` are injected so tests mock the HTTP boundary (no network)."""

    def __init__(self, session: Optional[Any] = None, clock: Optional[Callable[[], datetime]] = None,
                 timeout: float = 10.0):
        self._http = session or requests
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._timeout = timeout

    def _primary(self, symbol: str, timeframe: str, count: int) -> List[Candle]:
        if symbol == BY.CANONICAL_SYMBOL:
            return list(BY.BybitLinearPerpFeed(session=self._http, clock=self._clock,
                                               timeout=self._timeout).get_latest_candles(symbol, timeframe, count))
        return _bybit_scoped(self._http, self._clock, BY.API_BASE_URL, self._timeout, symbol, timeframe, count)

    def _fallback(self, symbol: str, timeframe: str, count: int) -> List[Candle]:
        if symbol == BN.CANONICAL_SYMBOL:
            return BN.BinanceUSDTMFeed(session=self._http, clock=self._clock,
                                       timeout=self._timeout).get_latest_candles(symbol, timeframe, count)
        return _binance_scoped(self._http, self._clock, BN.FAPI_BASE_URL, self._timeout, symbol, timeframe, count)

    def fetch_bundle(self, symbol: str, requests_: Sequence[Tuple[str, int]]) -> CandleBundle:
        if symbol not in SUPPORTED_SYMBOLS:
            raise ValueError(f"{symbol!r} not in {SUPPORTED_SYMBOLS}")
        try:
            return CandleBundle(symbol, PRIMARY_SOURCE,
                                {tf: self._primary(symbol, tf, n) for tf, n in requests_}, None)
        except BY.BybitFeedError as primary_exc:
            reason = primary_exc.reason_code
        try:
            return CandleBundle(symbol, FALLBACK_SOURCE,
                                {tf: self._fallback(symbol, tf, n) for tf, n in requests_}, reason)
        except BN.BinanceFeedError as fallback_exc:
            raise PublicCryptoFeedUnavailable(reason, fallback_exc.reason_code) from fallback_exc


class PrefetchedFeed:
    """CryptoCandleFeed over one already-fetched CandleBundle, so a strategy runner cannot
    silently mix venues or refetch mid-evaluation."""

    def __init__(self, bundle: CandleBundle):
        self.bundle = bundle

    def get_latest_candles(self, symbol: str, timeframe: str, count: int) -> List[Candle]:
        if symbol != self.bundle.symbol or timeframe not in self.bundle.candles:
            raise ValueError(f"bundle has no {symbol}/{timeframe}")
        return list(self.bundle.candles[timeframe][-count:])
