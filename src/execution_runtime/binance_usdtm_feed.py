"""Binance USDT-M perpetual futures candle adapter -- the FIRST real exchange integration
in this repo (audited before adding: grep for binance/bybit/ccxt/klines/BTCUSDT across the
repo found nothing outside strategy_engine.sweep_retest's own test fixtures and
crypto_symbols.py's synthetic tick-size table; execution_runtime/crypto_feed.py's own
docstring explicitly says its CryptoCandleFeed Protocol is "exactly the shape a future
concrete adapter should implement" and that the runtime's crypto path stays disabled
until one exists -- this module is that adapter).

Scope: Binance USDT-M perpetual futures, symbol BTCUSDT only (user's explicit choice --
do not add ETHUSDT or spot BTCUSDT, do not use another exchange).

Transport choice: plain `requests` against Binance's public REST endpoints
(https://fapi.binance.com/fapi/v1/klines, /fapi/v1/exchangeInfo), NOT ccxt. `requests` is
already a resolvable dependency in this environment and is the simpler, more directly
testable boundary (a single `requests.get` call to mock), whereas ccxt wraps this in a
much larger surface (dozens of exchange-specific quirks, its own exception hierarchy, an
undeclared dependency not yet in requirements.txt) for no behavior this task needs beyond
"GET klines, GET exchangeInfo". ccxt IS already importable in this environment (`pip show
ccxt` succeeded, v4.5.65) but is not listed in requirements.txt/pyproject.toml, so relying
on it would be an undeclared, unverified dependency; `requests` (2.34.2) already is one
(post_asian_pilot's own MT5 stack pulls it transitively and it resolves cleanly here).

Fail-closed contract (spec): every validation failure raises a typed BinanceFeedError
subclass -- this module NEVER fabricates, forward-fills, or silently drops a bad candle
except the one specific, expected case of Binance's own in-progress "current" kline (see
_drop_forming_candle), which is dropped, not fabricated-around, and only when it is
provably still open (close_time in the future relative to `now`).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

import requests

from mt5.symbol_resolver import METADATA_SOURCE_SYNTHETIC_RESEARCH, SymbolMeta
from strategy_engine.session import Candle

FAPI_BASE_URL = "https://fapi.binance.com"
KLINES_PATH = "/fapi/v1/klines"
EXCHANGE_INFO_PATH = "/fapi/v1/exchangeInfo"

EXCHANGE_ID = "BINANCE_USDT_M_PERP"
CANONICAL_SYMBOL = "BTCUSDT"
EXCHANGE_SYMBOL = "BTCUSDT"  # identical on Binance USDT-M; kept distinct on the record on
                             # purpose (spec: "record exchange identity + canonical/
                             # exchange symbol ... explicitly") in case a future symbol
                             # ever needs a translation layer.
SETTLEMENT_ASSET = "USDT"
CONTRACT_TYPE = "PERPETUAL"

# Binance interval strings (fapi klines `interval` param).
_TIMEFRAME_TO_BINANCE_INTERVAL = {"M5": "5m", "H1": "1h"}
_TIMEFRAME_MS = {"M5": 5 * 60 * 1000, "H1": 60 * 60 * 1000}

# Binance funds USDT-M perpetuals every 8h at 00:00/08:00/16:00 UTC -- Binance's own public
# "Funding Rate History" / "Funding Fee" documentation (fapi.binance.com docs, funding
# section), cross-checked 2026-09-02: standard funding interval is 8 hours, anchored to
# UTC midnight. This module does not itself apply funding (see btc_sweep_research.costs);
# it only exposes the constant since it is exchange-identity information, same audit trail
# as the tick size below.
FUNDING_INTERVAL_HOURS = 8

# Binance BTCUSDT-PERP public exchange-info facts, recorded here with an explicit
# source/date rather than assumed. Confirmed against crypto_symbols.py's own tick size
# (0.1) -- MATCHES; step size (quantity precision) is 0.001 BTC, ALSO matches
# crypto_symbols.py's default volume_step=0.001. Source: Binance USDT-M Futures public
# GET /fapi/v1/exchangeInfo for symbol=BTCUSDT, PRICE_FILTER.tickSize and
# LOT_SIZE.stepSize, as documented in Binance's public Futures API reference (checked
# 2026-09-02; the live values can also be fetched at runtime via fetch_exchange_symbol_meta
# below rather than trusted blindly -- this constant is the offline-safe fallback / default
# used when no live fetch is performed).
BTCUSDT_TICK_SIZE = 0.1
BTCUSDT_STEP_SIZE = 0.001
BTCUSDT_PRICE_PRECISION = 1
BTCUSDT_QUANTITY_PRECISION = 3
BTCUSDT_MIN_QTY = 0.001
BTCUSDT_CONTRACT_SIZE = 1.0  # 1 contract == 1 BTC for USDT-M linear perpetuals

# Reject a klines response whose freshest CLOSED candle is older than this many multiples
# of its own timeframe -- fail-closed staleness guard (spec: "stale data").
_STALE_MULTIPLE = 3


class BinanceFeedError(RuntimeError):
    """Base for every fail-closed rejection this adapter raises. reason_code mirrors the
    repo's existing MarketDataError convention (mt5.market_data.MarketDataError)."""

    def __init__(self, reason_code: str, message: str):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code


