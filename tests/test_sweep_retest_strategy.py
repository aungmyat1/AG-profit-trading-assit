"""Tests for ST_SESSION_SWEEP_RETEST_V1 (strategy_engine.sweep_retest).

Deterministic synthetic fixtures only, no MT5/live connection -- same idiom as
tests/test_session_router.py and tests/test_market_structure.py. Every fixture below only
ever looks at candles up to and including the one that produces the decision under test,
mirroring the lookahead discipline documented in session/setups.py.
"""
from __future__ import annotations

import datetime as dt
from datetime import time

import pytest

from execution.daily_loss_guard import DailyLossGuard
from execution.position_guard import OpenPositionGuard
from market_structure.models import MarketStructureConfig
from mt5.symbol_resolver import SymbolMeta
from runtime_state.store import JsonKeyValueStore
from strategy_engine.session import Candle
from strategy_engine.sweep_retest.engine import (
    SweepRetestRuntime,
    evaluate_setup,
    transition_order_submitted,
    transition_position_open,
    transition_runner_active,
    transition_tp1_hit,
)
from strategy_engine.sweep_retest.mss import MSS_BEARISH, find_mss
from strategy_engine.sweep_retest.models import (
    STATE_BLOCKED_DAILY_LOSS,
    STATE_BLOCKED_OPEN_POSITION,
    STATE_ENTRY_READY,
    STATE_NO_TRADE_DIRECTION,
    STATE_NO_TRADE_TARGET_GEOMETRY,
    STATE_POSITION_OPEN,
    STATE_RUNNER_ACTIVE,
    STATE_SETUP_EXPIRED,
    STATE_TP1_HIT,
    STATE_WAITING_MSS,
    STATE_WAITING_RETEST,
)
from strategy_engine.sweep_retest.retest import find_retest
from strategy_engine.sweep_retest.state_store import SweepRetestStateStore
from strategy_engine.sweep_retest.sweep import SWEEP_HIGH, SWEEP_LOW, find_qualified_sweep
from strategy_engine.sweep_retest.targets import build_target_plan
from strategy_engine.sweep_retest.trend import h1_trend_direction

UTC = dt.timezone.utc
CFG = MarketStructureConfig(swing_length=1, close_break=True, default_analysis_count=50)

LONDON_WINDOW = (time(7, 0), time(10, 0))

EURUSD_META = SymbolMeta(
    symbol="EURUSD", tick_size=0.00001, tick_value=1.0, contract_size=100000,
    volume_min=0.01, volume_max=50.0, volume_step=0.01, digits=5, point=0.00001,
)


def _c(minute, o, h, l, cl, hour=7):
    return Candle(time=dt.datetime(2026, 1, 5, hour, minute, tzinfo=UTC), open=o, high=h, low=l, close=cl, volume=1.0)


# The validated fixture: a HIGH sweep of AsianHigh=1.1050, swing low ~1.0940 located
# before the sweep, MSS confirms on the 3rd post-sweep candle (07:30, after one
# intrabar-only penetration at 07:20 that must NOT confirm), retest at 07:35.
def _short_sequence():
    return [
        _c(0, 1.1000, 1.1005, 1.0995, 1.1000),
        _c(5, 1.0980, 1.0985, 1.0940, 1.0950),   # swing low candidate ~1.0940
        _c(10, 1.0960, 1.1010, 1.0955, 1.1005),  # rally
        _c(15, 1.1005, 1.1080, 1.0900, 1.0910),  # SWEEP: high>1.1050, close<1.1050
        _c(20, 1.0910, 1.0950, 1.0930, 1.0945),  # intrabar only: low<1.0940, close above
        _c(25, 1.0945, 1.0950, 1.0935, 1.0942),  # still above
        _c(30, 1.0942, 1.0945, 1.0890, 1.0895),  # closes below 1.0940 -> MSS confirmed
        _c(35, 1.0895, 1.0945, 1.0890, 1.0900),  # retest: high 1.0945 >= 1.0940
        _c(40, 1.0900, 1.0905, 1.0850, 1.0860),
    ]


