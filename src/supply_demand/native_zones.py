"""Native (non-smartmoneyconcepts) Supply & Demand zones: session boxes, previous-day
high/low, and premium/equilibrium/discount computed from an explicitly-named dealing
range. No smc import here -- see smc_adapter.py for the order-block/FVG side.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

from mt5.market_data import MarketDataError, get_latest_candles, get_tick

from .models import ZoneDirection, ZoneFamily, ZoneRole, ZoneResult, ZoneStatus

__all__ = ["session_zone", "previous_day_high_low", "previous_week_high_low", "dealing_range_zones",
           "premium_discount_from_previous_day", "premium_discount_from_session"]


# --------------------------------------------------------------------------- 3. Session zones

def session_zone(symbol: str, session_name: str, session_date: Optional[date] = None) -> ZoneResult:
    """Reuses assistant.market_data.session_snapshot() -- no new session math here.
    Status is deliberately UNKNOWN: whether a session box has since been swept/reclaimed
    is a Liquidity-phase question, not modeled here.

    Import is deferred to call time (not module load time): assistant.market_data sits
    above supply_demand in assistant/__init__.py's own import chain (assistant ->
    entry_confirmation -> liquidity -> supply_demand -> assistant), so importing it
    eagerly here re-enters assistant mid-init. See docs/specs/ENTRY_CONFIRMATION_V1_SPEC.md
    circular-import repair note."""
    from assistant.market_data import session_snapshot

    snap = session_snapshot(symbol, session_name, session_date)
    if snap.status != "OK":
        return ZoneResult(symbol=symbol, timeframe="M15", family=ZoneFamily.SESSION, role=ZoneRole.REFERENCE,
                           direction=ZoneDirection.NONE, status=ZoneStatus.UNKNOWN,
                           source="config/canonical_sessions.yaml", reason_codes=(snap.status,))

    return ZoneResult(
        symbol=symbol, timeframe="M15", family=ZoneFamily.SESSION, role=ZoneRole.REFERENCE,
        direction=ZoneDirection.NONE, low=snap.low, high=snap.high,
        origin_time=datetime.combine(snap.session_date, datetime.min.time(), tzinfo=timezone.utc),
        status=ZoneStatus.UNKNOWN, source="config/canonical_sessions.yaml",
        reason_codes=("STATUS_LIFECYCLE_NOT_MODELED_IN_SUPPLY_DEMAND_PHASE",),
    )


# --------------------------------------------------------------------------- 4. Previous Day High/Low

def previous_day_high_low(symbol: str) -> ZoneResult:
    """Project-owned, no smc: the last CLOSED D1 candle's high/low. get_latest_candles
    already excludes the still-forming current bar, so position 1 is exactly
    "yesterday" without any date-boundary arithmetic here."""
    try:
        candles = get_latest_candles(symbol, "D1", 1)
    except MarketDataError as exc:
        return ZoneResult(symbol=symbol, timeframe="D1", family=ZoneFamily.PREVIOUS_DAY, role=ZoneRole.REFERENCE,
                           direction=ZoneDirection.NONE, status=ZoneStatus.UNKNOWN,
                           source="mt5 D1 candles", reason_codes=(exc.reason_code,))

    prev = candles[0]
    status = ZoneStatus.FRESH
    reason_codes = ()
    try:
        tick = get_tick(symbol)
        if tick.bid > prev.high or tick.ask < prev.low:
            status = ZoneStatus.TOUCHED
        else:
            reason_codes = ("TOUCHED_CHECKS_CURRENT_PRICE_ONLY_NOT_INTRADAY_PATH",)
    except MarketDataError:
        status = ZoneStatus.UNKNOWN
        reason_codes = ("CURRENT_TICK_UNAVAILABLE_FOR_TOUCH_CHECK",)

    return ZoneResult(
        symbol=symbol, timeframe="D1", family=ZoneFamily.PREVIOUS_DAY, role=ZoneRole.REFERENCE,
        direction=ZoneDirection.NONE, low=prev.low, high=prev.high, origin_time=prev.time,
        status=status, source="mt5 D1 candles", reason_codes=reason_codes,
    )


# --------------------------------------------------------------------------- 4b. Previous Week High/Low

def previous_week_high_low(symbol: str) -> ZoneResult:
    """Project-owned, no smc: the high/low of the last fully CLOSED ISO calendar week,
    built from D1 candles only (mirrors previous_day_high_low's closed-period discipline).

    Deliberately does not reuse smc.previous_high_low(time_frame="1W") -- that path
    resamples internally and (per market_structure/smc_adapter.py's own documented
    bookend-artifact caveat on this smc version) is not something this pass wants to
    trust for a liquidity level's exact price. Instead: fetch a window of closed D1
    candles, group by ISO (year, week), exclude the week containing the most recent
    closed D1 candle (which may still be in progress broker-side), and take the most
    recent COMPLETE week that remains. No lookahead: only candles get_latest_candles
    already reports as closed are used, and the in-progress week is always excluded."""
    try:
        candles = get_latest_candles(symbol, "D1", 15)  # ~2-3 weeks of D1 bars, buffer for holidays/gaps
    except MarketDataError as exc:
        return ZoneResult(symbol=symbol, timeframe="D1", family=ZoneFamily.PREVIOUS_WEEK, role=ZoneRole.REFERENCE,
                           direction=ZoneDirection.NONE, status=ZoneStatus.UNKNOWN,
                           source="mt5 D1 candles", reason_codes=(exc.reason_code,))
    if not candles:
        return ZoneResult(symbol=symbol, timeframe="D1", family=ZoneFamily.PREVIOUS_WEEK, role=ZoneRole.REFERENCE,
                           direction=ZoneDirection.NONE, status=ZoneStatus.UNKNOWN,
                           source="mt5 D1 candles", reason_codes=("NO_D1_CANDLES",))

    def _iso_week(c):
        iso = c.time.isocalendar()
        return (iso[0], iso[1])

    current_week = _iso_week(candles[-1])
    prior_candles = [c for c in candles if _iso_week(c) != current_week]
    if not prior_candles:
        return ZoneResult(symbol=symbol, timeframe="D1", family=ZoneFamily.PREVIOUS_WEEK, role=ZoneRole.REFERENCE,
                           direction=ZoneDirection.NONE, status=ZoneStatus.UNKNOWN,
                           source="mt5 D1 candles", reason_codes=("INSUFFICIENT_WEEK_HISTORY",))

    last_complete_week = max(_iso_week(c) for c in prior_candles)
    week_candles = [c for c in prior_candles if _iso_week(c) == last_complete_week]
    high = max(c.high for c in week_candles)
    low = min(c.low for c in week_candles)
    origin = week_candles[-1].time  # last closed candle of that completed week

    status = ZoneStatus.FRESH
    reason_codes = ()
    try:
        tick = get_tick(symbol)
        if tick.bid > high or tick.ask < low:
            status = ZoneStatus.TOUCHED
        else:
            reason_codes = ("TOUCHED_CHECKS_CURRENT_PRICE_ONLY_NOT_INTRADAY_PATH",)
    except MarketDataError:
        status = ZoneStatus.UNKNOWN
        reason_codes = ("CURRENT_TICK_UNAVAILABLE_FOR_TOUCH_CHECK",)

    return ZoneResult(
        symbol=symbol, timeframe="D1", family=ZoneFamily.PREVIOUS_WEEK, role=ZoneRole.REFERENCE,
        direction=ZoneDirection.NONE, low=low, high=high, origin_time=origin,
        status=status, source="mt5 D1 candles", reason_codes=reason_codes,
    )


# --------------------------------------------------------------------------- 5. Premium/Equilibrium/Discount

@dataclass(frozen=True)
class DealingRangeZones:
    symbol: str
    source: str
    low: float
    high: float
    equilibrium: float
    premium_low: float   # equilibrium
    premium_high: float  # range high
    discount_low: float  # range low
    discount_high: float  # equilibrium
    current_price: Optional[float] = None
    current_zone: Optional[str] = None  # "PREMIUM" / "DISCOUNT" / "EQUILIBRIUM"


def dealing_range_zones(symbol: str, low: float, high: float, source: str, current_price: Optional[float] = None) -> DealingRangeZones:
    """Pure calculation from an EXPLICIT low/high -- this function never picks a dealing
    range itself. `source` must name where low/high came from (e.g. "previous_day",
    "session:asian:2026-08-26") so premium/discount is never reported without knowing
    what range it's relative to."""
    equilibrium = (low + high) / 2.0
    zone = None
    if current_price is not None:
        if current_price > equilibrium:
            zone = "PREMIUM"
        elif current_price < equilibrium:
            zone = "DISCOUNT"
        else:
            zone = "EQUILIBRIUM"
    return DealingRangeZones(
        symbol=symbol, source=source, low=low, high=high, equilibrium=equilibrium,
        premium_low=equilibrium, premium_high=high, discount_low=low, discount_high=equilibrium,
        current_price=current_price, current_zone=zone,
    )


def premium_discount_from_previous_day(symbol: str) -> Optional[DealingRangeZones]:
    zone = previous_day_high_low(symbol)
    if zone.low is None or zone.high is None:
        return None
    current = None
    try:
        current = get_tick(symbol).bid
    except MarketDataError:
        pass
    return dealing_range_zones(symbol, zone.low, zone.high, source="previous_day", current_price=current)


def premium_discount_from_session(symbol: str, session_name: str, session_date: Optional[date] = None) -> Optional[DealingRangeZones]:
    zone = session_zone(symbol, session_name, session_date)
    if zone.low is None or zone.high is None:
        return None
    current = None
    try:
        current = get_tick(symbol).bid
    except MarketDataError:
        pass
    return dealing_range_zones(symbol, zone.low, zone.high, source=f"session:{session_name}", current_price=current)
