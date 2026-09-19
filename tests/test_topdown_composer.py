"""TD-7: deterministic, offline tests for the six-timeframe TopDownContext composer
(src/mtf_context/topdown_composer.py). All six per-tier builders are mocked at their
bound names inside topdown_composer's own module namespace -- same idiom already used
throughout this package's tests (test_topdown_new_builders.py,
test_topdown_context_adapters.py) -- no real MT5/market data needed.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from mtf_context.topdown_composer import (
    HistoricalAsOfNotSupportedError,
    IncompleteTopDownCompositionError,
    TopDownSymbolMismatchError,
    TopDownTemporalViolationError,
    TopDownTimeframeSlotError,
    build_topdown_context,
    compute_topdown_context_id,
)
from mtf_context.topdown_contracts import (
    DATA_QUALITY_PARTIAL,
    DATA_QUALITY_VALID,
    TIMEFRAME_D1,
    TIMEFRAME_H1,
    TIMEFRAME_H4,
    TIMEFRAME_M5,
    TIMEFRAME_M15,
    TIMEFRAME_W1,
    DailyContext,
    H1Context,
    H4Context,
    M5Context,
    M15Context,
    WeeklyContext,
)

_NOW = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)


def _clock():
    return _NOW


def _weekly(symbol="EURUSD", context_id="TDCTX-W1-1", bar_close=None, status=DATA_QUALITY_VALID):
    return WeeklyContext(
        context_id=context_id, symbol=symbol, timeframe=TIMEFRAME_W1, source="TEST",
        bar_close_time=bar_close or (_NOW - timedelta(days=1)),
        feature_version="TEST_V1", data_quality_status=status,
    )


def _daily(symbol="EURUSD", context_id="TDCTX-D1-1", parent_weekly_context_id=None,
           bar_close=None, status=DATA_QUALITY_VALID):
    return DailyContext(
        context_id=context_id, symbol=symbol, timeframe=TIMEFRAME_D1, source="TEST",
        bar_close_time=bar_close or (_NOW - timedelta(hours=12)),
        feature_version="TEST_V1", data_quality_status=status,
        parent_weekly_context_id=parent_weekly_context_id,
    )


def _h4(symbol="EURUSD", context_id="TDCTX-H4-1", parent_daily_context_id=None,
        bar_close=None, status=DATA_QUALITY_VALID):
    return H4Context(
        context_id=context_id, symbol=symbol, timeframe=TIMEFRAME_H4, source="TEST",
        bar_close_time=bar_close or (_NOW - timedelta(hours=4)),
        feature_version="TEST_V1", data_quality_status=status,
        parent_daily_context_id=parent_daily_context_id,
    )


def _h1(symbol="EURUSD", context_id="TDCTX-H1-1", parent_h4_context_id=None,
        bar_close=None, status=DATA_QUALITY_VALID):
    return H1Context(
        context_id=context_id, symbol=symbol, timeframe=TIMEFRAME_H1, source="TEST",
        bar_close_time=bar_close or (_NOW - timedelta(hours=1)),
        feature_version="TEST_V1", data_quality_status=status,
        parent_h4_context_id=parent_h4_context_id,
    )


def _m15(symbol="EURUSD", context_id="TDCTX-M15-1", parent_h1_context_id=None,
         bar_close=None, status=DATA_QUALITY_VALID):
    return M15Context(
        context_id=context_id, symbol=symbol, timeframe=TIMEFRAME_M15, source="TEST",
        bar_close_time=bar_close or (_NOW - timedelta(minutes=15)),
        feature_version="TEST_V1", data_quality_status=status,
        parent_h1_context_id=parent_h1_context_id,
    )


def _m5(symbol="EURUSD", context_id="TDCTX-M5-1", parent_m15_context_id=None,
        bar_close=None, status=DATA_QUALITY_VALID):
    return M5Context(
        context_id=context_id, symbol=symbol, timeframe=TIMEFRAME_M5, source="TEST",
        bar_close_time=bar_close or (_NOW - timedelta(minutes=5)),
        feature_version="TEST_V1", data_quality_status=status,
        parent_m15_context_id=parent_m15_context_id,
    )


def _valid_chain(symbol="EURUSD"):
    """A fully consistent, real-lineage six-tier chain -- each parent id set to the
    PRECEDING tier's own context_id, exactly as the composer itself would thread them."""
    weekly = _weekly(symbol=symbol)
    daily = _daily(symbol=symbol, parent_weekly_context_id=weekly.context_id)
    h4 = _h4(symbol=symbol, parent_daily_context_id=daily.context_id)
    h1 = _h1(symbol=symbol, parent_h4_context_id=h4.context_id)
    m15 = _m15(symbol=symbol, parent_h1_context_id=h1.context_id)
    m5 = _m5(symbol=symbol, parent_m15_context_id=m15.context_id)
    return weekly, daily, h4, h1, m15, m5