def _descending_zigzag_h1(cycles=25, trend_step=0.0100, amplitude=0.0300):
    prices = []
    for i in range(cycles):
        high = 1.2000 - i * trend_step
        prices.append(high)
        prices.append(high - amplitude)
    return prices


def _ascending_zigzag_h1(cycles=25, trend_step=0.0100, amplitude=0.0300):
    prices = []
    for i in range(cycles):
        low = 1.1000 + i * trend_step
        prices.append(low)
        prices.append(low + amplitude)
    return prices


def _h1_candles(prices, step_minutes=60):
    out, t = [], dt.datetime(2026, 1, 1, tzinfo=UTC)
    for p in prices:
        out.append(Candle(time=t, open=p, high=p + 0.0005, low=p - 0.0005, close=p, volume=1.0))
        t += dt.timedelta(minutes=step_minutes)
    return out


H1_BEARISH = _h1_candles(_descending_zigzag_h1())
H1_BULLISH = _h1_candles(_ascending_zigzag_h1())

ASIAN_HIGH, ASIAN_LOW = 1.1050, 1.0700


def _asian_candles():
    return [Candle(time=dt.datetime(2026, 1, 5, 3, 0, tzinfo=UTC), open=1.0900, high=ASIAN_HIGH, low=ASIAN_LOW, close=1.0900, volume=1.0)]


# --------------------------------------------------------------------------- 1/2/3: sweep

def test_valid_high_sweep_detected():
    candles = _short_sequence()
    sweep = find_qualified_sweep(candles, ASIAN_HIGH, ASIAN_LOW)
    assert sweep is not None
    assert sweep.direction == SWEEP_HIGH
    assert sweep.extreme_price == pytest.approx(1.1080)


def test_valid_low_sweep_detected():
    candle = _c(15, 1.0750, 1.0760, 1.0650, 1.0720)  # low<AsianLow(1.0700), close>AsianLow
    sweep = find_qualified_sweep([candle], ASIAN_HIGH, ASIAN_LOW)
    assert sweep is not None
    assert sweep.direction == SWEEP_LOW
    assert sweep.extreme_price == pytest.approx(1.0650)


def test_wick_outside_but_close_also_outside_is_not_a_sweep():
    # high > AsianHigh, but close does NOT come back inside -- not a qualified sweep.
    candle = _c(15, 1.1005, 1.1080, 1.1055, 1.1070)
    sweep = find_qualified_sweep([candle], ASIAN_HIGH, ASIAN_LOW)
    assert sweep is None


# --------------------------------------------------------------------------- 4/5: H1 gating

def test_high_sweep_rejected_by_bullish_h1_direction():
    assert h1_trend_direction(H1_BULLISH, CFG) == "LONG_ONLY"
    candles = _short_sequence()  # contains only a HIGH sweep candle
    sweep = find_qualified_sweep(candles, ASIAN_HIGH, ASIAN_LOW, required_direction=SWEEP_LOW)
    assert sweep is None


def test_low_sweep_rejected_by_bearish_h1_direction():
    assert h1_trend_direction(H1_BEARISH, CFG) == "SHORT_ONLY"
    candle = _c(15, 1.0850, 1.0860, 1.0750, 1.0820)  # a LOW sweep candle only
    sweep = find_qualified_sweep([candle], ASIAN_HIGH, ASIAN_LOW, required_direction=SWEEP_HIGH)
    assert sweep is None


# --------------------------------------------------------------------------- 6/7: MSS

