"""FX discovery V1 candidate families A_SSR, B_HSF, C_LBR.

Each family is exactly as frozen in config/research/FX_DISCOVERY_V1_HYPOTHESIS_LEDGER.yaml
(b34ceca). Every function is causal: a decision at time t uses only bars and features
that are closed and known at t.
"""
from __future__ import annotations

import bisect
import datetime as dt
from typing import Dict, List, Optional, Sequence

from strategy_engine.session import Candle

from . import features as F
from .resolver import TradePlan

M15 = dt.timedelta(minutes=15)
H1 = dt.timedelta(hours=1)
K = 2
BUFFER_ATR = 0.1
MIN_STOP_ATR = 0.5
TARGET_R = 2.0


def aggregate(bars: Sequence[Candle], minutes: int) -> List[Candle]:
    out: List[Candle] = []
    cur = None
    for b in bars:
        t = b.time.replace(minute=(b.time.minute // minutes) * minutes if minutes < 60 else 0, second=0, microsecond=0)
        if cur is None or t != cur[0]:
            if cur is not None:
                out.append(Candle(time=cur[0], open=cur[1], high=cur[2], low=cur[3], close=cur[4]))
            cur = [t, b.open, b.high, b.low, b.close]
        else:
            cur[2], cur[3], cur[4] = max(cur[2], b.high), min(cur[3], b.low), b.close
    if cur is not None:
        out.append(Candle(time=cur[0], open=cur[1], high=cur[2], low=cur[3], close=cur[4]))
    return out


class Market:
    """Pre-computed M15/H1 series and causal ATR_H1 lookup for one development window."""

    def __init__(self, base: Sequence[Candle]):
        self.m15 = aggregate(base, 15)
        self.h1 = aggregate(base, 60)
        self.h1_atr = F.atr(self.h1, 14)
        self.h1_close_times = [b.time + H1 for b in self.h1]
        self.m15_times = [b.time for b in self.m15]
        h1_sw = F.swings(self.h1, K)
        self.h1_breaks = F.structure_breaks(self.h1, h1_sw)
        m15_sw = F.swings(self.m15, K)
        self.m15_sweeps = F.sweeps(self.m15, m15_sw)
        self.m15_fvgs = F.fvgs(self.m15)

    def atr_h1(self, t: dt.datetime) -> Optional[float]:
        i = bisect.bisect_right(self.h1_close_times, t) - 1
        return self.h1_atr[i] if i >= 0 else None

    def h1_bias(self, t: dt.datetime) -> str:
        bias = "neutral"
        for b in self.h1_breaks:
            if self.h1[b.index].time + H1 <= t:
                bias = b.direction
            else:
                break
        return bias

    def day_m15(self, d: dt.date) -> List[Candle]:
        lo = bisect.bisect_left(self.m15_times, dt.datetime.combine(d, dt.time(0), tzinfo=dt.timezone.utc))
        hi = bisect.bisect_left(self.m15_times, dt.datetime.combine(d + dt.timedelta(days=1), dt.time(0), tzinfo=dt.timezone.utc))
        return self.m15[lo:hi]


def _at(d: dt.date, hh: int, mm: int = 0) -> dt.datetime:
    return dt.datetime.combine(d, dt.time(hh, mm), tzinfo=dt.timezone.utc)


def _stops(direction: str, entry: float, structural: float, atr: float) -> Optional[tuple]:
    stop = structural - BUFFER_ATR * atr if direction == "LONG" else structural + BUFFER_ATR * atr
    risk = (entry - stop) if direction == "LONG" else (stop - entry)
    if risk <= 0:
        return None
    if risk < MIN_STOP_ATR * atr:
        risk = MIN_STOP_ATR * atr
        stop = entry - risk if direction == "LONG" else entry + risk
    target = entry + TARGET_R * risk if direction == "LONG" else entry - TARGET_R * risk
    return stop, target, risk


def _asian_box(day: Sequence[Candle], d: dt.date):
    box = [b for b in day if _at(d, 0) <= b.time < _at(d, 6)]
    if len(box) != 24:
        return None
    return max(b.high for b in box), min(b.low for b in box)


def family_a(mkt: Market, d: dt.date) -> Optional[TradePlan]:
    day = mkt.day_m15(d)
    box = _asian_box(day, d)
    if box is None:
        return None
    hi, lo = box
    sweep_i, side = None, None
    for i, b in enumerate(day):
        if not (_at(d, 7) <= b.time < _at(d, 10)):
            continue
        up = b.high > hi and b.close < hi
        dn = b.low < lo and b.close > lo
        if up and dn:
            continue
        if up or dn:
            sweep_i, side = i, ("bearish" if up else "bullish")
            break
    if sweep_i is None:
        return None
    for br in F.structure_breaks(day, F.swings(day, K)):
        if br.index <= sweep_i:
            continue
        if br.index > sweep_i + 8 or day[br.index].time >= _at(d, 10):
            return None
        if br.direction != side:
            continue
        direction = "LONG" if side == "bullish" else "SHORT"
        fill = day[br.index].time + M15
        atr = mkt.atr_h1(fill)
        if atr is None:
            return None
        seg = day[sweep_i:br.index + 1]
        structural = min(b.low for b in seg) if direction == "LONG" else max(b.high for b in seg)
        entry = day[br.index].close
        geo = _stops(direction, entry, structural, atr)
        if geo is None:
            return None
        stop, target, risk = geo
        return TradePlan("A_SSR", d, direction, "MARKET", entry, stop, target, fill, None, _at(d, 12),
                         {"sweep_time": day[sweep_i].time.isoformat(), "break": br.event, "atr_h1": atr,
                          "risk_pips": risk / 0.0001, "box_high": hi, "box_low": lo})
    return None


def family_b(mkt: Market, d: dt.date) -> Optional[TradePlan]:
    t = mkt.m15_times
    for sw in mkt.m15_sweeps:
        sb = mkt.m15[sw.index]
        if not (_at(d, 7) <= sb.time < _at(d, 15)):
            continue
        close_t = sb.time + M15
        bias = mkt.h1_bias(close_t)
        if bias == "neutral" or bias != sw.direction:
            continue
        fvg = next((f for f in mkt.m15_fvgs if f.direction == sw.direction and f.index > sw.index
                    and f.known_at <= sw.index + 6 and mkt.m15[f.known_at].time + M15 <= _at(d, 15)), None)
        if fvg is None:
            continue
        # First qualifying setup of the day (a sweep that obtains an FVG). Its order is final for the day.
        direction = "LONG" if sw.direction == "bullish" else "SHORT"
        activation = mkt.m15[fvg.known_at].time + M15
        atr = mkt.atr_h1(activation)
        if atr is None:
            return None
        entry = fvg.top if direction == "LONG" else fvg.bottom
        structural = sb.low if direction == "LONG" else sb.high
        geo = _stops(direction, entry, structural, atr)
        if geo is None:
            return None
        stop, target, risk = geo
        return TradePlan("B_HSF", d, direction, "LIMIT", entry, stop, target, activation,
                         min(activation + dt.timedelta(hours=3), _at(d, 16)), _at(d, 17),
                         {"sweep_time": sb.time.isoformat(), "fvg_known": activation.isoformat(), "h1_bias": bias,
                          "atr_h1": atr, "risk_pips": risk / 0.0001})
    return None


def family_c(mkt: Market, d: dt.date) -> Optional[TradePlan]:
    day = mkt.day_m15(d)
    box = _asian_box(day, d)
    if box is None:
        return None
    hi, lo = box
    bo = None
    for i, b in enumerate(day):
        if _at(d, 7) <= b.time < _at(d, 11) and (b.close > hi or b.close < lo):
            bo = (i, "LONG" if b.close > hi else "SHORT")
            break
    if bo is None:
        return None
    i0, direction = bo
    level = hi if direction == "LONG" else lo
    for j in range(i0 + 1, min(i0 + 9, len(day))):
        b = day[j]
        if b.time >= _at(d, 11):
            return None
        if direction == "LONG":
            if b.low <= level and b.close > level:
                break
            if b.close <= level:
                return None
        else:
            if b.high >= level and b.close < level:
                break
            if b.close >= level:
                return None
    else:
        return None
    fill = day[j].time + M15
    atr = mkt.atr_h1(fill)
    if atr is None:
        return None
    structural = day[j].low if direction == "LONG" else day[j].high
    geo = _stops(direction, day[j].close, structural, atr)
    if geo is None:
        return None
    stop, target, risk = geo
    return TradePlan("C_LBR", d, direction, "MARKET", day[j].close, stop, target, fill, None, _at(d, 16),
                     {"breakout_time": day[i0].time.isoformat(), "retest_time": day[j].time.isoformat(),
                      "atr_h1": atr, "risk_pips": risk / 0.0001, "box_high": hi, "box_low": lo})


FAMILIES = {"A_SSR": family_a, "B_HSF": family_b, "C_LBR": family_c}
