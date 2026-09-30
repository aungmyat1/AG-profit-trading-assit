"""Market profile abstraction: parameterizes the asset-independent sweep/MSS/retest/state
machine engine (engine.py) by asset class instead of forking it.

The Forex profile's reference liquidity (Asian High/Low/Mid) and the Crypto profile's
reference liquidity (Previous-Day High/Low/Mid) are both just a completed candle window's
high/low/mid -- strategy_engine.session.build_reference_box already computes exactly that
generically (it only takes a session NAME label plus candles, never anything Asian-
specific), so this module REUSES it for both rather than adding a second box formula.

Audited before adding: no existing crypto/day-boundary contract exists anywhere in this
repo (checked session_clock.py -- Forex-session-specific only -- config/, liquidity/,
market_structure/, and the multi-asset-conventions skill, which is advisory markdown, not
code). previous_utc_day_window() below is therefore a genuinely new, deliberately minimal
piece: a strict [start, end) UTC calendar day boundary, nothing more.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence, Tuple

from strategy_engine.session import Candle, ReferenceBox, build_reference_box

REFERENCE_ASIAN_SESSION = "ASIAN_SESSION"
REFERENCE_PREVIOUS_DAY = "PREVIOUS_DAY"

BUFFER_PIP = "PIP"
BUFFER_TICK = "TICK"

PROFILE_FOREX = "FOREX"
PROFILE_CRYPTO_PERP = "CRYPTO_PERP"


@dataclass(frozen=True)
class MarketProfile:
    profile_id: str  # PROFILE_FOREX / PROFILE_CRYPTO_PERP
    symbols: Tuple[str, ...]
    reference_kind: str  # REFERENCE_ASIAN_SESSION / REFERENCE_PREVIOUS_DAY
    reference_label: str  # box.session_name, e.g. "Asian" / "PreviousDay"
    buffer_kind: str  # BUFFER_PIP / BUFFER_TICK
    execution_windows: Tuple[Tuple, ...] = ()  # [(time_start, time_end), ...] UTC, half-open


def profile_for_symbol(symbol: str, profiles: Sequence[MarketProfile]) -> Optional[MarketProfile]:
    return next((p for p in profiles if symbol in p.symbols), None)


def previous_utc_day_window(now: datetime) -> Tuple[datetime, datetime]:
    """Strict [start, end) UTC calendar day immediately preceding `now`'s own UTC
    calendar day -- the minimum boundary logic needed for the crypto Previous-Day
    reference (spec: "strict UTC day boundaries for V1"), nothing beyond that."""
    today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    return today_start - timedelta(days=1), today_start


def filter_previous_day_candles(candles: Sequence[Candle], now: datetime) -> list:
    start, end = previous_utc_day_window(now)
    return [c for c in candles if start <= c.time < end]


def build_profile_reference_box(
    profile: MarketProfile, candles: Sequence[Candle], expected_bar_count: Optional[int] = None
) -> Optional[ReferenceBox]:
    """Forex (ASIAN_SESSION): caller passes exactly the 00:00-06:00 UTC candles plus the
    real expected bar count, same completeness check as before (box.session_complete may
    be False -- an in-progress session).

    Crypto (PREVIOUS_DAY): caller passes exactly the completed prior UTC calendar day's
    candles (see filter_previous_day_candles); expected_bar_count defaults to len(candles)
    since "the prior day already ended" is itself the completeness signal for V1 -- no
    separate bar-count contract exists for crypto (spec: don't build more than needed).
    """
    if not candles:
        return None
    count = expected_bar_count if expected_bar_count is not None else len(candles)
    return build_reference_box(profile.reference_label, candles, count)