def test_mss_requires_m5_close_beyond_swing():
    candles = _short_sequence()
    sweep = find_qualified_sweep(candles, ASIAN_HIGH, ASIAN_LOW)
    up_to = [x for x in candles if x.time <= sweep.candle_time]
    after = [x for x in candles if x.time > sweep.candle_time]
    mss = find_mss(sweep, up_to, after, CFG)
    assert mss is not None
    assert mss.kind == MSS_BEARISH
    assert mss.broken_swing_price == pytest.approx(1.0940)
    assert mss.confirmed_at == dt.datetime(2026, 1, 5, 7, 30, tzinfo=UTC)


def test_intrabar_swing_penetration_does_not_confirm_mss():
    candles = _short_sequence()
    sweep = find_qualified_sweep(candles, ASIAN_HIGH, ASIAN_LOW)
    up_to = [x for x in candles if x.time <= sweep.candle_time]
    # Only the intrabar-only candle (07:20: low 1.0930 < swing 1.0940, close 1.0945 above)
    intrabar_only = [x for x in candles if x.time == dt.datetime(2026, 1, 5, 7, 20, tzinfo=UTC)]
    mss = find_mss(sweep, up_to, intrabar_only, CFG)
    assert mss is None


# --------------------------------------------------------------------------- 8/9: retest

def test_valid_retest_found_within_ttl():
    candles = _short_sequence()
    sweep = find_qualified_sweep(candles, ASIAN_HIGH, ASIAN_LOW)
    up_to = [x for x in candles if x.time <= sweep.candle_time]
    after = [x for x in candles if x.time > sweep.candle_time]
    mss = find_mss(sweep, up_to, after, CFG)
    after_mss = [x for x in candles if x.time > mss.confirmed_at]
    retest = find_retest(mss, after_mss)
    assert retest is not None
    assert retest.entry_price == pytest.approx(1.0940)
    assert retest.bars_after_mss == 1


def test_retest_ttl_expiry_when_no_retest_within_3_bars():
    mss = find_mss(
        find_qualified_sweep(_short_sequence(), ASIAN_HIGH, ASIAN_LOW),
        [x for x in _short_sequence() if x.time <= dt.datetime(2026, 1, 5, 7, 15, tzinfo=UTC)],
        [x for x in _short_sequence() if dt.datetime(2026, 1, 5, 7, 15, tzinfo=UTC) < x.time],
        CFG,
    )
    # 3 candles after MSS that never reach the broken swing (1.0940), then a 4th that
    # would touch it but arrives too late.
    late_candles = [
        _c(35, 1.0895, 1.0900, 1.0880, 1.0890),
        _c(40, 1.0890, 1.0900, 1.0870, 1.0885),
        _c(45, 1.0885, 1.0900, 1.0860, 1.0880),
        _c(50, 1.0880, 1.0945, 1.0870, 1.0900),  # would retest, but this is bar #4
    ]
    retest = find_retest(mss, late_candles)
    assert retest is None


# --------------------------------------------------------------------------- 10: SL

def test_correct_sweep_extreme_stop_loss_short():
    plan = build_target_plan("SHORT", entry=1.0940, sweep_extreme=1.1080, asian_mid=1.0925,
                              asian_high=ASIAN_HIGH, asian_low=ASIAN_LOW, symbol_meta=EURUSD_META)
    assert plan.stop_loss == pytest.approx(1.1080 + 2.5 * 0.0001)


def test_correct_sweep_extreme_stop_loss_long():
    plan = build_target_plan("LONG", entry=1.0810, sweep_extreme=1.0750, asian_mid=1.0925,
                              asian_high=ASIAN_HIGH, asian_low=ASIAN_LOW, symbol_meta=EURUSD_META)
    assert plan.stop_loss == pytest.approx(1.0750 - 2.5 * 0.0001)


# --------------------------------------------------------------------------- 11/12: geometry guard