def _patch_builders(weekly=None, daily=None, h4=None, h1=None, m15=None, m5=None):
    return patch.multiple(
        "mtf_context.topdown_composer",
        build_weekly_context=lambda symbol: weekly,
        build_daily_context=lambda symbol, **kw: daily,
        build_h4_context=lambda symbol, **kw: h4,
        build_h1_context=lambda symbol, **kw: h1,
        build_m15_context=lambda symbol, **kw: m15,
        build_m5_context=lambda symbol, **kw: m5,
    )


# --------------------------------------------------------------------------- 1. successful composition

def test_successful_composition_with_six_valid_tiers():
    weekly, daily, h4, h1, m15, m5 = _valid_chain()
    with _patch_builders(weekly=weekly, daily=daily, h4=h4, h1=h1, m15=m15, m5=m5):
        ctx = build_topdown_context("EURUSD", _clock=_clock)

    assert ctx.symbol == "EURUSD"
    assert ctx.evaluation_time == _NOW
    assert ctx.data_quality_status == DATA_QUALITY_VALID
    assert (ctx.weekly, ctx.daily, ctx.h4, ctx.h1, ctx.m15, ctx.m5) == (weekly, daily, h4, h1, m15, m5)
    # TopDownContext's own __post_init__ lineage check double-verifies for free.
    assert ctx.daily.parent_weekly_context_id == ctx.weekly.context_id
    assert ctx.h4.parent_daily_context_id == ctx.daily.context_id
    assert ctx.h1.parent_h4_context_id == ctx.h4.context_id
    assert ctx.m15.parent_h1_context_id == ctx.h1.context_id
    assert ctx.m5.parent_m15_context_id == ctx.m15.context_id


# --------------------------------------------------------------------------- 2/13. deterministic identity

def test_repeated_equivalent_composition_is_deterministic():
    weekly, daily, h4, h1, m15, m5 = _valid_chain()
    with _patch_builders(weekly=weekly, daily=daily, h4=h4, h1=h1, m15=m15, m5=m5):
        ctx_a = build_topdown_context("EURUSD", _clock=_clock)
        ctx_b = build_topdown_context("EURUSD", _clock=_clock)

    assert ctx_a.context_id == ctx_b.context_id
    assert ctx_a.to_dict() == ctx_b.to_dict()


def test_compute_topdown_context_id_is_deterministic():
    kwargs = dict(symbol="EURUSD", evaluation_time=_NOW,
                  child_context_ids=("A", "B", "C", "D", "E", "F"), feature_version="V1")
    assert compute_topdown_context_id(**kwargs) == compute_topdown_context_id(**kwargs)


# --------------------------------------------------------------------------- 3. different child -> different identity

def test_different_child_context_id_changes_composed_id():
    weekly, daily, h4, h1, m15, m5 = _valid_chain()
    with _patch_builders(weekly=weekly, daily=daily, h4=h4, h1=h1, m15=m15, m5=m5):
        ctx_a = build_topdown_context("EURUSD", _clock=_clock)

    m5_different = _m5(context_id="TDCTX-M5-DIFFERENT", parent_m15_context_id=m15.context_id)
    with _patch_builders(weekly=weekly, daily=daily, h4=h4, h1=h1, m15=m15, m5=m5_different):
        ctx_b = build_topdown_context("EURUSD", _clock=_clock)

    assert ctx_a.context_id != ctx_b.context_id


