"""AG canonical causal features. Expected values come from the parity harness run
(docs/research/FX_DISCOVERY_V1_SEMANTIC_PARITY.md), where AG == smc-mcp except for the
documented sweep look-ahead correction."""
from __future__ import annotations

import datetime as dt

from fx_discovery import features as F
from strategy_engine.session import Candle

T0 = dt.datetime(2025, 5, 5, tzinfo=dt.timezone.utc)
K = 2


def mk(ohlc):
    return [Candle(time=T0 + dt.timedelta(minutes=15 * i), open=o, high=h, low=l, close=c)
            for i, (o, h, l, c) in enumerate(ohlc)]


def flat(p, n):
    return [(p, p + 2, p - 2, p)] * n


BOS_UP = flat(100, 2) + [(100, 104, 99, 103), (103, 108, 102, 104), (104, 105, 100, 101), (101, 103, 99, 102),
                         (102, 112, 101, 111), (111, 115, 110, 112), (112, 113, 107, 108), (108, 110, 106, 109),
                         (109, 120, 108, 119)] + flat(119, 2)
CHOCH_DOWN = flat(100, 2) + [(100, 104, 99, 103), (103, 108, 102, 104), (104, 105, 100, 101), (101, 103, 99, 102),
                             (102, 112, 101, 111), (111, 115, 110, 112), (112, 113, 104, 105), (105, 109, 103, 108),
                             (108, 109, 104, 106), (106, 107, 95, 96)] + flat(96, 2)
WICK_SWEEP = flat(100, 3) + [(100, 101, 95, 96), (96, 97, 90, 94), (94, 99, 93, 98), (98, 102, 97, 101),
                             (101, 102, 99, 100), (100, 101, 88, 95)] + flat(96, 2)
CLOSE_THROUGH = WICK_SWEEP[:8] + [(100, 101, 86, 87)] + flat(87, 2)


def test_swing_confirmation_is_delayed_by_k():
    sw = F.swings(mk(BOS_UP), K)
    assert [(s.index, s.known_at, s.kind, s.price) for s in sw] == [
        (3, 5, "high", 108), (5, 7, "low", 99), (7, 9, "high", 115), (9, 11, "low", 106)]


def test_equal_highs_are_not_swings():
    bars = mk(flat(100, 3) + [(100, 110, 99, 105), (105, 106, 100, 101), (101, 110, 100, 104), (104, 105, 98, 99)] + flat(99, 3))
    assert F.swings(bars, K) == []


def test_forming_edge_bar_is_not_a_swing():
    bars = mk(flat(100, 4) + [(100, 105, 99, 104), (104, 110, 103, 106), (106, 107, 101, 102)])
    assert F.swings(bars, K) == []


def test_bos_and_choch_are_close_through():
    bars = mk(BOS_UP)
    assert [(b.index, b.event, b.direction) for b in F.structure_breaks(bars, F.swings(bars, K))] == [
        (6, "CHoCH", "bullish"), (10, "BOS", "bullish")]
    bars = mk(CHOCH_DOWN)
    assert [(b.index, b.event, b.direction) for b in F.structure_breaks(bars, F.swings(bars, K))] == [
        (6, "CHoCH", "bullish"), (11, "CHoCH", "bearish")]


def test_wick_sweep_vs_close_through():
    bars = mk(WICK_SWEEP)
    assert [(s.index, s.direction, s.level) for s in F.sweeps(bars, F.swings(bars, K))] == [(8, "bullish", 90)]
    bars = mk(CLOSE_THROUGH)
    sw = F.swings(bars, K)
    assert F.sweeps(bars, sw) == []
    assert [(b.index, b.direction) for b in F.structure_breaks(bars, sw)] == [(8, "bearish")]


def test_sweep_only_of_confirmed_swings():
    """smc-mcp compares against the unconfirmed 115 swing here and misses this; AG sweeps the confirmed 108."""
    bars = mk(CHOCH_DOWN)
    assert [(s.index, s.direction, s.level) for s in F.sweeps(bars, F.swings(bars, K))] == [(8, "bearish", 108)]


def test_fvg_known_one_bar_after_middle():
    bars = mk(flat(100, 3) + [(100, 101, 99, 100.5), (100.5, 108, 100.5, 107.5), (107.5, 110, 103, 109)] + flat(109, 3))
    assert [(f.index, f.known_at, f.direction, f.top, f.bottom) for f in F.fvgs(bars)] == [(4, 5, "bullish", 103, 101)]


def test_future_mutation_cannot_change_known_features():
    base = mk(BOS_UP)
    cut = 9
    mutated = base[:cut + 1] + [Candle(time=b.time, open=b.open * 3, high=b.high * 3, low=b.low * 0.1, close=b.close * 2)
                                for b in base[cut + 1:]]

    def known(bars):
        sw = F.swings(bars, K)
        return ([s for s in sw if s.known_at <= cut], [b for b in F.structure_breaks(bars, sw) if b.index <= cut],
                [s for s in F.sweeps(bars, sw) if s.index <= cut], [f for f in F.fvgs(bars) if f.known_at <= cut])
    assert known(base) == known(mutated)


def test_atr_and_ema_seeding():
    bars = mk([(1.0, 1.0 + i * 0.001, 1.0 - 0.001, 1.0) for i in range(1, 20)])
    a = F.atr(bars, 14)
    assert a[12] is None and a[13] is not None and a[14] is not None
    e = F.ema([float(i) for i in range(1, 11)], 5)
    assert e[3] is None and e[4] == 3.0 and abs(e[5] - (2 / 6 * 6 + 4 / 6 * 3.0)) < 1e-12