def test_invalid_tp1_geometry_rejected_short():
    # TP1 (asian_mid) is ABOVE entry for a SHORT -- invalid geometry.
    plan = build_target_plan("SHORT", entry=1.0900, sweep_extreme=1.1080, asian_mid=1.0950,
                              asian_high=ASIAN_HIGH, asian_low=ASIAN_LOW, symbol_meta=EURUSD_META)
    assert plan.status == "NO_TRADE_TARGET_GEOMETRY"


def test_tp2_below_minimum_r_multiple_rejected():
    # Small reward relative to a wide sweep-buffer stop -> R < 1.5.
    plan = build_target_plan("SHORT", entry=1.0940, sweep_extreme=1.1080, asian_mid=1.0925,
                              asian_high=ASIAN_HIGH, asian_low=1.0930, symbol_meta=EURUSD_META)
    assert plan.status == "NO_TRADE_TARGET_GEOMETRY"


def test_valid_geometry_accepted_with_sufficient_r():
    plan = build_target_plan("SHORT", entry=1.0940, sweep_extreme=1.1080, asian_mid=1.0925,
                              asian_high=ASIAN_HIGH, asian_low=ASIAN_LOW, symbol_meta=EURUSD_META)
    assert plan.status == "VALID"
    assert plan.tp2_r_multiple >= 1.5


# --------------------------------------------------------------------------- 13/14: TP1/breakeven transitions

def test_tp1_50_percent_transition():
    from strategy_engine.sweep_retest.models import SetupState
    state = SetupState(setup_id="s1", strategy_id="ST", symbol="EURUSD", state=STATE_POSITION_OPEN,
                        reason_code="POSITION_OPEN", entry=1.0940, stop_loss=1.1105)
    result = transition_tp1_hit(state, tp1_volume_pct=0.5)
    assert result.state == STATE_TP1_HIT
    assert result.evidence["tp1_close_pct"] == 0.5
    assert result.evidence["sl_moved_to_breakeven"] is True


def test_breakeven_moves_stop_to_entry():
    from strategy_engine.sweep_retest.models import SetupState
    state = SetupState(setup_id="s1", strategy_id="ST", symbol="EURUSD", state=STATE_TP1_HIT,
                        reason_code="TP1_REACHED", entry=1.0940, stop_loss=1.1105)
    result = transition_runner_active(state)
    assert result.state == STATE_RUNNER_ACTIVE
    assert result.stop_loss == pytest.approx(1.0940)


# --------------------------------------------------------------------------- 15/16/17: guards

def test_one_open_position_blocks_new_entry(tmp_path):
    guard = OpenPositionGuard(JsonKeyValueStore(str(tmp_path / "open_positions.json")))
    guard.register_open("pos-1", "ST_ASIAN_SWEEP_5R_V1", "GBPUSD")
    assert guard.is_blocked() is True

    result = evaluate_setup(
        setup_id="EURUSD:2026-01-05:LONDON", strategy_id="ST_SESSION_SWEEP_RETEST_V1", symbol="EURUSD",
        trading_day=dt.date(2026, 1, 5), asian_candles=_asian_candles(), asian_expected_bar_count=1,
        h1_candles=H1_BEARISH, m5_candles=_short_sequence(), execution_windows=[LONDON_WINDOW],
        equity=10000.0, symbol_meta=EURUSD_META, risk_percent=0.5, sl_buffer_pips=2.5,
        market_structure_config=CFG, open_position_guard=guard,
    )
    assert result.state == STATE_BLOCKED_OPEN_POSITION


