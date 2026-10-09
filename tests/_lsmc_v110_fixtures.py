"""Synthetic fixtures for ST_LARGE_SMC_V1@1.1.0 watch tests (no market data).

EURUSD-scaled prices. The fixture is built so that:
- H1: an oscillating base, then a bearish origin candle (bar 27) and a bullish
  displacement (bar 28) that closes above the base highs. That gives a bullish CHoCH
  (bias LONG), a bullish FVG [1.0994, 1.1030] and a PIVOT order block [1.0984, 1.0994].
  Price then retraces toward the FVG.
- M5 (from Tue 06:00 UTC): a gentle decline makes the M5 trend bearish. A swing high
  forms, a sweep bar wicks below the latest known swing low into the FVG and closes back
  above it, and a bullish displacement then closes above the swing high: a CHoCH.

`scale` multiplies every price (used for USDJPY/XAUUSD/crypto fixtures).
"""
from __future__ import annotations

import datetime as dt

from strategy_engine.session import Candle

UTC = dt.timezone.utc
H1_START = dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC)   # Monday
M5_START = dt.datetime(2026, 1, 6, 6, 0, tzinfo=UTC)   # Tuesday, london_am
NOW = dt.datetime(2026, 1, 6, 9, 30, tzinfo=UTC)


def _mk(t, o, h, l, c, k):
    return Candle(t, o * k, h * k, l * k, c * k)


def d1_bars(k=1.0):
    out = []
    start = dt.datetime(2025, 12, 22, 0, 0, tzinfo=UTC)
    for i in range(10):
        base = 1.0950 + 0.0010 * i
        out.append(_mk(start + dt.timedelta(days=i), base, base + 0.0060, base - 0.0040, base + 0.0020, k))
    return out


def h1_bars(k=1.0):
    rows = []
    wave = [0, 3, 6, 3, 0, -3]  # x 0.0001: strict fractal peaks/troughs every 6 bars
    for i in range(22):
        mid = 1.1000 + 0.0001 * wave[i % 6] - 0.00002 * i
        up = wave[(i + 1) % 6] > wave[i % 6]
        o, c = (mid - 0.0002, mid + 0.0002) if up else (mid + 0.0002, mid - 0.0002)
        rows.append((o, max(o, c) + 0.0004, min(o, c) - 0.0004, c))  # wide overlapping wicks: no base FVGs
    rows += [
        (1.0995, 1.0997, 1.0986, 1.0988),  # 22
        (1.0988, 1.0990, 1.0979, 1.0981),  # 23
        (1.0981, 1.0984, 1.0975, 1.0982),  # 24 swing low
        (1.0982, 1.0990, 1.0980, 1.0988),  # 25
        (1.0988, 1.0993, 1.0985, 1.0992),  # 26
        (1.0992, 1.0994, 1.0984, 1.0986),  # 27 bearish origin (body/range = 0.6 -> PIVOT_OB)
        (1.0986, 1.1042, 1.0985, 1.1040),  # 28 bullish displacement, closes above base highs
        (1.1040, 1.1055, 1.1030, 1.1050),  # 29 -> FVG [1.0994 (27.high), 1.1030 (29.low)]
        (1.1050, 1.1052, 1.1033, 1.1035),  # 30
        (1.1035, 1.1038, 1.1031, 1.1033),  # 31
        (1.1033, 1.1040, 1.1031, 1.1036),  # 32 (opens Tue 08:00, closes 09:00)
    ]
    return [_mk(H1_START + dt.timedelta(hours=i), *r, k) for i, r in enumerate(rows)]


def m5_bars(k=1.0, choch_delay=0, total=42, weak_choch=False, break_after=False):
    """choch_delay > 0 pads flat bars between the sweep and the CHoCH (negative fixture).
    total pads flat bars after the CHoCH (for expiry tests). weak_choch makes the CHoCH
    bar a non-displacement candle. break_after adds a close below the sweep low after the
    CHoCH (invalidation)."""
    rows = []
    level = 1.1048
    for i in range(26):  # gentle decline with small alternating bodies -> bearish M5 trend
        level -= 0.00004
        up = i % 3 == 1
        o, c = (level - 0.00005, level + 0.00003) if up else (level + 0.00003, level - 0.00005)
        rows.append((o, max(o, c) + 0.00003, min(o, c) - 0.00003, c))
    rows += [
        (1.10375, 1.10380, 1.10345, 1.10350),  # 26
        (1.10350, 1.10355, 1.10318, 1.10322),  # 27 swing low candidate
        (1.10322, 1.10360, 1.10320, 1.10355),  # 28
        (1.10355, 1.10392, 1.10350, 1.10385),  # 29 swing high candidate
        (1.10385, 1.10388, 1.10352, 1.10356),  # 30
        (1.10356, 1.10360, 1.10335, 1.10340),  # 31
    ]
    rows += [
        (1.10340, 1.10345, 1.10262, 1.10336),  # sweep: wick below swing low into FVG, close back above
    ]
    rows += [(1.10340, 1.10346, 1.10336, 1.10342)] * choch_delay
    rows += [
        (1.10336, 1.10350, 1.10330, 1.10345),
        (1.10345, 1.10460, 1.10342, 1.10455) if not weak_choch
        else (1.10300, 1.10460, 1.10290, 1.10400),  # bullish displacement, closes above swing high -> CHoCH
    ]
    if break_after:
        rows += [(1.10455, 1.10456, 1.10240, 1.10250)]
    while len(rows) < total + choch_delay:
        last = rows[-1][3]
        rows.append((last, last + 0.00006, last - 0.00004, last + 0.00002))
    return [_mk(M5_START + dt.timedelta(minutes=5 * i), *r, k) for i, r in enumerate(rows)]
