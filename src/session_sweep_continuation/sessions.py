"""Reference-session construction, extended for this new engine (isolated from
ST_ASIAN_SWEEP_5R_V1's own strategy_engine/session/ implementation).

No-future-contamination invariant: `build_reference_session` and `build_trade_session`
only ever consider candles whose bar-open time falls within [start, end) AND whose
bar-CLOSE time (time + timeframe_minutes) is <= `as_of`. A caller stepping a replay
clock forward one M15 bar at a time can never see a candle that has not fully closed
yet -- this is the single mechanism that prevents lookahead throughout the rest of the
package (regime/swing/BOS/FVG all consume only sessions built this way).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import List, Optional, Sequence, Tuple

from strategy_engine.session.candles import Candle

M15_MINUTES = 15


def _parse_utc_time(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


@dataclass(frozen=True)
class SessionWindow:
    pair_id: str
    kind: str  # "reference" or "trade"
    start_time_utc: time
    end_time_utc: time

    def bounds_for_date(self, trading_date) -> Tuple[datetime, datetime]:
        start = datetime.combine(trading_date, self.start_time_utc, tzinfo=timezone.utc)
        end_time = self.end_time_utc
        end = datetime.combine(trading_date, end_time, tzinfo=timezone.utc)
        if end <= start:
            end += timedelta(days=1)
        return start, end


def session_windows_from_config(config: dict) -> dict:
    """Returns {pair_id: {"reference": SessionWindow, "trade": SessionWindow}}."""
    out = {}
    for pair in config.get("session_pairs", ()):
        pair_id = pair["pair_id"]
        ref = pair["reference_session"]
        trd = pair["trade_session"]
        out[pair_id] = {
            "reference": SessionWindow(
                pair_id=pair_id, kind="reference",
                start_time_utc=_parse_utc_time(ref["start_time_utc"]),
                end_time_utc=_parse_utc_time(ref["end_time_utc"]),
            ),
            "trade": SessionWindow(
                pair_id=pair_id, kind="trade",
                start_time_utc=_parse_utc_time(trd["start_time_utc"]),
                end_time_utc=_parse_utc_time(trd["end_time_utc"]),
            ),
        }
    return out


@dataclass(frozen=True)
class ReferenceSession:
    pair_id: str
    trading_date: object
    start: datetime
    end: datetime
    high: Optional[float]
    low: Optional[float]
    midline: Optional[float]
    range_pips: Optional[float]
    candle_count: int
    frozen: bool  # True once `end` has fully closed as of the replay clock


def _closed_candles_in_window(
    candles: Sequence[Candle], start: datetime, end: datetime, as_of: datetime, timeframe_minutes: int
) -> List[Candle]:
    out = []
    for c in candles:
        if c.time < start or c.time >= end:
            continue
        close_time = c.time + timedelta(minutes=timeframe_minutes)
        if close_time > as_of:
            continue  # this candle has not fully closed yet as of the replay clock
        out.append(c)
    return sorted(out, key=lambda c: c.time)


def build_reference_session(
    candles: Sequence[Candle],
    window: SessionWindow,
    trading_date,
    as_of: datetime,
    pip_size: float,
    timeframe_minutes: int = M15_MINUTES,
) -> ReferenceSession:
    start, end = window.bounds_for_date(trading_date)
    closed = _closed_candles_in_window(candles, start, end, as_of, timeframe_minutes)
    frozen = as_of >= end
    if not closed:
        return ReferenceSession(
            pair_id=window.pair_id, trading_date=trading_date, start=start, end=end,
            high=None, low=None, midline=None, range_pips=None, candle_count=0, frozen=frozen,
        )
    high = max(c.high for c in closed)
    low = min(c.low for c in closed)
    midline = (high + low) / 2.0
    range_pips = (high - low) / pip_size
    return ReferenceSession(
        pair_id=window.pair_id, trading_date=trading_date, start=start, end=end,
        high=high, low=low, midline=midline, range_pips=range_pips,
        candle_count=len(closed), frozen=frozen,
    )


def trade_session_candles(
    candles: Sequence[Candle], window: SessionWindow, trading_date, as_of: datetime,
    timeframe_minutes: int = M15_MINUTES,
) -> List[Candle]:
    start, end = window.bounds_for_date(trading_date)
    return _closed_candles_in_window(candles, start, end, as_of, timeframe_minutes)