class BinanceFeedRequestError(BinanceFeedError):
    """Transport-level failure (HTTP error, timeout, malformed JSON)."""


class BinanceFeedDataError(BinanceFeedError):
    """The response parsed, but the candle data itself failed a validation rule
    (non-monotonic timestamps, duplicates, gaps, NaN/None, bad OHLC, non-positive price)."""


class BinanceFeedStaleData(BinanceFeedError):
    """The freshest CLOSED candle is older than _STALE_MULTIPLE x timeframe relative to
    the reference "now" -- the feed is not current."""


@dataclass(frozen=True)
class BinanceSymbolMeta:
    """Exchange-identity + contract metadata record for a Binance USDT-M perpetual symbol
    -- analogous to crypto_symbols.py's synthetic crypto_symbol_meta(), but explicitly
    tagged as coming from THIS adapter (source="BINANCE_USDT_M_PERP_ADAPTER_V1", either the
    hardcoded, documented-source constants above, or a live /fapi/v1/exchangeInfo fetch --
    see `source` and `fetched_at`)."""

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
    source: str  # "DOCUMENTED_CONSTANT_2026_09_02" or "LIVE_EXCHANGE_INFO"
    fetched_at: Optional[datetime] = None


def default_symbol_meta(symbol: str = CANONICAL_SYMBOL) -> BinanceSymbolMeta:
    """The offline-safe default -- documented constants above, no network call."""
    if symbol != CANONICAL_SYMBOL:
        raise ValueError(f"this adapter is scoped to {CANONICAL_SYMBOL!r} only, got {symbol!r}")
    return BinanceSymbolMeta(
        exchange=EXCHANGE_ID, canonical_symbol=CANONICAL_SYMBOL, exchange_symbol=EXCHANGE_SYMBOL,
        settlement_asset=SETTLEMENT_ASSET, contract_type=CONTRACT_TYPE,
        tick_size=BTCUSDT_TICK_SIZE, step_size=BTCUSDT_STEP_SIZE,
        price_precision=BTCUSDT_PRICE_PRECISION, quantity_precision=BTCUSDT_QUANTITY_PRECISION,
        min_qty=BTCUSDT_MIN_QTY, contract_size=BTCUSDT_CONTRACT_SIZE,
        source="DOCUMENTED_CONSTANT_2026_09_02",
    )


