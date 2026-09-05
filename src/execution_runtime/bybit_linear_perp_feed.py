"""Bybit V5 linear-perpetual candle adapter -- the read-only BTC production-market data
source for AG_V1_0_3_BYBIT_QUALIFICATION_EXCEPTION_AND_BTC_DAILY_DECISION_V3, mirroring
execution_runtime.binance_usdtm_feed's structure/fail-closed contract exactly (same
CryptoCandleFeed Protocol, same validation philosophy) -- reused as the template rather
than reinventing one. Owner-approved scope (AskUserQuestion, this milestone):
V1_0_3_BYBIT_QUALIFICATION_EXCEPTION = APPROVED_READ_ONLY_ONLY, covering exactly public
market data / registration reconciliation / daily research decisions / immutable
evidence -- no order/wallet/authenticated endpoint anywhere in this module.

Scope: Bybit V5 unified API, category=linear (USDT-margined linear perpetuals), symbol
BTCUSDT only -- matches the FX/BTC manifest's frozen market-data authority (Bybit,
2026-09-03 owner decision) and this repo's existing BTC canonical instrument
(BTCUSDT, CRYPTO_PERP profile in strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml).

Endpoints used (verified against Bybit's official V5 API docs,
https://bybit-exchange.github.io/docs/v5/market/kline and
https://bybit-exchange.github.io/docs/v5/market/instrument, checked this milestone --
not assumed from memory):
  GET /v5/market/kline            category, symbol, interval, limit -- public, no auth
  GET /v5/market/instruments-info category, symbol                  -- public, no auth

Two behavioral differences from Binance's klines, both handled here:
  1. Bybit's kline `result.list` is sorted DESCENDING by startTime (newest first) --
     reversed here to the oldest-first contract CryptoCandleFeed promises.
  2. Bybit's kline rows carry no explicit close time -- only startTime; close time is
     derived as startTime + interval, and the response envelope carries its own
     `retCode`/`retMsg` (0 == success) that must be checked before trusting `result`.

Fail-closed contract: every validation failure raises a typed BybitFeedError subclass --
this module never fabricates, forward-fills, or silently drops a bad candle except the
one specific, expected case of Bybit's own in-progress "current" kline (see
_drop_forming_candle), dropped only when it is provably still open.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, List, Optional, Sequence

import requests

from mt5.symbol_resolver import METADATA_SOURCE_SYNTHETIC_RESEARCH, SymbolMeta
from strategy_engine.session import Candle

API_BASE_URL = "https://api.bybit.com"
KLINE_PATH = "/v5/market/kline"
INSTRUMENTS_INFO_PATH = "/v5/market/instruments-info"

EXCHANGE_ID = "BYBIT_LINEAR_PERP"
CANONICAL_SYMBOL = "BTCUSDT"
EXCHANGE_SYMBOL = "BTCUSDT"  # identical on Bybit linear; kept distinct on the record on
                             # purpose, same rationale as binance_usdtm_feed.py.
CATEGORY = "linear"
SETTLEMENT_ASSET = "USDT"
CONTRACT_TYPE = "LinearPerpetual"

# Bybit V5 kline `interval` strings (bybit-exchange.github.io/docs/v5/market/kline):
# 1,3,5,15,30,60,120,240,360,720,D,W,M -- minutes as bare integers, no "m"/"h" suffix.
_TIMEFRAME_TO_BYBIT_INTERVAL = {"M5": "5", "H1": "60"}
_TIMEFRAME_MS = {"M5": 5 * 60 * 1000, "H1": 60 * 60 * 1000}

# Bybit funds USDT-margined linear perpetuals every 8h (venue-standard, same cadence as
# Binance USDT-M) -- exchange-identity information only, not applied by this module (see
# btc_sweep_research.costs for where funding assumptions are actually used).
FUNDING_INTERVAL_HOURS = 8

# Reject a kline response whose freshest CLOSED candle is older than this many multiples
# of its own timeframe -- fail-closed staleness guard, same threshold as the Binance
# adapter for consistency across both exchange integrations in this repo.
_STALE_MULTIPLE = 3


class BybitFeedError(RuntimeError):
    """Base for every fail-closed rejection this adapter raises. reason_code mirrors the
    repo's existing MarketDataError/BinanceFeedError convention."""

    def __init__(self, reason_code: str, message: str):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code


