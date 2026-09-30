"""ST_LARGE_SMC_V1@1.1.0 detection -- composition of existing causal primitives only.

- Swings, sweeps (Sweep A: wick beyond a KNOWN swing, close back inside) and FVGs come from
  fx_discovery.features, a byte-exact copy of blob f16baab.
- Breaks follow features.structure_breaks semantics (close beyond the latest known,
  unconsumed swing; the first break out of neutral is a CHoCH). The only difference is the
  owner-stated 5-point tie tolerance: a close within tolerance of the level is not a
  break. MSS = CHoCH.
- Order blocks apply AG_ORDER_BLOCK_V1:
  - origin = last opposing closed candle before a qualifying displacement, where the
    displacement is judged by AG_ENTRY_DISPLACEMENT_V1;
  - a matching FVG is required within MAX_CANDLES_TO_FVG = 3, and so is a matching
    close-confirmed break;
  - the zone comes from supply_demand.ob_contract._classify_family_and_zone, the frozen
    PIVOT/SHADOW geometry;
  - invalidation is a close beyond the far edge.
  smartmoneyconcepts' ob() candidate detector is not used, because smartmoneyconcepts is
  not signal authority in 1.1.0.

Every object carries the UTC time at which it becomes KNOWN (after the confirming bar's
close). Callers pass only CLOSED candles.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import List, Optional, Sequence

from entry_confirmation.displacement import evaluate_displacement
from entry_confirmation.models import CandidateDirection, ConfirmationState
from fx_discovery import features as F
from strategy_engine.session import Candle
from supply_demand.ob_config import load_ag_order_block_config
from supply_demand.ob_contract import _classify_family_and_zone

from . import contract as C


def close_time(bar: Candle, minutes: int) -> dt.datetime:
    return bar.time + dt.timedelta(minutes=minutes)


@dataclass(frozen=True)
class Break:
    index: int
    level: float
    event: str       # "BOS" | "CHoCH"
    direction: str   # "bullish" | "bearish"


def tolerant_breaks(bars: Sequence[Candle], swings: Sequence[F.Swing], tol: float) -> List[Break]:
    events: List[Break] = []
    trend = "neutral"
    last_high: Optional[F.Swing] = None
    last_low: Optional[F.Swing] = None
    pending = sorted(swings, key=lambda s: (s.known_at, s.index))
    cur = 0
    for i, b in enumerate(bars):
        while cur < len(pending) and pending[cur].known_at <= i:
            s = pending[cur]
            if s.kind == "high":
                last_high = s
            else:
                last_low = s
            cur += 1
        if last_high is not None and b.close > last_high.price + tol:
            events.append(Break(i, last_high.price, "BOS" if trend == "bullish" else "CHoCH", "bullish"))
            trend, last_high = "bullish", None
        elif last_low is not None and b.close < last_low.price - tol:
            events.append(Break(i, last_low.price, "BOS" if trend == "bearish" else "CHoCH", "bearish"))
            trend, last_low = "bearish", None
    return events


def bias_at(breaks: Sequence[Break], index: int) -> Optional[str]:
    """Direction of the latest break confirmed at or before bar `index` (LONG/SHORT)."""
    last = None
    for br in breaks:
        if br.index <= index:
            last = br
    if last is None:
        return None
    return "LONG" if last.direction == "bullish" else "SHORT"


@dataclass(frozen=True)
class POI:
    poi_id: str
    kind: str                 # "FVG" | "OB_PIVOT" | "OB_SHADOW"
    direction: str            # "LONG" (demand) | "SHORT" (supply)
    low: float
    high: float
    origin_time: dt.datetime
    known_time: dt.datetime
    invalidated_time: Optional[dt.datetime]


def _first_close_beyond(bars, start, direction, low, high, minutes) -> Optional[dt.datetime]:
    for b in bars[start:]:
        if (direction == "LONG" and b.close < low) or (direction == "SHORT" and b.close > high):
            return close_time(b, minutes)
    return None


def h1_pois(symbol: str, h1: Sequence[Candle], breaks: Sequence[Break]) -> List[POI]:
    tf = C.TIMEFRAME_MINUTES["H1"]
    out: List[POI] = []
    fvgs = F.fvgs(h1)
    for g in fvgs:
        direction = "LONG" if g.direction == "bullish" else "SHORT"
        out.append(POI(
            f"{symbol}:H1:FVG:{direction}:{h1[g.index].time.isoformat()}", "FVG", direction,
            g.bottom, g.top, h1[g.index].time, close_time(h1[g.known_at], tf),
            _first_close_beyond(h1, g.known_at + 1, direction, g.bottom, g.top, tf),
        ))
    threshold = load_ag_order_block_config().pivot_shadow_body_ratio_threshold
    for d in range(20, len(h1)):
        for direction, cand, opposing in (("LONG", CandidateDirection.LONG, lambda c: c.close < c.open),
                                          ("SHORT", CandidateDirection.SHORT, lambda c: c.close > c.open)):
            ev = evaluate_displacement(h1[d], cand, h1[:d])
            if ev.status is not ConfirmationState.PASS:
                continue
            origin = next((j for j in range(d - 1, max(d - 1 - C.OB_MAX_ORIGIN_LOOKBACK, -1), -1)
                           if opposing(h1[j])), None)
            if origin is None:
                continue
            want = "bullish" if direction == "LONG" else "bearish"
            fvg = next((g for g in fvgs if g.direction == want and origin + 1 <= g.index <= origin + 3), None)
            brk = next((b for b in breaks if b.direction == want and b.index >= origin), None)
            if fvg is None or brk is None:
                continue
            family, low, high = _classify_family_and_zone(h1[origin], direction == "LONG", threshold)
            known_idx = max(fvg.known_at, brk.index, d)
            kind = "OB_PIVOT" if family.value == "PIVOT_OB" else "OB_SHADOW"
            out.append(POI(
                f"{symbol}:H1:{kind}:{direction}:{h1[origin].time.isoformat()}", kind, direction, low, high,
                h1[origin].time, close_time(h1[known_idx], tf),
                _first_close_beyond(h1, known_idx + 1, direction, low, high, tf),
            ))
    unique = {}
    for p in out:
        unique.setdefault(p.poi_id, p)
    return sorted(unique.values(), key=lambda p: (p.known_time, p.poi_id))


@dataclass(frozen=True)
class Opportunity:
    opp_id: str
    poi_id: str
    direction: str
    sweep_time: dt.datetime
    sweep_extreme: float
    choch_time: dt.datetime
    choch_level: float
    entry_reference: float       # CHoCH bar close -- a reference price, never an order
    choch_index: int
    invalidated_time: Optional[dt.datetime]


def m5_opportunities(m5: Sequence[Candle], pois: Sequence[POI], poi_valid_at, tol: float) -> List[Opportunity]:
    tf = C.TIMEFRAME_MINUTES["M5"]
    sw = F.swings(m5, C.SWING_K)
    breaks = tolerant_breaks(m5, sw, tol)
    out: List[Opportunity] = []
    for s in F.sweeps(m5, sw):
        direction = "LONG" if s.direction == "bullish" else "SHORT"
        bar = m5[s.index]
        t = close_time(bar, tf)
        touched = [p for p in pois if p.direction == direction and poi_valid_at(p, t)
                   and ((direction == "LONG" and bar.low <= p.high) or (direction == "SHORT" and bar.high >= p.low))]
        if not touched:
            continue
        poi = touched[-1]
        want = "bullish" if direction == "LONG" else "bearish"
        choch = next((b for b in breaks if b.event == "CHoCH" and b.direction == want
                      and s.index < b.index <= s.index + C.SWEEP_TO_CHOCH_WINDOW_M5), None)
        if choch is None:
            continue
        cand = CandidateDirection.LONG if direction == "LONG" else CandidateDirection.SHORT
        if evaluate_displacement(m5[choch.index], cand, m5[:choch.index]).status is not ConfirmationState.PASS:
            continue
        extreme = bar.low if direction == "LONG" else bar.high
        invalid = None
        for b in m5[choch.index + 1:]:
            if (direction == "LONG" and b.close < extreme) or (direction == "SHORT" and b.close > extreme):
                invalid = close_time(b, tf)
                break
        out.append(Opportunity(
            f"{poi.poi_id}|{bar.time.isoformat()}|{m5[choch.index].time.isoformat()}", poi.poi_id, direction,
            bar.time, extreme, m5[choch.index].time, choch.level, m5[choch.index].close, choch.index, invalid,
        ))
    return out


def c11_causal_target(m5: Sequence[Candle], direction: str, entry: float, upto_index: int) -> Optional[float]:
    """C11 structural-fallback semantics on causal swings: nearest UNSWEPT opposing M5 swing
    known by `upto_index`, strictly beyond the entry reference. The primary external-
    liquidity tier needs smartmoneyconcepts-based structure tiers and is NOT_EVALUATED."""
    kind = "high" if direction == "LONG" else "low"
    best = None
    for s in F.swings(m5[: upto_index + 1], C.SWING_K):
        if s.kind != kind or s.known_at > upto_index:
            continue
        beyond = s.price > entry if direction == "LONG" else s.price < entry
        if not beyond:
            continue
        later = m5[s.index + 1: upto_index + 1]
        swept = any((b.high > s.price) if direction == "LONG" else (b.low < s.price) for b in later)
        if swept:
            continue
        if best is None or abs(s.price - entry) < abs(best - entry):
            best = s.price
    return best