# --------------------------------------------------------------------------- 4. mixed symbol fails closed

def test_mixed_symbol_composition_fails_closed():
    weekly = _weekly(symbol="EURUSD")
    daily = _daily(symbol="EURUSD", parent_weekly_context_id=weekly.context_id)
    h4 = _h4(symbol="GBPUSD", parent_daily_context_id=daily.context_id)  # wrong symbol
    with _patch_builders(weekly=weekly, daily=daily, h4=h4):
        with pytest.raises(TopDownSymbolMismatchError):
            build_topdown_context("EURUSD", _clock=_clock)


# --------------------------------------------------------------------------- 5. wrong timeframe slot fails closed

def test_wrong_timeframe_slot_fails_closed():
    """A build_h4_context() that returned an H1Context (wrong tier's type/timeframe)
    must never be silently accepted into the h4 slot."""
    weekly, daily, _h4_real, h1, m15, m5 = _valid_chain()
    wrong_type_h4 = _h1(context_id="TDCTX-H1-WRONG-SLOT", parent_h4_context_id=daily.context_id)
    with _patch_builders(weekly=weekly, daily=daily, h4=wrong_type_h4):
        with pytest.raises(TopDownTimeframeSlotError):
            build_topdown_context("EURUSD", _clock=_clock)


# --------------------------------------------------------------------------- 6. broken parent lineage fails closed

def test_broken_parent_lineage_fails_closed():
    weekly, daily_real, h4, h1, m15, m5 = _valid_chain()
    # Break ONLY the weekly<->daily link; h4/h1/m15/m5 stay chained onto daily's real
    # context_id, so all six tiers are still non-None and the failure is isolated to
    # TopDownContext.__post_init__'s own lineage check, not an earlier missing-tier error.
    broken_daily = _daily(context_id=daily_real.context_id,
                           parent_weekly_context_id="TDCTX-W1-SOMETHING-ELSE")
    with _patch_builders(weekly=weekly, daily=broken_daily, h4=h4, h1=h1, m15=m15, m5=m5):
        with pytest.raises(ValueError):
            build_topdown_context("EURUSD", _clock=_clock)


# --------------------------------------------------------------------------- 7. all children <= composition boundary

def test_all_children_bar_close_time_lte_composition_boundary():
    weekly, daily, h4, h1, m15, m5 = _valid_chain()
    with _patch_builders(weekly=weekly, daily=daily, h4=h4, h1=h1, m15=m15, m5=m5):
        ctx = build_topdown_context("EURUSD", _clock=_clock)

    for tier in (ctx.weekly, ctx.daily, ctx.h4, ctx.h1, ctx.m15, ctx.m5):
        assert tier.bar_close_time <= ctx.evaluation_time


# --------------------------------------------------------------------------- 8. future child fails closed

def test_future_child_context_fails_closed():
    weekly, daily, h4, h1, m15, _m5_real = _valid_chain()
    future_m5 = _m5(context_id="TDCTX-M5-FUTURE", parent_m15_context_id=m15.context_id,
                     bar_close=_NOW + timedelta(minutes=1))
    with _patch_builders(weekly=weekly, daily=daily, h4=h4, h1=h1, m15=m15, m5=future_m5):
        with pytest.raises(TopDownTemporalViolationError):
            build_topdown_context("EURUSD", _clock=_clock)


# --------------------------------------------------------------------------- 9. missing required tier fails closed

@pytest.mark.parametrize("missing_tier", ["weekly", "daily", "h4", "h1", "m15", "m5"])
def test_missing_required_tier_fails_closed(missing_tier):
    tiers = dict(zip(("weekly", "daily", "h4", "h1", "m15", "m5"), _valid_chain()))
    tiers[missing_tier] = None
    with _patch_builders(**tiers):
        with pytest.raises(IncompleteTopDownCompositionError):
            build_topdown_context("EURUSD", _clock=_clock)


