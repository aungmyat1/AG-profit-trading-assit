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

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from threading import RLock
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

from strategy_engine.session import Candle

from .dataset_identity import ReplayDatasetIdentity, build_dataset_identity, compute_candle_series_fingerprint

# TD-8: W1 added additively (mtf_context.topdown_composer's HISTORICAL_AS_OF mode needs
# a closed-bar boundary for all six TopDownContext tiers, including weekly) -- same
# value (10080 minutes = 7 days) already used by mt5/market_data.py's own
# _RAW_CACHE_PERIOD_MINUTES and strategy_contract/market_snapshot.py's
# _TIMEFRAME_MINUTES for W1. No existing (symbol, timeframe) key or behavior changes.
TIMEFRAME_MINUTES: Dict[str, int] = {
    "M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440, "W1": 10080,
}


def _require_aware_utc(value: datetime, label: str) -> None:
    """TD-8: explicit fail-closed guard for a timezone-naive replay clock/query time --
    same NAIVE_DATETIME_REJECTED idiom mt5/market_data.py::get_candles already uses for
    its own start_utc/end_utc parameters (this repo's dominant convention for any
    caller-supplied 'as-of'/'decision_time' argument: reject, never silently assume
    UTC). Before this guard, a naive `as_of` would silently compare against tz-aware
    `Candle.time` values and raise an unrelated TypeError deep inside bisect_right --
    this raises a clear, correctly-typed HistoricalDataError instead. Additive only:
    every existing caller already always passes tz-aware datetimes (see
    tests/test_historical_replay_no_lookahead.py), so this changes no existing
    passing test's behavior."""
    if value.tzinfo is None:
        raise HistoricalDataError("NAIVE_DATETIME_REJECTED", f"{label} must be timezone-aware UTC, got a naive datetime")


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
    identity: ReplayDatasetIdentity  # TD-8: always present once loaded -- see load_series


@dataclass(frozen=True)
class BoundReplaySeries:
    """Atomic identity and immutable candle population from one store state."""
    symbol: str
    timeframe: str
    identity: ReplayDatasetIdentity
    candles: Tuple[Candle, ...]

    def __post_init__(self) -> None:
        # Defensive normalization makes direct public construction safe for callers
        # that provide a list or other iterable; the stored representation is always
        # detached from caller-owned containers.
        normalized = tuple(self.candles)
        if not normalized:
            raise HistoricalDataError("DATA_MISSING", "cannot bind an empty replay series")
        if self.identity.symbol != self.symbol or self.identity.timeframe != self.timeframe:
            raise ValueError("bound series symbol/timeframe do not match dataset identity")
        if self.identity.fingerprint != compute_candle_series_fingerprint(
            self.symbol, self.timeframe, normalized,
        ):
            raise ValueError("bound series candles do not match dataset identity fingerprint")
        ordered = sorted(normalized, key=lambda candle: candle.time)
        if self.identity.coverage_start != ordered[0].time or self.identity.coverage_end != ordered[-1].time:
            raise ValueError("bound series coverage does not match dataset identity")
        if tuple(ordered) != normalized:
            raise ValueError("bound series candles must be chronologically ordered")
        object.__setattr__(self, "candles", normalized)


