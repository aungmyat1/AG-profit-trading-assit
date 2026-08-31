"""Real, production candle/equity/symbol-meta wiring for AG_DAYTRADING_RUNTIME_V1 --
built ENTIRELY on the existing mt5.market_data / mt5.account / mt5.symbol_resolver
capabilities (audited: this is the repo's one MT5 data-fetch layer; see those modules'
own docstrings). No second MT5 data-fetch mechanism is introduced here -- this module
only adapts the existing (symbol, timeframe, ...) -> List[Candle] shape to the specific
callables execution_runtime.cycle.evaluate_and_route expects (see that module's own
ReferenceCandlesFn/H1CandlesFn/M5CandlesFn/SymbolMetaFn/StopBufferFn type aliases).

Forex only -- see execution_runtime.crypto_feed for why no symmetric crypto provider
exists here (no crypto candle source exists anywhere in this repo).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from mt5.account import account as get_account
from mt5.market_data import get_candles, get_latest_candles
from mt5.symbol_resolver import SymbolMeta, get_symbol_meta
from strategy_engine.session import Candle
from strategy_engine.sweep_retest.config import ProfileConfig
from strategy_engine.sweep_retest.targets import forex_sl_buffer_price

H1_LOOKBACK_BARS = 60  # >= h1_trend_direction's own internal swing-detection need
M5_LOOKBACK_BARS = 200  # covers a full Asian->London/NY window at M5 granularity
ASIAN_M15_BAR_COUNT = 24  # 00:00-06:00 UTC at M15 == 6h * 4 bars/h


def fetch_h1_candles(symbol: str) -> List[Candle]:
    return get_latest_candles(symbol, "H1", H1_LOOKBACK_BARS)


def fetch_m5_candles(symbol: str) -> List[Candle]:
    return get_latest_candles(symbol, "M5", M5_LOOKBACK_BARS)


def fetch_forex_reference_candles(symbol: str, profile_config: ProfileConfig, now: datetime) -> List[Candle]:
    """Today's Asian-session (00:00-06:00 UTC) M15 candles -- the exact window
    profile_config.reference_start_gmt/reference_end_gmt names, at the M15 granularity
    ST_ASIAN_SWEEP_5R_V1's own timeframe_responsibilities convention already uses for
    session-reference boxes (see strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml)."""
    day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    start = day_start  # 00:00 GMT
    end = day_start + timedelta(hours=6)  # 06:00 GMT
    if now < end:
        end = now  # session still in progress -- only closed bars, never a future boundary
    if now < start:
        return []
    return get_candles(symbol, "M15", start, end)


def reference_expected_bar_count(profile_config: ProfileConfig) -> int:
    return ASIAN_M15_BAR_COUNT


def fetch_symbol_meta(symbol: str) -> SymbolMeta:
    return get_symbol_meta(symbol)


def fetch_equity() -> float:
    return get_account().equity


def forex_stop_buffer_price(symbol: str, profile_config: ProfileConfig) -> float:
    return forex_sl_buffer_price(fetch_symbol_meta(symbol), profile_config.buffer_pips)