class BybitFeedRequestError(BybitFeedError):
    """Transport-level failure (HTTP error, timeout, malformed JSON) or a non-zero
    Bybit `retCode` in an otherwise well-formed envelope."""


class BybitFeedDataError(BybitFeedError):
    """The response parsed and retCode==0, but the candle/instrument data itself failed
    a validation rule (non-monotonic timestamps, duplicates, gaps, NaN/None, bad OHLC,
    non-positive price)."""


class BybitFeedStaleData(BybitFeedError):
    """The freshest CLOSED candle is older than _STALE_MULTIPLE x timeframe relative to
    the reference "now" -- the feed is not current."""


@dataclass(frozen=True)
class BybitSymbolMeta:
    """Exchange-identity + contract metadata record for a Bybit linear-perpetual symbol
    -- analogous to binance_usdtm_feed.BinanceSymbolMeta, explicitly tagged as coming
    from THIS adapter (source="DOCUMENTED_CONSTANT_..." or "LIVE_INSTRUMENTS_INFO")."""

    exchange: str
    canonical_symbol: str
    exchange_symbol: str
    settlement_asset: str
    contract_type: str
    tick_size: float
    step_size: float
    price_precision: int
    quantity_precision: int
    min_qty: float
    contract_size: float
    source: str
    fetched_at: Optional[datetime] = None


# Bybit BTCUSDT linear-perpetual public instrument facts, recorded with an explicit
# source/date rather than assumed -- Bybit's official V5 instruments-info reference
# (bybit-exchange.github.io/docs/v5/market/instrument), checked 2026-09-05. These are the
# offline-safe fallback / default; fetch_exchange_symbol_meta() below fetches the live
# values at runtime rather than trusting this blindly forever.
BTCUSDT_TICK_SIZE = 0.1
BTCUSDT_STEP_SIZE = 0.001
BTCUSDT_PRICE_PRECISION = 1
BTCUSDT_QUANTITY_PRECISION = 3
BTCUSDT_MIN_QTY = 0.001
BTCUSDT_CONTRACT_SIZE = 1.0  # 1 contract == 1 BTC for USDT-margined linear perpetuals


def default_symbol_meta(symbol: str = CANONICAL_SYMBOL) -> BybitSymbolMeta:
    """The offline-safe default -- documented constants above, no network call."""
    if symbol != CANONICAL_SYMBOL:
        raise ValueError(f"this adapter is scoped to {CANONICAL_SYMBOL!r} only, got {symbol!r}")
    return BybitSymbolMeta(
        exchange=EXCHANGE_ID, canonical_symbol=CANONICAL_SYMBOL, exchange_symbol=EXCHANGE_SYMBOL,
        settlement_asset=SETTLEMENT_ASSET, contract_type=CONTRACT_TYPE,
        tick_size=BTCUSDT_TICK_SIZE, step_size=BTCUSDT_STEP_SIZE,
        price_precision=BTCUSDT_PRICE_PRECISION, quantity_precision=BTCUSDT_QUANTITY_PRECISION,
        min_qty=BTCUSDT_MIN_QTY, contract_size=BTCUSDT_CONTRACT_SIZE,
        source="DOCUMENTED_CONSTANT_2026_09_05",
    )


def _get_json(http: Any, url: str, params: dict, timeout: float, request_reason: str) -> dict:
    try:
        resp = http.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise BybitFeedRequestError(f"{request_reason}_REQUEST_FAILED", str(exc)) from exc
    if not isinstance(payload, dict):
        raise BybitFeedDataError(f"{request_reason}_MALFORMED_RESPONSE", f"expected a JSON object, got {type(payload)}")
    ret_code = payload.get("retCode")
    if ret_code != 0:
        raise BybitFeedRequestError(
            f"{request_reason}_NON_ZERO_RET_CODE",
            f"retCode={ret_code!r} retMsg={payload.get('retMsg')!r}",
        )
    return payload


