"""Canonical AG causal SMC and indicator features (FX discovery V1).

Semantics were chosen BEFORE any strategy outcome was computed; the parity evidence is in
docs/research/FX_DISCOVERY_V1_SEMANTIC_PARITY.md. Every feature carries the bar index
at which it becomes KNOWN (after that bar's close). A consumer at bar t may only use
features with known_at <= t.

- Swings follow the smc-mcp (MIT, AkhileshSelvan/smc-mcp @ 719862b) strict fractal.
  A swing high at i requires high[i] > high[i +/- j] for j = 1..k. Equal highs are
  NOT swings. The swing becomes known at i + k.
- BOS/CHoCH follow smc-mcp semantics: a CLOSE beyond the most recent KNOWN, not yet
  consumed swing. The label is relative to the trend in force; the first break out
  of neutral is CHoCH. A wick-only excursion is never a break.
- A sweep is AG-canonical. It follows smc-mcp's idea (wick beyond the level, close
  back inside), but only swings already KNOWN at the sweep bar are eligible. This
  corrects smc-mcp's liquidity.py, which accepts any swing with index < i, including
  unconfirmed ones (look-ahead).
- An FVG is the 3-candle gap low[i+1] > high[i-1] (bullish) or high[i+1] < low[i-1]
  (bearish), with no body-direction requirement (smc-mcp). It is known at i+1.
- ATR is Wilder's RMA of the true range, seeded with the SMA of the first n TRs. EMA
  uses alpha = 2/(n+1), seeded with the SMA of the first n closes. Both are checked
  against pandas-ta-classic 0.8.33.dev171 @ 8afeec2 in the parity harness.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from strategy_engine.session import Candle


@dataclass(frozen=True)
class Swing:
    index: int
    known_at: int
    price: float
    kind: str  # "high" | "low"


@dataclass(frozen=True)
class StructureBreak:
    index: int          # the bar whose CLOSE broke the level (known at its close)
    level: float
    swing_index: int
    event: str          # "BOS" | "CHoCH"
    direction: str      # "bullish" | "bearish"


@dataclass(frozen=True)
class Sweep:
    index: int          # the sweeping bar (known at its close)
    level: float
    swing_index: int
    direction: str      # "bullish" = low swept and closed back above; "bearish" = mirror


@dataclass(frozen=True)
class FVG:
    index: int          # middle candle
    known_at: int       # index + 1
    top: float
    bottom: float
    direction: str


def swings(bars: Sequence[Candle], k: int) -> List[Swing]:
    if k < 1:
        raise ValueError("k must be >= 1")
    out: List[Swing] = []
    for i in range(k, len(bars) - k):
        h, l = bars[i].high, bars[i].low
        if all(h > bars[i - j].high and h > bars[i + j].high for j in range(1, k + 1)):
            out.append(Swing(i, i + k, h, "high"))
        elif all(l < bars[i - j].low and l < bars[i + j].low for j in range(1, k + 1)):
            out.append(Swing(i, i + k, l, "low"))
    return out


def structure_breaks(bars: Sequence[Candle], sw: Sequence[Swing]) -> List[StructureBreak]:
    events: List[StructureBreak] = []
    trend = "neutral"
    last_high: Optional[Swing] = None
    last_low: Optional[Swing] = None
    pending = sorted(sw, key=lambda s: (s.known_at, s.index))
    cur = 0
    for i, b in enumerate(bars):
        while cur < len(pending) and pending[cur].known_at <= i:
            s = pending[cur]
            if s.kind == "high":
                last_high = s
            else:
                last_low = s
            cur += 1
        if last_high is not None and b.close > last_high.price:
            events.append(StructureBreak(i, last_high.price, last_high.index,
                                         "BOS" if trend == "bullish" else "CHoCH", "bullish"))
            trend, last_high = "bullish", None
        elif last_low is not None and b.close < last_low.price:
            events.append(StructureBreak(i, last_low.price, last_low.index,
                                         "BOS" if trend == "bearish" else "CHoCH", "bearish"))
            trend, last_low = "bearish", None
    return events


def sweeps(bars: Sequence[Candle], sw: Sequence[Swing]) -> List[Sweep]:
    out: List[Sweep] = []
    highs = sorted((s for s in sw if s.kind == "high"), key=lambda s: s.known_at)
    lows = sorted((s for s in sw if s.kind == "low"), key=lambda s: s.known_at)
    hi_cur = lo_cur = 0
    last_high: Optional[Swing] = None
    last_low: Optional[Swing] = None
    for i, b in enumerate(bars):
        # Strictly known before bar i: a swing confirmed by bar i itself cannot be swept by it.
        while hi_cur < len(highs) and highs[hi_cur].known_at < i:
            last_high = highs[hi_cur]
            hi_cur += 1
        while lo_cur < len(lows) and lows[lo_cur].known_at < i:
            last_low = lows[lo_cur]
            lo_cur += 1
        if last_high is not None and b.high > last_high.price and b.close < last_high.price:
            out.append(Sweep(i, last_high.price, last_high.index, "bearish"))
        elif last_low is not None and b.low < last_low.price and b.close > last_low.price:
            out.append(Sweep(i, last_low.price, last_low.index, "bullish"))
    return out


def fvgs(bars: Sequence[Candle]) -> List[FVG]:
    out: List[FVG] = []
    for i in range(1, len(bars) - 1):
        a, c = bars[i - 1], bars[i + 1]
        if c.low > a.high:
            out.append(FVG(i, i + 1, c.low, a.high, "bullish"))
        elif c.high < a.low:
            out.append(FVG(i, i + 1, a.low, c.high, "bearish"))
    return out


def atr(bars: Sequence[Candle], n: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(bars)
    trs: List[float] = []
    for i, b in enumerate(bars):
        tr = b.high - b.low if i == 0 else max(b.high - b.low, abs(b.high - bars[i - 1].close),
                                                abs(b.low - bars[i - 1].close))
        trs.append(tr)
        if i == n - 1:
            out[i] = sum(trs) / n
        elif i >= n:
            out[i] = (out[i - 1] * (n - 1) + tr) / n
    return out


def ema(values: Sequence[float], n: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    alpha = 2.0 / (n + 1)
    for i, v in enumerate(values):
        if i == n - 1:
            out[i] = sum(values[:n]) / n
        elif i >= n:
            out[i] = alpha * v + (1 - alpha) * out[i - 1]
    return out
