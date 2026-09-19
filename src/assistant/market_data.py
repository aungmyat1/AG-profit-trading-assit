"""Market Data Assistant layer: the five user-facing deterministic capabilities
(snapshot, historical query, session snapshot, data health, multi-timeframe snapshot).

Architecture: user request -> project-owned mt5.market_data / market_structure
functions -> validated, compact result dataclass -> caller/skill explains it. No raw
candle history gets routed through an LLM for calculation here -- every number in these
results is computed in Python before this module returns.

Reuses existing validation rather than re-implementing it: MT5 connection, UTC
normalization, OHLC/monotonic/freshness checks all live in mt5/market_data.py; this
module only adds gap detection and the assistant-shaped summaries.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

import session_clock as sc
from market_structure import StructureResult, analyze_structure
from mt5.market_data import MarketDataError, check_freshness, get_candles, get_latest_candles, get_tick
from strategy_engine.session import Candle

MAX_TICK_AGE_SECONDS = 120
RECENT_LOOKBACK_BARS = 20
_TIMEFRAME_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}


# --------------------------------------------------------------------------- 1. Market Snapshot

@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    status: str
    reason_codes: Tuple[str, ...]
    bid: Optional[float] = None
    ask: Optional[float] = None
    spread_points: Optional[int] = None
    tick_time_utc: Optional[datetime] = None
    freshness: Optional[str] = None
    latest_closed_candle: Optional[Candle] = None
    recent_high: Optional[float] = None
    recent_low: Optional[float] = None
    recent_lookback_bars: int = RECENT_LOOKBACK_BARS


def market_snapshot(symbol: str, timeframe: str = "M15") -> MarketSnapshot:
    try:
        tick = get_tick(symbol)
    except MarketDataError as exc:
        return MarketSnapshot(symbol=symbol, status=exc.reason_code, reason_codes=(exc.reason_code,))

    try:
        candles = get_latest_candles(symbol, timeframe, RECENT_LOOKBACK_BARS)
    except MarketDataError as exc:
        return MarketSnapshot(symbol=symbol, status=exc.reason_code, reason_codes=(exc.reason_code,),
                               bid=tick.bid, ask=tick.ask, spread_points=tick.spread_points,
                               tick_time_utc=tick.time_utc)

    now_utc = datetime.now(timezone.utc)
    freshness = check_freshness(tick.time_utc, now_utc, MAX_TICK_AGE_SECONDS) or "OK"

    return MarketSnapshot(
        symbol=symbol, status="OK", reason_codes=(),
        bid=tick.bid, ask=tick.ask, spread_points=tick.spread_points, tick_time_utc=tick.time_utc,
        freshness=freshness, latest_closed_candle=candles[-1],
        recent_high=max(c.high for c in candles), recent_low=min(c.low for c in candles),
        recent_lookback_bars=len(candles),
    )


# --------------------------------------------------------------------------- 2. Historical Candle Query

@dataclass(frozen=True)
class HistoricalCandleResult:
    symbol: str
    timeframe: str
    status: str
    reason_codes: Tuple[str, ...]
    candles: Tuple[Candle, ...] = ()
    start_utc: Optional[datetime] = None
    end_utc: Optional[datetime] = None
    candle_count: int = 0


def historical_candles(
    symbol: str,
    timeframe: str,
    start_utc: Optional[datetime] = None,
    end_utc: Optional[datetime] = None,
    count: Optional[int] = None,
) -> HistoricalCandleResult:
    """Either (start_utc, end_utc) or count -- not both, not neither."""
    if (start_utc is not None or end_utc is not None) and count is not None:
        return HistoricalCandleResult(symbol=symbol, timeframe=timeframe, status="AMBIGUOUS_QUERY",
                                       reason_codes=("AMBIGUOUS_QUERY",))
    try:
        if count is not None:
            candles = get_latest_candles(symbol, timeframe, count)
        elif start_utc is not None and end_utc is not None:
            candles = get_candles(symbol, timeframe, start_utc, end_utc)
        else:
            return HistoricalCandleResult(symbol=symbol, timeframe=timeframe, status="AMBIGUOUS_QUERY",
                                           reason_codes=("AMBIGUOUS_QUERY",))
    except MarketDataError as exc:
        return HistoricalCandleResult(symbol=symbol, timeframe=timeframe, status=exc.reason_code,
                                       reason_codes=(exc.reason_code,))

    return HistoricalCandleResult(symbol=symbol, timeframe=timeframe, status="OK", reason_codes=(),
                                   candles=tuple(candles), start_utc=candles[0].time, end_utc=candles[-1].time,
                                   candle_count=len(candles))


# --------------------------------------------------------------------------- 3. Session Snapshot

@dataclass(frozen=True)
class SessionSnapshot:
    symbol: str
    session_name: str
    session_date: date
    status: str
    reason_codes: Tuple[str, ...]
    complete: bool = False
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    range: Optional[float] = None
    midpoint: Optional[float] = None
    bar_count: Optional[int] = None
    expected_bar_count: Optional[int] = None


def session_snapshot(symbol: str, session_name: str, session_date: Optional[date] = None) -> SessionSnapshot:
    from historical_replay.candle_store import HistoricalDataError
    from historical_replay.data_source_patch import active_replay_context

    replay = active_replay_context()
    now_utc = replay[1] if replay is not None else datetime.now(timezone.utc)
    session_date = session_date or now_utc.date()

    try:
        start, end = sc.get_session_bounds(session_date, session_name)
        expected = sc.expected_bar_count(session_name, "M15")
    except sc.SessionContractConflict as exc:
        return SessionSnapshot(symbol=symbol, session_name=session_name, session_date=session_date,
                                status="SESSION_CONTRACT_CONFLICT", reason_codes=(str(exc),))

    complete = sc.session_complete(now_utc, session_date, session_name)
    if not complete:
        return SessionSnapshot(symbol=symbol, session_name=session_name, session_date=session_date,
                                status="SESSION_INCOMPLETE", reason_codes=("SESSION_INCOMPLETE",),
                                complete=False, expected_bar_count=expected)

    try:
        if replay is None:
            candles = get_candles(symbol, "M15", start, end)
        else:
            candles = replay[0].closed_candles_in_range(symbol, "M15", start, end, now_utc)
    except (MarketDataError, HistoricalDataError) as exc:
        return SessionSnapshot(symbol=symbol, session_name=session_name, session_date=session_date,
                                status=exc.reason_code, reason_codes=(exc.reason_code,),
                                complete=True, expected_bar_count=expected)

    high = max(c.high for c in candles)
    low = min(c.low for c in candles)
    status = "OK" if len(candles) == expected else "INSUFFICIENT_CANDLES"
    reason_codes = () if status == "OK" else ("INSUFFICIENT_CANDLES",)

    return SessionSnapshot(
        symbol=symbol, session_name=session_name, session_date=session_date, status=status,
        reason_codes=reason_codes, complete=True,
        open=candles[0].open, high=high, low=low, close=candles[-1].close,
        range=high - low, midpoint=(high + low) / 2.0,
        bar_count=len(candles), expected_bar_count=expected,
    )


# --------------------------------------------------------------------------- 4. Data Health

@dataclass(frozen=True)
class DataHealthResult:
    symbol: Optional[str]
    status: str  # "OK" or the first failing reason_code
    reason_codes: Tuple[str, ...]
    mt5_connected: bool
    checks: Dict[str, str]  # check name -> "OK" / a reason_code / "SKIPPED"


def data_health(symbol: Optional[str] = None, timeframe: str = "M15") -> DataHealthResult:
    from mt5.connection import is_connected
    checks: Dict[str, str] = {}

    connected = is_connected()
    checks["mt5_connection"] = "OK" if connected else "MT5_NOT_CONNECTED"
    if not connected:
        return DataHealthResult(symbol=symbol, status="MT5_NOT_CONNECTED", reason_codes=("MT5_NOT_CONNECTED",),
                                 mt5_connected=False, checks=checks)

    if symbol is None:
        return DataHealthResult(symbol=None, status="OK", reason_codes=(), mt5_connected=True, checks=checks)

    try:
        tick = get_tick(symbol)
        checks["symbol_available"] = "OK"
    except MarketDataError as exc:
        checks["symbol_available"] = exc.reason_code
        checks["freshness"] = "SKIPPED"
        checks["candle_integrity"] = "SKIPPED"
        checks["gap_check"] = "SKIPPED"
        return DataHealthResult(symbol=symbol, status=exc.reason_code, reason_codes=(exc.reason_code,),
                                 mt5_connected=True, checks=checks)

    now_utc = datetime.now(timezone.utc)
    checks["freshness"] = check_freshness(tick.time_utc, now_utc, MAX_TICK_AGE_SECONDS) or "OK"

    try:
        candles = get_latest_candles(symbol, timeframe, 100)
        # get_latest_candles already enforces OHLC validity / monotonic / duplicate / count
        checks["candle_integrity"] = "OK"
        checks["insufficient_history"] = "OK"
    except MarketDataError as exc:
        checks["candle_integrity"] = exc.reason_code
        checks["gap_check"] = "SKIPPED"
        return DataHealthResult(symbol=symbol, status=exc.reason_code, reason_codes=(exc.reason_code,),
                                 mt5_connected=True, checks=checks)

    gaps = _detect_unexpected_gaps(candles, timeframe)
    checks["gap_check"] = "OK" if not gaps else "UNEXPECTED_DATA_GAP"

    failing = [v for v in checks.values() if v not in ("OK", "SKIPPED")]
    status = "OK" if not failing else failing[0]
    return DataHealthResult(symbol=symbol, status=status, reason_codes=tuple(failing),
                             mt5_connected=True, checks=checks)


def _detect_unexpected_gaps(candles: Sequence[Candle], timeframe: str) -> List[Tuple[datetime, datetime]]:
    expected_minutes = _TIMEFRAME_MINUTES.get(timeframe)
    if expected_minutes is None:
        return []
    gaps = []
    for prev, cur in zip(candles, candles[1:]):
        actual_minutes = (cur.time - prev.time).total_seconds() / 60.0
        if actual_minutes > expected_minutes * 1.5 and not _spans_weekend_closure(prev.time, cur.time):
            gaps.append((prev.time, cur.time))
    return gaps


def _spans_weekend_closure(prev_time: datetime, cur_time: datetime) -> bool:
    """True if a Saturday (UTC) falls inside [prev_time, cur_time] -- the forex market
    is closed all Saturday, so a gap spanning one is an expected closure, not a fault."""
    d = prev_time.date()
    while d <= cur_time.date():
        if d.weekday() == 5:  # Saturday
            return True
        d += timedelta(days=1)
    return False


# --------------------------------------------------------------------------- 5. Multi-Timeframe Snapshot

@dataclass(frozen=True)
class TimeframeSummary:
    timeframe: str
    status: str
    bid: Optional[float] = None
    ask: Optional[float] = None
    latest_closed_close: Optional[float] = None
    structure: Optional[StructureResult] = None


@dataclass(frozen=True)
class MultiTimeframeSnapshot:
    symbol: str
    status: str
    reason_codes: Tuple[str, ...]
    by_timeframe: Tuple[TimeframeSummary, ...] = ()


def multi_timeframe_snapshot(symbol: str, timeframes: Sequence[str] = ("M15", "H1", "H4")) -> MultiTimeframeSnapshot:
    summaries = []
    failures = []
    for tf in timeframes:
        snap = market_snapshot(symbol, tf)
        if snap.status != "OK":
            summaries.append(TimeframeSummary(timeframe=tf, status=snap.status))
            failures.append(f"{tf}:{snap.status}")
            continue
        structure = analyze_structure(symbol, tf)
        summaries.append(TimeframeSummary(
            timeframe=tf, status="OK", bid=snap.bid, ask=snap.ask,
            latest_closed_close=snap.latest_closed_candle.close, structure=structure,
        ))

    status = "OK" if not failures else "PARTIAL"
    return MultiTimeframeSnapshot(symbol=symbol, status=status, reason_codes=tuple(failures),
                                   by_timeframe=tuple(summaries))
