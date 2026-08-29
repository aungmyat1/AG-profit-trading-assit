"""HistoricalCandleStore -- the historical stand-in for live MT5 candle retrieval
(historical-validation spec sections 8-11, 51). Holds a pre-loaded, immutable,
chronologically sorted candle series per (symbol, timeframe) and answers exactly the
question the live `get_latest_candles` answers: "the most recent N CLOSED bars as of
some clock time" -- except here "now" is the replay clock, not wall-clock, and a bar
only counts as closed once `bar_open_time + timeframe_duration <= as_of` (spec section
51: an H1 10:00-11:00 bar is not usable before 11:00; same rule for every timeframe,
including D1).

This module knows nothing about SMC semantics -- it is pure data plumbing, patched in
place of `mt5.market_data.get_latest_candles`/`get_tick` (see data_source_patch.py) so
the SAME frozen analyzers used live consume historical data with identical closure
semantics (spec section 9: differences limited to DATA SOURCE / CLOCK / EXECUTION
SIMULATOR, never SMC semantics).
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Sequence, Tuple

from strategy_engine.session import Candle

TIMEFRAME_MINUTES: Dict[str, int] = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}


class HistoricalDataError(RuntimeError):
    """Mirrors mt5.market_data.MarketDataError's (reason_code, message) shape so
    analyzers' existing except MarketDataError paths would need the same handling --
    the patch layer re-raises this AS a MarketDataError, see data_source_patch.py."""

    def __init__(self, reason_code: str, message: str):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code


def timeframe_duration(timeframe: str) -> timedelta:
    if timeframe not in TIMEFRAME_MINUTES:
        raise HistoricalDataError("UNSUPPORTED_TIMEFRAME", f"{timeframe!r} not in {list(TIMEFRAME_MINUTES)}")
    return timedelta(minutes=TIMEFRAME_MINUTES[timeframe])


@dataclass(frozen=True)
class _Series:
    times: Tuple[datetime, ...]  # open times, ascending, parallel to candles
    candles: Tuple[Candle, ...]


class HistoricalCandleStore:
    """Load once (e.g. from a bulk historical fetch or CSV import) via `load_series`,
    then query many times across a replay via `closed_candles`. Candles must be
    strictly ascending by open time and gap-checked by the caller beforehand (spec
    section 48 data-quality audit is a separate, earlier step -- this store does not
    silently repair bad input; see market_data_quality skill)."""

    def __init__(self) -> None:
        self._series: Dict[Tuple[str, str], _Series] = {}

    def load_series(self, symbol: str, timeframe: str, candles: Sequence[Candle]) -> None:
        ordered = sorted(candles, key=lambda c: c.time)
        for a, b in zip(ordered, ordered[1:]):
            if b.time <= a.time:
                raise HistoricalDataError(
                    "DUPLICATE_OR_UNORDERED_TIMESTAMP",
                    f"{symbol} {timeframe}: non-increasing candle timestamps at {a.time} -> {b.time}",
                )
        self._series[(symbol, timeframe)] = _Series(
            times=tuple(c.time for c in ordered), candles=tuple(ordered),
        )

    def closed_candles(self, symbol: str, timeframe: str, as_of: datetime, count: int) -> List[Candle]:
        """Most recent `count` bars whose CLOSE time (open + duration) <= as_of,
        oldest first -- the historical analogue of get_latest_candles's "position 1 is
        the last fully closed bar" contract."""
        key = (symbol, timeframe)
        if key not in self._series:
            raise HistoricalDataError("DATA_MISSING", f"no historical series loaded for {symbol} {timeframe}")
        series = self._series[key]
        duration = timeframe_duration(timeframe)
        cutoff_open_time = as_of - duration  # a bar is closed iff its OPEN time <= cutoff_open_time
        # times ascending; bisect_right gives first index whose open time > cutoff_open_time
        end_index = bisect_right(series.times, cutoff_open_time)
        if end_index == 0:
            raise HistoricalDataError(
                "DATA_MISSING", f"{symbol} {timeframe}: no closed bars at or before {as_of.isoformat()}"
            )
        start_index = max(0, end_index - count)
        result = list(series.candles[start_index:end_index])
        if len(result) < count:
            raise HistoricalDataError(
                "INSUFFICIENT_CANDLES", f"{symbol} {timeframe}: requested {count}, only {len(result)} closed by {as_of.isoformat()}"
            )
        return result

    def last_closed_price(self, symbol: str, timeframe: str, as_of: datetime) -> float:
        """Close price of the most recent bar closed at/before `as_of` -- used to
        synthesize a historical Tick (spread/slippage are Stage D concerns, out of
        scope for this semantic-replay data source; see docs RESEARCH_ASSUMPTION note
        in data_source_patch.py)."""
        return self.closed_candles(symbol, timeframe, as_of, 1)[0].close
