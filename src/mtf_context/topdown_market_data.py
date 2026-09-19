"""TD-2: closed-candle acquisition entrypoint scoped to TopDownContext V1's six
canonical timeframes (W1/D1/H4/H1/M15/M5). NOT a new data provider -- delegates
entirely to strategy_contract.market_snapshot.from_mt5_latest_closed(), which itself
delegates to mt5.market_data.get_latest_candles() (copy_rates_from_pos position=1: the
still-forming bar is excluded, never returned as closed). No candle is fetched,
normalized, or validated a second time here.

Adds exactly one constraint on top of that existing, unmodified call chain: reject any
timeframe outside TOPDOWN_TIMEFRAMES up front, so a caller building future TD-3/TD-4
tier contexts cannot accidentally request M1 or M30 through this entrypoint. Those
remain fully available, unrestricted, via mt5.market_data / strategy_contract.
market_snapshot directly for execution-oriented consumers -- see TIMEFRAME_M1 in
topdown_contracts.py, which this module does not touch or restrict.

Fail-closed data-quality guards are entirely REUSED, not reinvented:
  - empty result / DATA_MISSING, INSUFFICIENT_CANDLES  -- mt5.market_data.get_latest_candles
  - forming/unclosed latest bar excluded                -- copy_rates_from_pos(..., 1, ...)
  - duplicate timestamps  (DUPLICATE_TIMESTAMPS)         -- mt5.market_data._validate_monotonic
  - non-monotonic timestamps (NON_MONOTONIC_TIMESTAMPS)  -- mt5.market_data._validate_monotonic
  - invalid OHLC geometry (INVALID_OHLC, NONFINITE_PRICE)-- mt5.market_data._validate_ohlc
  - unsupported timeframe (UNSUPPORTED_TIMEFRAME)        -- mt5.market_data._TIMEFRAMES lookup
  - not connected / symbol not found                     -- mt5.market_data._require_connected/_require_symbol
No new validation semantics are introduced in this module beyond the one additional
TOPDOWN_TIMEFRAMES membership check above.

REPLAY-FUTURE NOTE (recorded per TD-2 mission, not acted on): every call below reaches
a connected, live MT5 terminal via mt5.market_data.get_latest_candles ->
MetaTrader5.copy_rates_from_pos, and MarketSnapshot.from_mt5_latest_closed's
market_data_mode is hardcoded to "REAL". historical_replay/data_source_patch.py is the
existing, project-wide mechanism (TD-0 audit) that substitutes replay data at that
exact mt5.market_data call site by monkeypatching each importing module's own bound
name -- this module imports strategy_contract.market_snapshot, which itself imports
mt5.market_data.get_latest_candles at module load time, so a future TD-8 will need to
patch strategy_contract.market_snapshot's bound name the same way, or add a
from_replay_candle()-based path here, exactly like every other consumer in the
existing audit -- no new pattern to invent, but not free either: this module has no
REPLAY-mode entrypoint yet.
"""
from __future__ import annotations

from strategy_contract.market_snapshot import MarketSnapshot, from_mt5_latest_closed

from .topdown_contracts import TOPDOWN_TIMEFRAMES, InvalidTimeframeError


def closed_snapshot_for_topdown_timeframe(
    symbol: str, timeframe: str, source: str = "VANTAGE_DEMO_MT5",
) -> MarketSnapshot:
    """Fetch the single most recent CLOSED candle for one of TopDownContext V1's six
    canonical timeframes (W1/D1/H4/H1/M15/M5 -- see topdown_contracts.TOPDOWN_TIMEFRAMES)
    and wrap it as a MarketSnapshot. Raises InvalidTimeframeError for anything outside
    that set -- fail-closed, never silently widened to M1/M30/any other MT5-supported
    timeframe -- and propagates mt5.market_data.MarketDataError verbatim for any
    retrieval failure, same as MarketSnapshot.from_mt5_latest_closed itself.
    """
    if timeframe not in TOPDOWN_TIMEFRAMES:
        raise InvalidTimeframeError(
            f"{timeframe!r} is not one of TopDownContext V1's canonical timeframes {TOPDOWN_TIMEFRAMES}"
        )
    return from_mt5_latest_closed(symbol, timeframe, source=source)