def fetch_exchange_symbol_meta(
    symbol: str = CANONICAL_SYMBOL, *, session: Optional[requests.Session] = None, timeout: float = 10.0,
) -> BybitSymbolMeta:
    """Live confirmation/correction of default_symbol_meta() against Bybit's real
    /v5/market/instruments-info. Optional -- callers that want the offline-safe default
    should call default_symbol_meta() instead."""
    if symbol != CANONICAL_SYMBOL:
        raise ValueError(f"this adapter is scoped to {CANONICAL_SYMBOL!r} only, got {symbol!r}")
    http = session or requests
    payload = _get_json(http, f"{API_BASE_URL}{INSTRUMENTS_INFO_PATH}",
                        {"category": CATEGORY, "symbol": symbol}, timeout, "INSTRUMENTS_INFO")

    result = payload.get("result") or {}
    entries = result.get("list")
    if not entries:
        raise BybitFeedDataError("INSTRUMENTS_INFO_EMPTY", f"no instrument entries for {symbol!r}")
    entry = next((e for e in entries if e.get("symbol") == symbol), entries[0])

    price_filter = entry.get("priceFilter") or {}
    lot_filter = entry.get("lotSizeFilter") or {}
    if "tickSize" not in price_filter or "qtyStep" not in lot_filter:
        raise BybitFeedDataError("INSTRUMENTS_INFO_FILTERS_MISSING",
                                 f"priceFilter.tickSize/lotSizeFilter.qtyStep missing for {symbol!r}")

    tick_size = float(price_filter["tickSize"])
    step_size = float(lot_filter["qtyStep"])
    return BybitSymbolMeta(
        exchange=EXCHANGE_ID, canonical_symbol=symbol, exchange_symbol=symbol,
        settlement_asset=entry.get("settleCoin", SETTLEMENT_ASSET),
        contract_type=entry.get("contractType", CONTRACT_TYPE),
        tick_size=tick_size, step_size=step_size,
        price_precision=_decimals(price_filter["tickSize"]), quantity_precision=_decimals(lot_filter["qtyStep"]),
        min_qty=float(lot_filter.get("minOrderQty", BTCUSDT_MIN_QTY)), contract_size=1.0,
        source="LIVE_INSTRUMENTS_INFO", fetched_at=datetime.now(timezone.utc),
    )


def _decimals(value_str: str) -> int:
    """Number of decimal places in a Bybit filter string like "0.10" -> 2. Used only as
    a best-effort precision hint (mirrors binance_usdtm_feed's pricePrecision), never
    load-bearing for validation."""
    if "." not in value_str:
        return 0
    return len(value_str.split(".", 1)[1].rstrip("0")) or 0


def to_symbol_meta(bybit_meta: BybitSymbolMeta, volume_max: float = 1000.0) -> SymbolMeta:
    """Bridges BybitSymbolMeta into the SymbolMeta shape execution.risk.size_position /
    btc_sweep_research actually consume -- same bridging role as binance_usdtm_feed.
    to_symbol_meta, same METADATA_SOURCE_SYNTHETIC_RESEARCH tagging (never
    EXCHANGE_VERIFIED -- that tag's real meaning is FX/MT5 broker-order eligibility,
    which this crypto RESEARCH-domain record must never claim)."""
    return SymbolMeta(
        symbol=bybit_meta.canonical_symbol, tick_size=bybit_meta.tick_size, tick_value=bybit_meta.tick_size,
        contract_size=bybit_meta.contract_size, volume_min=bybit_meta.min_qty, volume_max=volume_max,
        volume_step=bybit_meta.step_size, digits=bybit_meta.price_precision, point=bybit_meta.tick_size,
        metadata_source=METADATA_SOURCE_SYNTHETIC_RESEARCH,
    )


def _to_float(value: Any, field_name: str, row_index: int) -> float:
    if value is None:
        raise BybitFeedDataError("CANDLE_NULL_FIELD", f"row {row_index}: {field_name} is null")
    try:
        f = float(value)
    except (TypeError, ValueError) as exc:
        raise BybitFeedDataError("CANDLE_NON_NUMERIC_FIELD", f"row {row_index}: {field_name}={value!r}") from exc
    if math.isnan(f) or math.isinf(f):
        raise BybitFeedDataError("CANDLE_NAN_FIELD", f"row {row_index}: {field_name}={value!r}")
    return f


