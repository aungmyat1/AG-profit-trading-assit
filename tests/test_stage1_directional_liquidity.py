"""Tests for the directional HTF liquidity contract (historical_replay.stage1):
DirectionalLiquidityTimeline / lookup(direction, t). Regression for the diagnosed
Stage-1 scope bug: M3's liquidity_level is direction-scoped and shared across E1/E2/E3
(confirmed by call-graph audit of conditional_entry_snapshot.py:222-256), not owned
by E3 alone.
"""
from __future__ import annotations

import datetime as dt

from historical_replay.stage1 import DirectionalLiquidityInterval, DirectionalLiquidityTimeline
from historical_replay.stage2 import Stage1LiquidityReference

UTC = dt.timezone.utc


def _ref(price, source="PDH", side="BUY_SIDE"):
    return Stage1LiquidityReference(symbol="EURUSD", timeframe="H1", side=side, source=source,
                                    price=price, origin_time=None, status="SWEPT",
                                    sweep_time=dt.datetime(2026, 1, 1, tzinfo=UTC), reclaim_time=None)


# --------------------------------------------------------------------------- lookup basics

def test_lookup_short_uses_buy_side():
    ref = _ref(1.1)
    tl = DirectionalLiquidityTimeline(
        buy=(DirectionalLiquidityInterval(dt.datetime(2026, 1, 1, tzinfo=UTC), dt.datetime(2026, 1, 2, tzinfo=UTC), ref),),
        sell=(),
    )
    assert tl.lookup("SHORT", dt.datetime(2026, 1, 1, 12, tzinfo=UTC)) is ref


def test_lookup_long_uses_sell_side():
    ref = _ref(1.1, side="SELL_SIDE")
    tl = DirectionalLiquidityTimeline(
        buy=(), sell=(DirectionalLiquidityInterval(dt.datetime(2026, 1, 1, tzinfo=UTC), dt.datetime(2026, 1, 2, tzinfo=UTC), ref),),
    )
    assert tl.lookup("LONG", dt.datetime(2026, 1, 1, 12, tzinfo=UTC)) is ref


# --------------------------------------------------------------------------- transition (A != B over time)

def test_directional_reference_transitions_over_time():
    ref_a, ref_b = _ref(1.10, source="PDH"), _ref(1.20, source="PWH")
    tl = DirectionalLiquidityTimeline(
        buy=(
            DirectionalLiquidityInterval(dt.datetime(2026, 1, 1, tzinfo=UTC), dt.datetime(2026, 1, 2, tzinfo=UTC), ref_a),
            DirectionalLiquidityInterval(dt.datetime(2026, 1, 2, tzinfo=UTC), dt.datetime(2026, 1, 3, tzinfo=UTC), ref_b),
        ),
        sell=(),
    )
    t1 = dt.datetime(2026, 1, 1, 12, tzinfo=UTC)
    t2 = dt.datetime(2026, 1, 2, 12, tzinfo=UTC)
    assert tl.lookup("SHORT", t1) == ref_a
    assert tl.lookup("SHORT", t2) == ref_b
    assert tl.lookup("SHORT", t1) != tl.lookup("SHORT", t2)


# --------------------------------------------------------------------------- gap (no fallback/backfill)

def test_gap_returns_none_no_fallback():
    ref = _ref(1.1)
    tl = DirectionalLiquidityTimeline(
        buy=(
            DirectionalLiquidityInterval(dt.datetime(2026, 1, 1, tzinfo=UTC), dt.datetime(2026, 1, 1, 12, tzinfo=UTC), ref),
            # explicit gap: no interval from 12:00 to 18:00
            DirectionalLiquidityInterval(dt.datetime(2026, 1, 1, 18, tzinfo=UTC), dt.datetime(2026, 1, 2, tzinfo=UTC), ref),
        ),
        sell=(),
    )
    assert tl.lookup("SHORT", dt.datetime(2026, 1, 1, 15, tzinfo=UTC)) is None


def test_explicit_none_interval_returns_none_not_error():
    tl = DirectionalLiquidityTimeline(
        buy=(DirectionalLiquidityInterval(dt.datetime(2026, 1, 1, tzinfo=UTC), dt.datetime(2026, 1, 2, tzinfo=UTC), None),),
        sell=(),
    )
    assert tl.lookup("SHORT", dt.datetime(2026, 1, 1, 12, tzinfo=UTC)) is None


# --------------------------------------------------------------------------- no lookahead

def test_reference_not_visible_before_its_own_interval_starts():
    """A reference that becomes available at t2 must not be visible at t1 < t2."""
    ref_b = _ref(1.20, source="PWH")
    tl = DirectionalLiquidityTimeline(
        buy=(DirectionalLiquidityInterval(dt.datetime(2026, 1, 2, tzinfo=UTC), dt.datetime(2026, 1, 3, tzinfo=UTC), ref_b),),
        sell=(),
    )
    t1_before = dt.datetime(2026, 1, 1, 23, 59, tzinfo=UTC)
    assert tl.lookup("SHORT", t1_before) is None  # not yet visible
    assert tl.lookup("SHORT", dt.datetime(2026, 1, 2, tzinfo=UTC)) == ref_b  # visible exactly at start


def test_real_reconstructed_timeline_round_trips_and_matches_e3_payload():
    """Persistence round-trip + the known-regression consumer proof: the directional
    lookup at the exact E1M3/E3M3 shared timestamp must agree (on the fields M3 reads)
    with the E3 event's own independently-enriched liquidity reference."""
    import pickle

    from historical_replay.stage1 import load_directional_liquidity_timeline

    timeline = load_directional_liquidity_timeline("artifacts/backtests/directional_liquidity_timeline.json")
    t = dt.datetime(2025, 9, 15, 12, 10, tzinfo=UTC)
    looked_up = timeline.lookup("SHORT", t)
    assert looked_up is not None

    with open("artifacts/backtests/stage1_events_enriched.pkl", "rb") as f:
        enriched = pickle.load(f)
    e3_own = next(e.liquidity_reference for e in enriched
                 if e.entry_condition == "E3" and e.reference_key == "PWH|None|None|1.1765")

    assert looked_up.side == e3_own.side
    assert looked_up.price == e3_own.price
    assert looked_up.source == e3_own.source


def test_boundary_end_exclusive():
    ref = _ref(1.1)
    tl = DirectionalLiquidityTimeline(
        buy=(DirectionalLiquidityInterval(dt.datetime(2026, 1, 1, tzinfo=UTC), dt.datetime(2026, 1, 1, 1, tzinfo=UTC), ref),),
        sell=(),
    )
    assert tl.lookup("SHORT", dt.datetime(2026, 1, 1, 1, tzinfo=UTC)) is None
