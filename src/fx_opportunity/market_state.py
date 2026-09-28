"""Strategy-neutral normalized MarketState for the FX Opportunity platform.

Describes closed-bar FACTS for one symbol/cycle/instant: reference-session box,
post-session extremes, whether reference liquidity was taken, last closed bar,
observed spread (only when genuinely observed), provenance and a deterministic
fingerprint. It carries no trading authority -- no direction, no signal, no
execute/authorized flag, no broker handle.

Only bars whose close time is <= `now` participate (see `closed_only`). Dropped
forming/future bars are deliberately NOT part of MarketState: their mere presence in a
feed must not change the state or its fingerprint (look-ahead guarantee).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from mt5.market_data import MarketDataError
from post_asian_pilot.fingerprint import fingerprint
from strategy_engine.session import Candle

from .instruments import Instrument

SCHEMA = "AG_FX_MARKET_STATE_V1"
M15 = dt.timedelta(minutes=15)

FetchCandles = Callable[[str, str, dt.datetime, dt.datetime], List[Candle]]


def closed_only(
    candles: Sequence[Candle], start: dt.datetime, end: dt.datetime, now: dt.datetime,
) -> Tuple[List[Candle], int]:
    """Keep bars with open in [start, end) whose close is <= min(now, end)."""
    horizon = min(now, end)
    kept = [c for c in candles if start <= c.time < end and c.time + M15 <= horizon]
    return kept, len(candles) - len(kept)


def ordered_unique(candles: Sequence[Candle]) -> bool:
    times = [c.time for c in candles]
    return times == sorted(times) and len(set(times)) == len(times)


def candles_fingerprint(candles: Sequence[Candle]) -> Optional[str]:
    if not candles:
        return None
    return fingerprint([[c.time.isoformat(), c.open, c.high, c.low, c.close] for c in candles])


@dataclass(frozen=True)
class MarketState:
    schema: str
    symbol: str
    instrument_fingerprint: str
    timeframe: str
    cycle: str
    trading_date: str
    as_of: str
    market_data_mode: str
    source: str
    reference_session: str
    reference_window_utc: Tuple[str, str]
    execution_window_utc: Tuple[str, str]
    reference_bars_expected: int
    reference_bar_count: int
    reference_complete: bool
    reference_high: Optional[float]
    reference_low: Optional[float]
    reference_mid: Optional[float]
    reference_range: Optional[float]
    reference_range_pips: Optional[float]
    reference_fingerprint: Optional[str]
    post_session_bar_count: int
    post_session_high: Optional[float]
    post_session_low: Optional[float]
    reference_high_taken: Optional[bool]
    reference_low_taken: Optional[bool]
    post_session_fingerprint: Optional[str]
    last_closed_bar: Optional[Dict[str, Any]]
    spread_pips: Optional[float]
    spread_source: Optional[str]
    fingerprint: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_market_state(
    *,
    instrument: Instrument,
    cycle: str,
    trading_date: dt.date,
    now: dt.datetime,
    reference_session: str,
    reference_window: Tuple[dt.datetime, dt.datetime],
    execution_window: Tuple[dt.datetime, dt.datetime],
    expected_reference_bars: int,
    reference_candles: Sequence[Candle],
    post_candles: Sequence[Candle],
    market_data_mode: str,
    source: str,
    spread_price: Optional[float] = None,
    spread_source: Optional[str] = None,
) -> MarketState:
    """Pure: identical closed candles + configuration -> identical MarketState."""
    for bar in list(reference_candles) + list(post_candles):
        if bar.time + M15 > now:
            raise ValueError(f"forming bar {bar.time.isoformat()} passed to build_market_state at {now.isoformat()}")
    complete = len(reference_candles) == expected_reference_bars and ordered_unique(reference_candles)
    hi = max(c.high for c in reference_candles) if complete else None
    lo = min(c.low for c in reference_candles) if complete else None
    post_hi = max(c.high for c in post_candles) if post_candles else None
    post_lo = min(c.low for c in post_candles) if post_candles else None
    last = (list(post_candles) or list(reference_candles) or [None])[-1]
    fields: Dict[str, Any] = dict(
        schema=SCHEMA,
        symbol=instrument.symbol,
        instrument_fingerprint=instrument.fingerprint(),
        timeframe=instrument.timeframe,
        cycle=cycle,
        trading_date=trading_date.isoformat(),
        as_of=now.isoformat(),
        market_data_mode=market_data_mode,
        source=source,
        reference_session=reference_session,
        reference_window_utc=(reference_window[0].isoformat(), reference_window[1].isoformat()),
        execution_window_utc=(execution_window[0].isoformat(), execution_window[1].isoformat()),
        reference_bars_expected=expected_reference_bars,
        reference_bar_count=len(reference_candles),
        reference_complete=complete,
        reference_high=hi,
        reference_low=lo,
        reference_mid=round((hi + lo) / 2, instrument.digits + 1) if complete else None,
        reference_range=round(hi - lo, instrument.digits) if complete else None,
        reference_range_pips=instrument.price_to_pips(hi - lo) if complete else None,
        reference_fingerprint=candles_fingerprint(reference_candles),
        post_session_bar_count=len(post_candles),
        post_session_high=post_hi,
        post_session_low=post_lo,
        reference_high_taken=(post_hi > hi) if (complete and post_candles) else None,
        reference_low_taken=(post_lo < lo) if (complete and post_candles) else None,
        post_session_fingerprint=candles_fingerprint(post_candles),
        last_closed_bar=None if last is None else {
            "open_utc": last.time.isoformat(), "close_utc": (last.time + M15).isoformat(),
            "open": last.open, "high": last.high, "low": last.low, "close": last.close,
        },
        spread_pips=instrument.price_to_pips(spread_price) if spread_price is not None else None,
        spread_source=spread_source if spread_price is not None else None,
    )
    return MarketState(fingerprint=fingerprint(fields), **fields)


def observe_market_state(
    *,
    instrument: Instrument,
    cycle: str,
    trading_date: dt.date,
    now: dt.datetime,
    reference_session: str,
    reference_window: Tuple[dt.datetime, dt.datetime],
    execution_window: Tuple[dt.datetime, dt.datetime],
    expected_reference_bars: int,
    fetch_candles: FetchCandles,
    market_data_mode: str,
    source: str,
    spread_price: Optional[float] = None,
    spread_source: Optional[str] = None,
) -> Tuple[Optional[MarketState], Tuple[str, ...]]:
    """Fetch closed bars and build a MarketState without any strategy.

    Returns (state, reason_codes). A fetch failure returns (None, (reason_code,));
    before the reference session closes nothing is fetched.
    """
    ref_start, ref_end = reference_window
    win_start, win_end = execution_window
    ref: List[Candle] = []
    post: List[Candle] = []
    if now >= ref_end:
        try:
            ref, _ = closed_only(fetch_candles(instrument.symbol, instrument.timeframe, ref_start, ref_end),
                                 ref_start, ref_end, now)
        except MarketDataError as exc:
            return None, (exc.reason_code,)
    if now >= win_start + M15:
        try:
            raw = fetch_candles(instrument.symbol, instrument.timeframe, win_start, min(now, win_end))
        except MarketDataError as exc:
            return None, (exc.reason_code,)
        post, _ = closed_only(raw, win_start, win_end, now)
        if not ordered_unique(post):
            return None, ("POST_SESSION_DUPLICATE_OR_UNORDERED_BARS",)
    state = build_market_state(
        instrument=instrument, cycle=cycle, trading_date=trading_date, now=now,
        reference_session=reference_session, reference_window=reference_window,
        execution_window=execution_window, expected_reference_bars=expected_reference_bars,
        reference_candles=ref, post_candles=post,
        market_data_mode=market_data_mode, source=source,
        spread_price=spread_price, spread_source=spread_source,
    )
    return state, ()