def fetch_exchange_symbol_meta(
    symbol: str = CANONICAL_SYMBOL, *, session: Optional[requests.Session] = None, timeout: float = 10.0,
) -> BinanceSymbolMeta:
    """Live confirmation/correction of default_symbol_meta() against Binance's real
    /fapi/v1/exchangeInfo. Optional -- callers that want the offline-safe default should
    call default_symbol_meta() instead; this exists so the tick/step-size assumption above
    can be verified against the live venue rather than trusted blindly forever (spec:
    "verify, don't assume")."""
    if symbol != CANONICAL_SYMBOL:
        raise ValueError(f"this adapter is scoped to {CANONICAL_SYMBOL!r} only, got {symbol!r}")
    http = session or requests
    try:
        resp = http.get(f"{FAPI_BASE_URL}{EXCHANGE_INFO_PATH}", timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise BinanceFeedRequestError("EXCHANGE_INFO_REQUEST_FAILED", str(exc)) from exc

    symbols = payload.get("symbols") if isinstance(payload, dict) else None
    if not symbols:
        raise BinanceFeedDataError("EXCHANGE_INFO_MALFORMED", "no 'symbols' array in exchangeInfo response")
    entry = next((s for s in symbols if s.get("symbol") == symbol), None)
    if entry is None:
        raise BinanceFeedDataError("EXCHANGE_INFO_SYMBOL_NOT_FOUND", f"{symbol!r} not present in exchangeInfo")

    filters = {f.get("filterType"): f for f in entry.get("filters", [])}
    price_filter = filters.get("PRICE_FILTER")
    lot_filter = filters.get("LOT_SIZE")
    if price_filter is None or lot_filter is None:
        raise BinanceFeedDataError("EXCHANGE_INFO_FILTERS_MISSING", f"PRICE_FILTER/LOT_SIZE missing for {symbol!r}")

    return BinanceSymbolMeta(
        exchange=EXCHANGE_ID, canonical_symbol=symbol, exchange_symbol=symbol,
        settlement_asset=entry.get("marginAsset", SETTLEMENT_ASSET), contract_type=entry.get("contractType", CONTRACT_TYPE),
        tick_size=float(price_filter["tickSize"]), step_size=float(lot_filter["stepSize"]),
        price_precision=int(entry.get("pricePrecision", BTCUSDT_PRICE_PRECISION)),
        quantity_precision=int(entry.get("quantityPrecision", BTCUSDT_QUANTITY_PRECISION)),
        min_qty=float(lot_filter["minQty"]), contract_size=1.0,
        source="LIVE_EXCHANGE_INFO", fetched_at=datetime.now(timezone.utc),
    )


def to_symbol_meta(binance_meta: BinanceSymbolMeta, volume_max: float = 1000.0) -> SymbolMeta:
    """Bridges BinanceSymbolMeta (this adapter's own exchange-identity record) into the
    SymbolMeta shape execution.risk.size_position / btc_sweep_research actually consume --
    using THIS adapter's tick_size/step_size/min_qty/contract_size as the authority, not
    strategy_engine.sweep_retest.crypto_symbols.crypto_symbol_meta()'s hardcoded synthetic
    defaults (spec: "for fields that are exchange-specific, prefer the verified Binance
    exchangeInfo metadata ... do not silently continue using synthetic metadata where real
    Binance metadata is already available"). Still tagged METADATA_SOURCE_SYNTHETIC_RESEARCH
    (never METADATA_SOURCE_EXCHANGE_VERIFIED): that tag's real meaning in this repo is
    execution.adapter.require_exchange_verified_metadata()'s gate for FX/MT5 broker-order
    eligibility, which this crypto RESEARCH-domain record must never claim regardless of
    whether the underlying numbers came from a live Binance fetch or the offline-safe
    documented default -- see this module's own EXCHANGE/CONTRACT constants' docstrings."""
    return SymbolMeta(
        symbol=binance_meta.canonical_symbol, tick_size=binance_meta.tick_size, tick_value=binance_meta.tick_size,
        contract_size=binance_meta.contract_size, volume_min=binance_meta.min_qty, volume_max=volume_max,
        volume_step=binance_meta.step_size, digits=binance_meta.price_precision, point=binance_meta.tick_size,
        metadata_source=METADATA_SOURCE_SYNTHETIC_RESEARCH,
    )


def _to_float(value: Any, field_name: str, row_index: int) -> float:
    if value is None:
        raise BinanceFeedDataError("CANDLE_NULL_FIELD", f"row {row_index}: {field_name} is null")
    try:
        f = float(value)
    except (TypeError, ValueError) as exc:
        raise BinanceFeedDataError("CANDLE_NON_NUMERIC_FIELD", f"row {row_index}: {field_name}={value!r}") from exc
    if math.isnan(f) or math.isinf(f):
        raise BinanceFeedDataError("CANDLE_NAN_FIELD", f"row {row_index}: {field_name}={value!r}")
    return f


def _to_epoch_ms(value: Any, field_name: str, row_index: int) -> int:
    """Normalizes a raw timestamp field to an int epoch-ms, never leaking a raw
    ValueError/TypeError/OverflowError from int()/float() -- every malformed timestamp
    (non-numeric, None, absurdly large/NaN-ish) fails closed as a typed
    BinanceFeedDataError carrying the symbol/timeframe context the caller adds (spec:
    "malformed exchange timestamps must not leak arbitrary low-level exceptions")."""
    if value is None:
        raise BinanceFeedDataError("CANDLE_NULL_TIMESTAMP", f"row {row_index}: {field_name} is null")
    try:
        ms = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise BinanceFeedDataError(
            "CANDLE_MALFORMED_TIMESTAMP", f"row {row_index}: {field_name}={value!r} ({exc})",
        ) from exc
    return ms


def _parse_klines(raw: Sequence[Sequence[Any]], timeframe: str) -> List[dict]:
    """Parses Binance's raw kline rows into plain dicts (open_time_ms, close_time_ms,
    open/high/low/close, volume) and validates every fail-closed rule EXCEPT the
    forming-candle drop (handled separately, see _drop_forming_candle) and the
    monotonic/duplicate/gap checks across the whole series (handled separately, see
    _validate_series) -- kept as small single-purpose passes rather than one large
    function, matching this package's existing style (sweep.py/mss.py/retest.py each do
    one check)."""
    parsed = []
    for i, row in enumerate(raw):
        if not isinstance(row, (list, tuple)) or len(row) < 7:
            raise BinanceFeedDataError("CANDLE_MALFORMED_ROW", f"row {i}: expected >=7 fields, got {row!r}")
        open_time_ms, o, h, l, c, v, close_time_ms = row[0], row[1], row[2], row[3], row[4], row[5], row[6]
        open_ = _to_float(o, "open", i)
        high = _to_float(h, "high", i)
        low = _to_float(l, "low", i)
        close = _to_float(c, "close", i)
        volume = _to_float(v, "volume", i)

        if open_ <= 0 or high <= 0 or low <= 0 or close <= 0:
            raise BinanceFeedDataError("CANDLE_NON_POSITIVE_PRICE", f"row {i}: open={open_} high={high} low={low} close={close}")
        if volume < 0:
            raise BinanceFeedDataError("CANDLE_NEGATIVE_VOLUME", f"row {i}: volume={volume} (0 is valid -- a genuinely quiet bar; negative is not)")
        if high < max(open_, close, low) or low > min(open_, close, high):
            raise BinanceFeedDataError(
                "CANDLE_OHLC_INCONSISTENT",
                f"row {i}: open={open_} high={high} low={low} close={close} violates high>=o,c,l and low<=o,c,h",
            )

        parsed.append({
            "open_time_ms": _to_epoch_ms(open_time_ms, "open_time", i),
            "close_time_ms": _to_epoch_ms(close_time_ms, "close_time", i),
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
            raise BinanceFeedDataError("CANDLE_DUPLICATE_TIMESTAMP", f"row {i}: duplicate open_time {open_time}")
        seen_open_times.add(open_time)

        if prev_open_time is not None:
            if open_time <= prev_open_time:
                raise BinanceFeedDataError(
                    "CANDLE_NON_MONOTONIC", f"row {i}: open_time {open_time} <= previous {prev_open_time}",
                )
            gap = open_time - prev_open_time
            if gap != expected_spacing_ms:
                raise BinanceFeedDataError(
                    "CANDLE_UNEXPECTED_SPACING",
                    f"row {i}: gap {gap}ms between candles != expected {expected_spacing_ms}ms "
                    f"for timeframe {timeframe!r} (missing or extra candle)",
                )
        prev_open_time = open_time


def _drop_forming_candle(parsed: List[dict], now_ms: int) -> List[dict]:
    """Binance's klines endpoint includes the currently-open (not-yet-closed) candle as
    its last row when the query range reaches "now". A candle is still forming if its
    close_time has not yet passed -- drop it (never treat it as a closed bar), rather than
    raising, since this is Binance's normal/expected response shape, not a data anomaly.
    Only ever drops from the END of the series (the forming candle, by construction, is
    always the most recent one)."""
    if not parsed:
        return parsed
    if parsed[-1]["close_time_ms"] + 1 > now_ms:  # Binance close_time is inclusive-end - 1ms
        return parsed[:-1]
    return parsed


def _to_candles(parsed: Sequence[dict], symbol: str, timeframe: str) -> List[Candle]:
    candles = []
    for row in parsed:
        try:
            candle_time = datetime.fromtimestamp(row["open_time_ms"] / 1000.0, tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as exc:
            # Same fail-closed normalization as _to_epoch_ms -- a numerically valid but
            # out-of-range epoch-ms (e.g. an absurdly large value) must not leak a raw
            # platform exception (spec: "must not leak arbitrary low-level exceptions").
            raise BinanceFeedDataError(
                "CANDLE_TIMESTAMP_OUT_OF_RANGE",
                f"{symbol}/{timeframe}: open_time_ms={row['open_time_ms']!r} ({exc})",
            ) from exc
        candles.append(Candle(
            time=candle_time, open=row["open"], high=row["high"], low=row["low"],
            close=row["close"], volume=row["volume"],
        ))
    return candles


class BinanceUSDTMFeed:
    """Concrete implementation of execution_runtime.crypto_feed.CryptoCandleFeed for
    Binance USDT-M perpetual futures, BTCUSDT only. get_latest_candles returns
    oldest-first, CLOSED bars only (the in-progress candle is dropped, never returned --
    see _drop_forming_candle), UTC timestamps, fail-closed on every validation rule listed
    in this module's docstring.

    `session`/`clock` are injected (default: real `requests` module / real UTC now) purely
    so tests can mock the HTTP boundary and pin "now" without any network call -- same
    dependency-injection idiom execution_runtime/cycle.py already uses for candle/equity
    fetchers."""

    def __init__(
        self,
        session: Optional[Any] = None,
        clock: Optional[Any] = None,
        base_url: str = FAPI_BASE_URL,
        timeout: float = 10.0,
    ):
        self._http = session or requests
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._base_url = base_url
        self._timeout = timeout

    def get_latest_candles(self, symbol: str, timeframe: str, count: int) -> List[Candle]:
        if symbol != CANONICAL_SYMBOL:
            raise ValueError(f"this adapter is scoped to {CANONICAL_SYMBOL!r} only, got {symbol!r}")
        interval = _TIMEFRAME_TO_BINANCE_INTERVAL.get(timeframe)
        if interval is None:
            raise ValueError(f"unsupported timeframe {timeframe!r} -- only {list(_TIMEFRAME_TO_BINANCE_INTERVAL)}")
        if count <= 0:
            raise ValueError(f"count must be positive, got {count}")

        # Fetch one extra candle: Binance may include the still-forming current candle,
        # which _drop_forming_candle then removes -- fetching count+1 keeps the returned
        # closed-candle count at `count` in the common case rather than silently under-
        # delivering by one bar every call.
        params = {"symbol": symbol, "interval": interval, "limit": count + 1}
        try:
            resp = self._http.get(f"{self._base_url}{KLINES_PATH}", params=params, timeout=self._timeout)
            resp.raise_for_status()
            raw = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise BinanceFeedRequestError("KLINES_REQUEST_FAILED", str(exc)) from exc
        if not isinstance(raw, list):
            raise BinanceFeedDataError("KLINES_MALFORMED_RESPONSE", f"expected a JSON array, got {type(raw)}")
        if not raw:
            raise BinanceFeedDataError("KLINES_EMPTY_RESPONSE", f"no candles returned for {symbol}/{timeframe}")

        parsed = _parse_klines(raw, timeframe)
        _validate_series(parsed, timeframe)

        now = self._clock()
        now_ms = int(now.astimezone(timezone.utc).timestamp() * 1000)
        parsed = _drop_forming_candle(parsed, now_ms)
        if not parsed:
            raise BinanceFeedDataError("KLINES_ALL_CANDLES_FORMING", f"no closed candle available for {symbol}/{timeframe}")

        expected_spacing_ms = _TIMEFRAME_MS[timeframe]
        staleness_ms = now_ms - parsed[-1]["close_time_ms"]
        if staleness_ms > expected_spacing_ms * _STALE_MULTIPLE:
            raise BinanceFeedStaleData(
                "KLINES_STALE_DATA",
                f"freshest closed candle for {symbol}/{timeframe} is {staleness_ms / 1000.0:.0f}s old "
                f"(> {_STALE_MULTIPLE}x{expected_spacing_ms // 1000}s threshold)",
            )

        return _to_candles(parsed[-count:], symbol, timeframe)
