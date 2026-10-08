"""Deterministic-opportunity engine for CRYPTO_CFD_TURTLE_BREAKOUT_D1_V1 (spec v1.0.0).

Every public function here is side-effect free, takes only CLOSED-bar data as of the
evaluation point, and never reads beyond the index it is given (no look-ahead). All
triggers are decided strictly on bar CLOSE (never intrabar). Stop/target/entry prices are
always rounded to a caller-supplied tick size before being returned.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence

N_CHANNEL = 55
ATR_PERIOD = 20
STOP_ATR_MULTIPLE = 2.0
TP_R_MULTIPLE = 2.0
EXPIRY_BARS = 5


@dataclass(frozen=True)
class Bar:
    time: datetime  # must be timezone-aware, UTC, represents the bar's CLOSE time
    open: float
    high: float
    low: float
    close: float

    def validate(self) -> None:
        if self.time.tzinfo is None:
            raise ValueError("Bar.time must be timezone-aware")
        if not (self.low <= self.open <= self.high and self.low <= self.close <= self.high):
            raise ValueError("Bar OHLC is internally inconsistent")


@dataclass(frozen=True)
class Decision:
    status: str  # NO_TRIGGER | TRIGGER_LONG | TRIGGER_SHORT | INSUFFICIENT_WARMUP | TRIGGER_DEFERRED_WEEKEND
    reason: str
    bar_time: datetime
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    tp1: Optional[float] = None
    expiry: Optional[datetime] = None
    direction: Optional[str] = None


@dataclass(frozen=True)
class Ticket:
    direction: str
    entry_price: float
    stop_loss: float
    tp1: float
    trigger_time: datetime
    expiry: datetime


@dataclass(frozen=True)
class TickResolution:
    filled: bool
    outcome: str  # EXPIRED_UNFILLED | TP1_HIT | STOP_HIT | UNRESOLVED_AT_HORIZON
    realized_r: Optional[float]
    detail: str


def _is_weekend_utc(ts: datetime) -> bool:
    """Saturday 00:00 UTC through Monday 00:00 UTC (spec deviation #4)."""
    if ts.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    ts = ts.astimezone(timezone.utc)
    return ts.weekday() in (5, 6)  # Mon=0 .. Sun=6; Sat=5, Sun=6


def _round_to_tick(price: float, tick_size: float, direction: str) -> float:
    """Quantize `price` to a multiple of `tick_size`.

    direction in {"away_up", "away_down", "toward_up", "toward_down"}: "away_*" rounds
    AWAY from entry (used for stops, conservative = wider), "toward_*" rounds TOWARD entry
    (used for targets, conservative = nearer) -- reuses PR #48's signed "stop rounds away
    from entry, target rounds toward it" convention. The _up/_down suffix picks which of
    ceil/floor implements "away"/"toward" for that side of the trade (LONG stop is below
    entry -> away = floor; LONG target is above entry -> toward = floor; etc., chosen by
    the caller per direction, not re-derived here).
    """
    import math
    if tick_size <= 0:
        raise ValueError("tick_size must be positive")
    ratio = round(price / tick_size, 8)  # guard against float noise before floor/ceil
    if direction in ("away_down", "toward_down"):
        n = math.floor(ratio)
    elif direction in ("away_up", "toward_up"):
        n = math.ceil(ratio)
    else:
        raise ValueError(f"unknown rounding direction: {direction}")
    return round(n * tick_size, 10)


def _true_range(prev_close: float, bar: Bar) -> float:
    return max(bar.high - bar.low, abs(bar.high - prev_close), abs(bar.low - prev_close))


def _atr(bars: Sequence[Bar], period: int = ATR_PERIOD) -> Optional[float]:
    """Simple-average ATR over `period` bars ending at the LAST bar in `bars` (bars[-1]).
    Requires period+1 bars (needs a previous close for the first true-range calc)."""
    if len(bars) < period + 1:
        return None
    window = bars[-(period + 1):]
    trs = [_true_range(window[i - 1].close, window[i]) for i in range(1, len(window))]
    return sum(trs) / len(trs)


def evaluate(bars_closed: Sequence[Bar], tick_size: float) -> Decision:
    """Evaluate the LAST bar in `bars_closed` as a potential trigger bar. `bars_closed`
    must contain ONLY bars with close_time <= the evaluation point (no look-ahead) and
    must be chronologically sorted ascending with bars_closed[-1] being the bar under
    evaluation."""
    for b in bars_closed:
        b.validate()
    if len(bars_closed) < N_CHANNEL + 1:
        return Decision(status="INSUFFICIENT_WARMUP", reason="fewer than N+1 closed bars available",
                         bar_time=bars_closed[-1].time if bars_closed else None)

    t_bar = bars_closed[-1]
    prior = bars_closed[-(N_CHANNEL + 1):-1]  # the N=55 bars strictly BEFORE t (no look-ahead, excludes t)
    channel_high = max(b.close for b in prior)
    channel_low = min(b.close for b in prior)

    if t_bar.close > channel_high:
        direction = "LONG"
    elif t_bar.close < channel_low:
        direction = "SHORT"
    else:
        return Decision(status="NO_TRIGGER", reason="close within [channel_low, channel_high]",
                         bar_time=t_bar.time)

    if _is_weekend_utc(t_bar.time):
        return Decision(status="TRIGGER_DEFERRED_WEEKEND",
                         reason="trigger condition met on a weekend-window bar; ticket deferred, "
                                "not lost -- re-evaluate this bar's own close once weekday resumes",
                         bar_time=t_bar.time, direction=direction)

    atr20 = _atr(bars_closed, ATR_PERIOD)
    if atr20 is None or atr20 <= 0:
        return Decision(status="NO_TRIGGER", reason="ATR(20) unavailable or non-positive; cannot size stop",
                         bar_time=t_bar.time, direction=direction)

    risk_distance = STOP_ATR_MULTIPLE * atr20
    entry_price = round(t_bar.close / tick_size) * tick_size  # entry itself has no "away/toward" side

    if direction == "LONG":
        stop_loss = _round_to_tick(entry_price - risk_distance, tick_size, "away_down")
        tp1 = _round_to_tick(entry_price + TP_R_MULTIPLE * risk_distance, tick_size, "toward_down")
    else:
        stop_loss = _round_to_tick(entry_price + risk_distance, tick_size, "away_up")
        tp1 = _round_to_tick(entry_price - TP_R_MULTIPLE * risk_distance, tick_size, "toward_up")

    expiry = t_bar.time + timedelta(days=EXPIRY_BARS)  # D1 cadence: EXPIRY_BARS calendar days is an
    # over-approximation on weekends but is only used to bound the resolver's search window below;
    # the actual bar-count-based expiry is enforced in resolve_ticket via max_bars.

    return Decision(status=f"TRIGGER_{direction}", reason="close-confirmed N=55 close-channel breakout",
                     bar_time=t_bar.time, entry_price=entry_price, stop_loss=stop_loss, tp1=tp1,
                     expiry=expiry, direction=direction)


def resolve_ticket(ticket: Ticket, bars_after: Sequence[Bar], max_bars: int = EXPIRY_BARS) -> TickResolution:
    """Resolve a pending LIMIT ticket against subsequent CLOSED bars only (no look-ahead
    beyond what's passed in). Always terminates within max_bars -- if the LIMIT is never
    touched, the ticket EXPIRES; this function never returns an indefinitely-pending state."""
    for b in bars_after:
        b.validate()
    window = list(bars_after)[:max_bars]

    filled_at: Optional[int] = None
    for i, b in enumerate(window):
        touched = (b.low <= ticket.entry_price <= b.high)
        if touched:
            filled_at = i
            break

    if filled_at is None:
        return TickResolution(filled=False, outcome="EXPIRED_UNFILLED", realized_r=None,
                               detail=f"LIMIT @ {ticket.entry_price} never touched within {max_bars} bars; "
                                      f"ticket EXPIRED (never left pending indefinitely)")

    risk = abs(ticket.entry_price - ticket.stop_loss)
    for b in window[filled_at:]:
        stop_hit = (b.low <= ticket.stop_loss) if ticket.direction == "LONG" else (b.high >= ticket.stop_loss)
        tp_hit = (b.high >= ticket.tp1) if ticket.direction == "LONG" else (b.low <= ticket.tp1)
        if stop_hit and tp_hit:
            # stop-first-on-same-bar-collision, consistent with the parent campaign's
            # replay convention (research_external/candidate_factory/replay/common.py)
            return TickResolution(filled=True, outcome="STOP_HIT", realized_r=-1.0,
                                   detail="same-bar collision resolved stop-first")
        if stop_hit:
            return TickResolution(filled=True, outcome="STOP_HIT", realized_r=-1.0, detail="stop touched")
        if tp_hit:
            r = TP_R_MULTIPLE if risk > 0 else 0.0
            return TickResolution(filled=True, outcome="TP1_HIT", realized_r=r, detail="target touched")

    return TickResolution(filled=True, outcome="UNRESOLVED_AT_HORIZON", realized_r=None,
                           detail=f"filled but neither stop nor target touched within the {max_bars}-bar horizon "
                                  f"passed to this call (caller's data window ended, not a strategy-level hang)")
