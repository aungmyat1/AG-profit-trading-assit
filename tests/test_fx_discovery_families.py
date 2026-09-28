"""FX discovery V1: family triggers, resolver invariants, and truncation look-ahead proof."""
from __future__ import annotations

import datetime as dt
import random
from dataclasses import replace

import pytest

from fx_discovery import features as F
from fx_discovery.families import FAMILIES, Market, family_a, family_b, family_c
from fx_discovery.resolver import (
    AMBIGUOUS,
    NOT_FILLED,
    RESOLVED_SL,
    RESOLVED_TIME,
    RESOLVED_TP,
    UNRESOLVED,
    TradePlan,
    resolve,
)
from strategy_engine.session import Candle

UTC = dt.timezone.utc
D0, D1 = dt.date(2025, 5, 5), dt.date(2025, 5, 6)
M15 = dt.timedelta(minutes=15)


def at(d, h, m=0):
    return dt.datetime.combine(d, dt.time(h, m), tzinfo=UTC)


def c(t, o, h, l, cl):
    return Candle(time=t, open=o, high=h, low=l, close=cl)


def warmup_day():
    """D0: oscillating M15 bars (ATR_H1 ~ 0.0020), no strict swings needed."""
    return [c(at(D0, 0) + i * M15, 1.1010, 1.1020, 1.1000, 1.1010) for i in range(96)]


def asian_and_morning(overrides):
    bars = {}
    for i in range(96):
        t = at(D1, 0) + i * M15
        bars[t] = c(t, 1.1010, 1.1020, 1.1000, 1.1010) if t < at(D1, 6) else c(t, 1.1008, 1.1012, 1.1003, 1.1008)
    for t, v in overrides.items():
        bars[t] = c(t, *v)
    return warmup_day() + [bars[t] for t in sorted(bars)]


def a_day():
    return asian_and_morning({
        at(D1, 6, 0): (1.1008, 1.1012, 1.1003, 1.1008), at(D1, 6, 15): (1.1008, 1.1013, 1.1003, 1.1009),
        at(D1, 6, 30): (1.1009, 1.1015, 1.1003, 1.1010), at(D1, 6, 45): (1.1010, 1.1012, 1.1003, 1.1008),
        at(D1, 7, 0): (1.1008, 1.1011, 1.1003, 1.1007),
        at(D1, 7, 15): (1.1007, 1.1010, 1.0990, 1.1005),      # sweeps the Asian low (1.1000), closes back inside
        at(D1, 7, 30): (1.1005, 1.1019, 1.1004, 1.1018),      # closes above the confirmed 06:30 swing high -> bullish break
    })


# --- families -------------------------------------------------------------------------


def test_family_a_sweep_then_reclaim():
    p = family_a(Market(a_day()), D1)
    assert p is not None and p.direction == "LONG" and p.entry_type == "MARKET"
    assert p.entry == 1.1018 and p.decision_time == at(D1, 7, 45)
    assert p.stop < 1.0990 and p.time_exit == at(D1, 12)
    assert p.target == pytest.approx(p.entry + 2 * (p.entry - p.stop))


def test_family_c_breakout_retest():
    bars = asian_and_morning({at(D1, 7, 0): (1.1015, 1.1030, 1.1014, 1.1026),   # closes above 1.1020
                              at(D1, 7, 15): (1.1026, 1.1027, 1.1018, 1.1024)})  # retests and holds
    p = family_c(Market(bars), D1)
    assert p is not None and p.direction == "LONG" and p.entry == 1.1024 and p.decision_time == at(D1, 7, 30)


def test_family_c_failed_breakout_is_no_trade():
    bars = asian_and_morning({at(D1, 7, 0): (1.1015, 1.1030, 1.1014, 1.1026),
                              at(D1, 7, 15): (1.1026, 1.1027, 1.1010, 1.1015)})  # closes back inside
    assert family_c(Market(bars), D1) is None


def test_family_b_gating_and_limit_geometry():
    mkt = Market(a_day())
    sweep_i = mkt.m15_times.index(at(D1, 8))
    mkt.m15_sweeps = [F.Sweep(sweep_i, 1.1000, sweep_i - 5, "bullish")]
    mkt.m15_fvgs = [F.FVG(sweep_i + 2, sweep_i + 3, 1.1012, 1.1006, "bullish")]
    mkt.h1_breaks = []
    assert family_b(mkt, D1) is None                      # neutral H1 bias -> no trade
    h1_i = next(i for i, b in enumerate(mkt.h1) if b.time == at(D1, 6))
    mkt.h1_breaks = [F.StructureBreak(h1_i, 1.1015, h1_i - 2, "CHoCH", "bullish")]
    p = family_b(mkt, D1)
    assert p is not None and p.entry_type == "LIMIT" and p.entry == 1.1012
    assert p.decision_time == mkt.m15[sweep_i + 3].time + M15
    assert p.order_expiry == p.decision_time + dt.timedelta(hours=3)
    mkt.h1_breaks = [F.StructureBreak(h1_i, 1.1015, h1_i - 2, "CHoCH", "bearish")]
    assert family_b(mkt, D1) is None                      # bias disagrees with the sweep