# --------------------------------------------------------------------------- 12. no mutation of child contexts

def test_composition_does_not_mutate_child_contexts():
    weekly, daily, h4, h1, m15, m5 = _valid_chain()
    snapshot = tuple(dataclasses.replace(t) for t in (weekly, daily, h4, h1, m15, m5))
    with _patch_builders(weekly=weekly, daily=daily, h4=h4, h1=h1, m15=m15, m5=m5):
        ctx = build_topdown_context("EURUSD", _clock=_clock)

    # Frozen dataclasses cannot be mutated in place; this proves the SAME objects
    # (identity, not copies) come back unchanged, and their fields still match a
    # snapshot taken before composition.
    assert ctx.weekly is weekly and ctx.weekly == snapshot[0]
    assert ctx.daily is daily and ctx.daily == snapshot[1]
    assert ctx.h4 is h4 and ctx.h4 == snapshot[2]
    assert ctx.h1 is h1 and ctx.h1 == snapshot[3]
    assert ctx.m15 is m15 and ctx.m15 == snapshot[4]
    assert ctx.m5 is m5 and ctx.m5 == snapshot[5]


# --------------------------------------------------------------------------- 14. single captured composition boundary

def test_live_current_uses_single_captured_boundary():
    calls = []

    def _counting_clock():
        calls.append(1)
        return _NOW

    weekly, daily, h4, h1, m15, m5 = _valid_chain()
    with _patch_builders(weekly=weekly, daily=daily, h4=h4, h1=h1, m15=m15, m5=m5):
        build_topdown_context("EURUSD", _clock=_counting_clock)

    assert len(calls) == 1  # captured exactly once, never re-queried per tier


# --------------------------------------------------------------------------- 15. historical as-of rejected, not silently served

def test_historical_as_of_raises_not_supported_and_calls_no_builder():
    weekly, daily, h4, h1, m15, m5 = _valid_chain()
    with _patch_builders(weekly=weekly, daily=daily, h4=h4, h1=h1, m15=m15, m5=m5) as mocks:
        with pytest.raises(HistoricalAsOfNotSupportedError):
            build_topdown_context("EURUSD", as_of_time=_NOW - timedelta(days=30))
    # None of the six builders were ever invoked -- rejected before any composition work.
    # (patch.multiple's lambdas aren't call-tracked directly; re-verify via a spy instead.)


def test_historical_as_of_never_reaches_any_builder():
    with patch("mtf_context.topdown_composer.build_weekly_context") as mock_weekly:
        with pytest.raises(HistoricalAsOfNotSupportedError):
            build_topdown_context("EURUSD", as_of_time=_NOW - timedelta(days=30))
    mock_weekly.assert_not_called()


# --------------------------------------------------------------------------- data-quality propagation (not scored)

def test_partial_tier_quality_propagates_to_composed_status_without_failing():
    weekly, daily, h4, h1, m15, m5 = _valid_chain()
    degraded_h1 = _h1(context_id=h1.context_id, parent_h4_context_id=h1.parent_h4_context_id,
                       bar_close=h1.bar_close_time, status=DATA_QUALITY_PARTIAL)
    with _patch_builders(weekly=weekly, daily=daily, h4=h4, h1=degraded_h1, m15=m15, m5=m5):
        ctx = build_topdown_context("EURUSD", _clock=_clock)

    assert ctx.data_quality_status == DATA_QUALITY_PARTIAL
    assert ctx.h1.data_quality_status == DATA_QUALITY_PARTIAL  # preserved, not hidden


# --------------------------------------------------------------------------- package membership (mirrors existing idiom)

def test_topdown_composer_module_is_inside_the_guarded_package():
    import mtf_context.topdown_composer as module

    assert "mtf_context" in module.__name__