class HistoricalCandleStore:
    """Load once (e.g. from a bulk historical fetch or CSV import) via `load_series`,
    then query many times across a replay via `closed_candles`. Candles must be
    strictly ascending by open time and gap-checked by the caller beforehand (spec
    section 48 data-quality audit is a separate, earlier step -- this store does not
    silently repair bad input; see market_data_quality skill)."""

    def __init__(self) -> None:
        self._series: Dict[Tuple[str, str], _Series] = {}
        self._lock = RLock()

    def load_series(
        self, symbol: str, timeframe: str, candles: Sequence[Candle], *,
        dataset_id: Optional[str] = None, source: str = "REPLAY",
    ) -> None:
        """TD-8: `dataset_id`/`source` are optional, additive kwargs -- every existing
        call site (stage1/stage2/orchestrator and their tests) keeps working completely
        unmodified. A `ReplayDatasetIdentity` is always computed and stored regardless
        (see build_dataset_identity: collision-safety comes from a content-derived
        `fingerprint`, not from the caller bothering to supply a label), so
        `dataset_identity()` below never returns None for a (symbol, timeframe) that
        was actually loaded -- only for one that was never loaded at all."""
        ordered = sorted(candles, key=lambda c: c.time)
        for a, b in zip(ordered, ordered[1:]):
            if b.time <= a.time:
                raise HistoricalDataError(
                    "DUPLICATE_OR_UNORDERED_TIMESTAMP",
                    f"{symbol} {timeframe}: non-increasing candle timestamps at {a.time} -> {b.time}",
                )
        identity = build_dataset_identity(
            symbol=symbol, timeframe=timeframe, candles=ordered, dataset_id=dataset_id, source=source,
        )
        with self._lock:
            self._series[(symbol, timeframe)] = _Series(
                times=tuple(c.time for c in ordered), candles=tuple(ordered), identity=identity,
            )

    def bind_series(self, symbol: str, timeframe: str) -> BoundReplaySeries:
        """Atomically bind identity and immutable candles from one loaded series."""
        with self._lock:
            series = self._series.get((symbol, timeframe))
            if series is None:
                raise HistoricalDataError("DATA_MISSING", f"no historical series loaded for {symbol} {timeframe}")
            return BoundReplaySeries(symbol, timeframe, series.identity, series.candles)

    def dataset_identity(self, symbol: str, timeframe: str) -> Optional[ReplayDatasetIdentity]:
        """TD-8: None iff nothing was ever loaded for this (symbol, timeframe) -- a
        caller (e.g. mtf_context.topdown_composer's HISTORICAL_AS_OF path) can use this
        as a pre-flight "is this tier's replay data even present" check, distinct from
        (and earlier than) `closed_candles` raising DATA_MISSING/INSUFFICIENT_CANDLES
        for an `as_of` that has too little history."""
        series = self._series.get((symbol, timeframe))
        return series.identity if series is not None else None

    def closed_candles(self, symbol: str, timeframe: str, as_of: datetime, count: int) -> List[Candle]:
        """Most recent `count` bars whose CLOSE time (open + duration) <= as_of,
        oldest first -- the historical analogue of get_latest_candles's "position 1 is
        the last fully closed bar" contract."""
        _require_aware_utc(as_of, "as_of")
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

    def closed_candles_in_range(
        self, symbol: str, timeframe: str, start: datetime, end: datetime, as_of: datetime,
    ) -> List[Candle]:
        """Closed bars opening in half-open [start, end), visible at replay time."""
        for label, value in (("start", start), ("end", end), ("as_of", as_of)):
            _require_aware_utc(value, label)
        if start >= end:
            raise HistoricalDataError("INVALID_RANGE", "start must precede end")
        series = self._series.get((symbol, timeframe))
        if series is None:
            raise HistoricalDataError("DATA_MISSING", f"no historical series loaded for {symbol} {timeframe}")
        first = bisect_left(series.times, start)
        last = bisect_left(series.times, end)
        duration = timeframe_duration(timeframe)
        visible = [c for c in series.candles[first:last] if c.time + duration <= as_of]
        if not visible:
            raise HistoricalDataError("DATA_MISSING", f"no closed {timeframe} bars for {symbol} in [{start}, {end}) at {as_of}")
        return visible

    def last_closed_price(self, symbol: str, timeframe: str, as_of: datetime) -> float:
        """Close price of the most recent bar closed at/before `as_of` -- used to
        synthesize a historical Tick (spread/slippage are Stage D concerns, out of
        scope for this semantic-replay data source; see docs RESEARCH_ASSUMPTION note
        in data_source_patch.py)."""
        return self.closed_candles(symbol, timeframe, as_of, 1)[0].close