# --- resolver --------------------------------------------------------------------------


def plan(**kw):
    base = dict(family="T", trading_date=D1, direction="LONG", entry_type="MARKET", entry=1.1010,
                stop=1.1000, target=1.1030, decision_time=at(D1, 8), order_expiry=None, time_exit=at(D1, 9))
    base.update(kw)
    return TradePlan(**base)


def m5(start, end, ov=None, px=1.1010):
    ov = ov or {}
    out, t = [], start
    while t < end:
        out.append(ov.get(t, c(t, px, px + 0.0002, px - 0.0002, px)))
        t += dt.timedelta(minutes=5)
    return out


def test_prefill_bars_cannot_resolve():
    pre = [c(at(D1, 7, 55), 1.1010, 1.1011, 1.0990, 1.1010)]   # would hit SL, but opens before the fill
    assert resolve(plan(), pre + m5(at(D1, 8), at(D1, 9)), 5).state == RESOLVED_TIME


def test_sl_tp_ambiguous_and_time_exit():
    assert resolve(plan(), m5(at(D1, 8), at(D1, 9), {at(D1, 8, 30): c(at(D1, 8, 30), 1.101, 1.1011, 1.0999, 1.1)}), 5).state == RESOLVED_SL
    tp = resolve(plan(), m5(at(D1, 8), at(D1, 9), {at(D1, 8, 30): c(at(D1, 8, 30), 1.101, 1.1031, 1.1009, 1.103)}), 5)
    assert tp.state == RESOLVED_TP and tp.gross_R == pytest.approx(2.0) and tp.net_R == pytest.approx(2.0 - 0.3)
    assert resolve(plan(), m5(at(D1, 8), at(D1, 9), {at(D1, 8, 30): c(at(D1, 8, 30), 1.101, 1.1031, 1.0999, 1.1)}), 5).state == AMBIGUOUS
    te = resolve(plan(), m5(at(D1, 8), at(D1, 9), px=1.1015), 5)
    assert te.state == RESOLVED_TIME and te.gross_R == pytest.approx(0.5)


def test_missing_bar_is_unresolved():
    bars = [b for b in m5(at(D1, 8), at(D1, 9)) if b.time != at(D1, 8, 20)]
    assert resolve(plan(), bars, 5).state == UNRESOLVED


def test_limit_not_filled_and_ambiguous_fill_bar():
    lim = plan(entry_type="LIMIT", entry=1.1005, stop=1.0995, target=1.1025, order_expiry=at(D1, 8, 30))
    assert resolve(lim, m5(at(D1, 8), at(D1, 9)), 5).state == NOT_FILLED
    ov = {at(D1, 8, 10): c(at(D1, 8, 10), 1.101, 1.101, 1.0994, 1.1)}  # the fill bar also trades through the stop
    assert resolve(lim, m5(at(D1, 8), at(D1, 9), ov), 5).state == AMBIGUOUS
    ov = {at(D1, 8, 10): c(at(D1, 8, 10), 1.101, 1.101, 1.1004, 1.1006)}
    filled = resolve(lim, m5(at(D1, 8), at(D1, 9), ov), 5)
    assert filled.state == RESOLVED_TIME and filled.fill_time == at(D1, 8, 10).isoformat()


# --- causality: decisions reproduce from truncated data -------------------------------


def random_walk(days=12, seed=11):
    rng = random.Random(seed)
    px, out = 1.10, []
    t = at(dt.date(2025, 5, 5), 0)
    for _ in range(days * 288):
        o = px
        px += rng.gauss(0, 0.00012)
        hi, lo = max(o, px) + abs(rng.gauss(0, 0.00005)), min(o, px) - abs(rng.gauss(0, 0.00005))
        out.append(c(t, round(o, 5), round(hi, 5), round(lo, 5), round(px, 5)))
        t += dt.timedelta(minutes=5)
    return out


def test_every_plan_reproduces_from_data_truncated_at_its_decision_time():
    base = random_walk()
    full = Market(base)
    checked = 0
    for name, fn in FAMILIES.items():
        for d in sorted({b.time.date() for b in base})[2:]:
            p = fn(full, d)
            if p is None:
                continue
            cut = [b for b in base if b.time + dt.timedelta(minutes=5) <= p.decision_time]
            assert fn(Market(cut), d) == p, (name, d)
            checked += 1
    assert checked >= 5