def test_daily_loss_circuit_breaker_blocks_after_minus_2r(tmp_path):
    guard = DailyLossGuard(JsonKeyValueStore(str(tmp_path / "daily_r.json")), "ST_SESSION_SWEEP_RETEST_V1")
    day = dt.date(2026, 1, 5)
    guard.record_trade_result(day, -1.0)
    guard.record_trade_result(day, -1.0)
    assert guard.is_blocked(day) is True

    result = evaluate_setup(
        setup_id="EURUSD:2026-01-05:LONDON", strategy_id="ST_SESSION_SWEEP_RETEST_V1", symbol="EURUSD",
        trading_day=day, asian_candles=_asian_candles(), asian_expected_bar_count=1,
        h1_candles=H1_BEARISH, m5_candles=_short_sequence(), execution_windows=[LONDON_WINDOW],
        equity=10000.0, symbol_meta=EURUSD_META, risk_percent=0.5, sl_buffer_pips=2.5,
        market_structure_config=CFG, daily_loss_guard=guard,
    )
    assert result.state == STATE_BLOCKED_DAILY_LOSS


def test_daily_loss_circuit_breaker_resets_next_trading_day(tmp_path):
    guard = DailyLossGuard(JsonKeyValueStore(str(tmp_path / "daily_r.json")), "ST_SESSION_SWEEP_RETEST_V1")
    day1 = dt.date(2026, 1, 5)
    day2 = dt.date(2026, 1, 6)
    guard.record_trade_result(day1, -2.0)
    assert guard.is_blocked(day1) is True
    assert guard.is_blocked(day2) is False
    assert guard.realized_r(day2) == 0.0


# --------------------------------------------------------------------------- full pipeline / replay

def _engine_kwargs(**overrides):
    kwargs = dict(
        setup_id="EURUSD:2026-01-05:LONDON", strategy_id="ST_SESSION_SWEEP_RETEST_V1", symbol="EURUSD",
        trading_day=dt.date(2026, 1, 5), asian_candles=_asian_candles(), asian_expected_bar_count=1,
        h1_candles=H1_BEARISH, m5_candles=_short_sequence(), execution_windows=[LONDON_WINDOW],
        equity=10000.0, symbol_meta=EURUSD_META, risk_percent=0.5, sl_buffer_pips=2.5,
        market_structure_config=CFG,
    )
    kwargs.update(overrides)
    return kwargs


def test_semantic_replay_reference_sweep_mss_retest_proposal():
    """The required small deterministic replay: REFERENCE -> SWEEP -> MSS -> RETEST -> PROPOSAL."""
    result = evaluate_setup(**_engine_kwargs())
    assert result.state == STATE_ENTRY_READY
    assert result.direction == "SHORT"
    assert result.asian_high == pytest.approx(ASIAN_HIGH)
    assert result.entry == pytest.approx(1.0940)
    assert result.stop_loss == pytest.approx(1.1080 + 2.5 * 0.0001)
    assert result.tp1 == pytest.approx(result.asian_mid)
    assert result.tp2 == pytest.approx(ASIAN_LOW)
    assert result.tp2_r_multiple >= 1.5
    assert result.volume is not None and result.volume > 0


def test_no_trade_direction_when_h1_neutral():
    flat_h1 = _h1_candles([1.1000] * 10, step_minutes=60)
    result = evaluate_setup(**_engine_kwargs(h1_candles=flat_h1))
    assert result.state == STATE_NO_TRADE_DIRECTION


def test_waiting_mss_state_before_confirmation():
    truncated = [x for x in _short_sequence() if x.time <= dt.datetime(2026, 1, 5, 7, 25, tzinfo=UTC)]
    result = evaluate_setup(**_engine_kwargs(m5_candles=truncated))
    assert result.state == STATE_WAITING_MSS


def test_waiting_retest_state_after_mss_before_retest():
    truncated = [x for x in _short_sequence() if x.time <= dt.datetime(2026, 1, 5, 7, 30, tzinfo=UTC)]
    result = evaluate_setup(**_engine_kwargs(m5_candles=truncated))
    assert result.state == STATE_WAITING_RETEST


# --------------------------------------------------------------------------- 18: idempotency