def _to_epoch_ms(value: Any, field_name: str, row_index: int) -> int:
    """Normalizes a raw timestamp field to an int epoch-ms without leaking a raw
    ValueError/TypeError/OverflowError -- same convention as binance_usdtm_feed's
    _to_epoch_ms."""
    if value is None:
        raise BybitFeedDataError("CANDLE_NULL_TIMESTAMP", f"row {row_index}: {field_name} is null")
    try:
        ms = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise BybitFeedDataError(
            "CANDLE_MALFORMED_TIMESTAMP", f"row {row_index}: {field_name}={value!r} ({exc})",
        ) from exc
    return ms


def _parse_klines(raw: Sequence[Sequence[Any]], timeframe: str) -> List[dict]:
    """Parses Bybit's raw kline rows (already reversed to oldest-first by the caller --
    see get_latest_candles) into plain dicts, deriving close_time_ms since Bybit's kline
    rows carry no explicit close time -- only [startTime, open, high, low, close,
    volume, turnover]."""
    span_ms = _TIMEFRAME_MS[timeframe]
    parsed = []
    for i, row in enumerate(raw):
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            raise BybitFeedDataError("CANDLE_MALFORMED_ROW", f"row {i}: expected >=6 fields, got {row!r}")
        start_ms, o, h, l, c, v = row[0], row[1], row[2], row[3], row[4], row[5]
        open_ = _to_float(o, "open", i)
        high = _to_float(h, "high", i)
        low = _to_float(l, "low", i)
        close = _to_float(c, "close", i)
        volume = _to_float(v, "volume", i)

        if open_ <= 0 or high <= 0 or low <= 0 or close <= 0:
            raise BybitFeedDataError("CANDLE_NON_POSITIVE_PRICE", f"row {i}: open={open_} high={high} low={low} close={close}")
        if volume < 0:
            raise BybitFeedDataError("CANDLE_NEGATIVE_VOLUME", f"row {i}: volume={volume} (0 is valid; negative is not)")
        if high < max(open_, close, low) or low > min(open_, close, high):
            raise BybitFeedDataError(
                "CANDLE_OHLC_INCONSISTENT",
                f"row {i}: open={open_} high={high} low={low} close={close} violates high>=o,c,l and low<=o,c,h",
            )

        open_time_ms = _to_epoch_ms(start_ms, "startTime", i)
        parsed.append({
            "open_time_ms": open_time_ms, "close_time_ms": open_time_ms + span_ms - 1,
            "open": open_, "high": high, "low": low, "close": close, "volume": volume,
        })
    return parsed


def _validate_series(parsed: Sequence[dict], timeframe: str) -> None:
    expected_spacing_ms = _TIMEFRAME_MS[timeframe]
    seen_open_times = set()
    prev_open_time = None
    for i, row in enumerate(parsed):
        open_time = row["open_time_ms"]
        if open_time in seen_open_times:
            raise BybitFeedDataError("CANDLE_DUPLICATE_TIMESTAMP", f"row {i}: duplicate open_time {open_time}")
        seen_open_times.add(open_time)

        if prev_open_time is not None:
            if open_time <= prev_open_time:
                raise BybitFeedDataError(
                    "CANDLE_NON_MONOTONIC", f"row {i}: open_time {open_time} <= previous {prev_open_time}",
                )
            gap = open_time - prev_open_time
            if gap != expected_spacing_ms:
                raise BybitFeedDataError(
                    "CANDLE_UNEXPECTED_SPACING",
                    f"row {i}: gap {gap}ms between candles != expected {expected_spacing_ms}ms "
                    f"for timeframe {timeframe!r} (missing or extra candle)",
                )
        prev_open_time = open_time


def _drop_forming_candle(parsed: List[dict], now_ms: int) -> List[dict]:
    """Bybit's kline endpoint includes the currently-open (not-yet-closed) candle as its
    most recent row. A candle is still forming if its (derived) close_time has not yet
    passed -- drop it, never treat it as closed. Only ever drops from the END of the
    (already oldest-first-ordered) series."""
    if not parsed:
        return parsed
    if parsed[-1]["close_time_ms"] + 1 > now_ms:
        return parsed[:-1]
    return parsed


def _to_candles(parsed: Sequence[dict], symbol: str, timeframe: str) -> List[Candle]:
    candles = []
    for row in parsed:
        try:
            candle_time = datetime.fromtimestamp(row["open_time_ms"] / 1000.0, tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as exc:
            raise BybitFeedDataError(
                "CANDLE_TIMESTAMP_OUT_OF_RANGE",
                f"{symbol}/{timeframe}: open_time_ms={row['open_time_ms']!r} ({exc})",
            ) from exc
        candles.append(Candle(
            time=candle_time, open=row["open"], high=row["high"], low=row["low"],
            close=row["close"], volume=row["volume"],
        ))
    return candles


class BybitLinearPerpFeed:
    """Concrete implementation of execution_runtime.crypto_feed.CryptoCandleFeed for
    Bybit V5 linear-perpetual futures, BTCUSDT only. get_latest_candles returns
    oldest-first, CLOSED bars only, UTC timestamps, fail-closed on every validation rule
    listed in this module's docstring. Public endpoints only -- no API key, no
    authentication, no order/wallet endpoint anywhere in this class.

    `session`/`clock` are injected (default: real `requests` module / real UTC now) so
    tests can mock the HTTP boundary and pin "now" without any network call -- same
    idiom as execution_runtime.binance_usdtm_feed.BinanceUSDTMFeed."""

    def __init__(
        self,
        session: Optional[Any] = None,
        clock: Optional[Any] = None,
        base_url: str = API_BASE_URL,
        timeout: float = 10.0,
    ):
        self._http = session or requests
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._base_url = base_url
        self._timeout = timeout

    def get_latest_candles(self, symbol: str, timeframe: str, count: int) -> List[Candle]:
        if symbol != CANONICAL_SYMBOL:
            raise ValueError(f"this adapter is scoped to {CANONICAL_SYMBOL!r} only, got {symbol!r}")
        interval = _TIMEFRAME_TO_BYBIT_INTERVAL.get(timeframe)
        if interval is None:
            raise ValueError(f"unsupported timeframe {timeframe!r} -- only {list(_TIMEFRAME_TO_BYBIT_INTERVAL)}")
        if count <= 0:
            raise ValueError(f"count must be positive, got {count}")

        # Fetch one extra candle: Bybit may include the still-forming current candle,
        # which _drop_forming_candle then removes -- fetching count+1 keeps the returned
        # closed-candle count at `count` in the common case.
        params = {"category": CATEGORY, "symbol": symbol, "interval": interval, "limit": count + 1}
        payload = _get_json(self._http, f"{self._base_url}{KLINE_PATH}", params, self._timeout, "KLINES")

        result = payload.get("result") or {}
        raw_desc = result.get("list")
        if raw_desc is None:
            raise BybitFeedDataError("KLINES_MALFORMED_RESPONSE", "no 'result.list' in kline response")
        if not raw_desc:
            raise BybitFeedDataError("KLINES_EMPTY_RESPONSE", f"no candles returned for {symbol}/{timeframe}")

        # Bybit returns klines newest-first (descending startTime) -- reverse to the
        # oldest-first contract CryptoCandleFeed promises before any other processing.
        raw = list(reversed(raw_desc))

        parsed = _parse_klines(raw, timeframe)
        _validate_series(parsed, timeframe)

        now = self._clock()
        now_ms = int(now.astimezone(timezone.utc).timestamp() * 1000)
        parsed = _drop_forming_candle(parsed, now_ms)
        if not parsed:
            raise BybitFeedDataError("KLINES_ALL_CANDLES_FORMING", f"no closed candle available for {symbol}/{timeframe}")

        expected_spacing_ms = _TIMEFRAME_MS[timeframe]
        staleness_ms = now_ms - parsed[-1]["close_time_ms"]
        if staleness_ms > expected_spacing_ms * _STALE_MULTIPLE:
            raise BybitFeedStaleData(
                "KLINES_STALE_DATA",
                f"freshest closed candle for {symbol}/{timeframe} is {staleness_ms / 1000.0:.0f}s old "
                f"(> {_STALE_MULTIPLE}x{expected_spacing_ms // 1000}s threshold)",
            )

        return _to_candles(parsed[-count:], symbol, timeframe)