def test_duplicate_replay_is_idempotent(tmp_path):
    runtime = SweepRetestRuntime(SweepRetestStateStore(str(tmp_path / "state.json")))
    first = runtime.evaluate(**_engine_kwargs())
    second = runtime.evaluate(**_engine_kwargs())
    assert first.state == second.state == STATE_ENTRY_READY
    assert first.entry == second.entry
    assert first.volume == second.volume
    # ENTRY_READY is not terminal, so both calls recompute -- but recomputation of the
    # SAME inputs is bit-identical (pure function), so no duplicate/divergent signal
    # is ever produced for a replayed evaluation.


def test_duplicate_replay_never_reprocesses_a_terminal_setup(tmp_path):
    runtime = SweepRetestRuntime(SweepRetestStateStore(str(tmp_path / "state.json")))
    flat_h1 = _h1_candles([1.1000] * 10, step_minutes=60)
    first = runtime.evaluate(**_engine_kwargs(h1_candles=flat_h1))
    assert first.state == STATE_NO_TRADE_DIRECTION
    # Second call, even with DIFFERENT (now-bullish) candles, must return the SAME
    # terminal result -- a terminal setup_id is never re-evaluated.
    second = runtime.evaluate(**_engine_kwargs(h1_candles=H1_BULLISH))
    assert second.state == STATE_NO_TRADE_DIRECTION
    assert second.evaluated_at == first.evaluated_at


# --------------------------------------------------------------------------- 19/20: restart safety

def test_restart_during_waiting_mss_preserves_and_continues(tmp_path):
    state_path = str(tmp_path / "state.json")
    truncated = [x for x in _short_sequence() if x.time <= dt.datetime(2026, 1, 5, 7, 25, tzinfo=UTC)]

    runtime_before_restart = SweepRetestRuntime(SweepRetestStateStore(state_path))
    before = runtime_before_restart.evaluate(**_engine_kwargs(m5_candles=truncated))
    assert before.state == STATE_WAITING_MSS

    # "Restart": brand new runtime instance pointed at the same persisted state file.
    runtime_after_restart = SweepRetestRuntime(SweepRetestStateStore(state_path))
    persisted = runtime_after_restart.store.load("EURUSD:2026-01-05:LONDON")
    assert persisted is not None
    assert persisted.state == STATE_WAITING_MSS

    after = runtime_after_restart.evaluate(**_engine_kwargs())  # full history now available
    assert after.state == STATE_ENTRY_READY


def test_restart_during_waiting_retest_preserves_and_continues(tmp_path):
    state_path = str(tmp_path / "state.json")
    truncated = [x for x in _short_sequence() if x.time <= dt.datetime(2026, 1, 5, 7, 30, tzinfo=UTC)]

    runtime_before_restart = SweepRetestRuntime(SweepRetestStateStore(state_path))
    before = runtime_before_restart.evaluate(**_engine_kwargs(m5_candles=truncated))
    assert before.state == STATE_WAITING_RETEST

    runtime_after_restart = SweepRetestRuntime(SweepRetestStateStore(state_path))
    persisted = runtime_after_restart.store.load("EURUSD:2026-01-05:LONDON")
    assert persisted is not None
    assert persisted.state == STATE_WAITING_RETEST

    after = runtime_after_restart.evaluate(**_engine_kwargs())
    assert after.state == STATE_ENTRY_READY


# --------------------------------------------------------------------------- lifecycle chain sanity

def test_full_lifecycle_transition_chain_from_entry_ready():
    result = evaluate_setup(**_engine_kwargs())
    assert result.state == STATE_ENTRY_READY
    submitted = transition_order_submitted(result)
    opened = transition_position_open(submitted)
    tp1 = transition_tp1_hit(opened, tp1_volume_pct=0.5)
    runner = transition_runner_active(tp1)
    assert submitted.state == "ORDER_SUBMITTED"
    assert opened.state == STATE_POSITION_OPEN
    assert tp1.state == STATE_TP1_HIT
    assert runner.state == STATE_RUNNER_ACTIVE
    assert runner.stop_loss == pytest.approx(result.entry)
