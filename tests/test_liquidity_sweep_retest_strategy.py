"""Tests for ST_LIQUIDITY_SWEEP_RETEST_V1 (strategy_engine.sweep_retest).

Covers both the Forex profile (Asian High/Low/Mid reference, pip-based SL buffer) and the
Crypto profile (Previous-Day High/Low/Mid reference, tick-based SL buffer) through the
SAME sweep/MSS/retest/state-machine engine, parameterized by profile.py's MarketProfile --
not two duplicated engines. Deterministic synthetic fixtures only, no MT5/live/exchange
connection -- same idiom as tests/test_session_router.py and tests/test_market_structure.py.
Every fixture only ever looks at candles up to and including the one that produces the
decision under test.
"""
from __future__ import annotations

import datetime as dt
from datetime import time

import pytest

from execution.adapter import AdapterSubmitResult, CryptoExecutionAdapter, MT5ExecutionAdapter, select_adapter
from execution.daily_loss_guard import DailyLossGuard
from execution.position_guard import OpenPositionGuard
from market_structure.models import MarketStructureConfig
from mt5.symbol_resolver import SymbolMeta
from runtime_state.store import JsonKeyValueStore
from strategy_engine.session import Candle
from strategy_engine.sweep_retest.crypto_symbols import crypto_sl_buffer_price, crypto_symbol_meta
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
    STATE_POSITION_OPEN,
    STATE_RUNNER_ACTIVE,
    STATE_TP1_HIT,
    STATE_WAITING_MSS,
    STATE_WAITING_RETEST,
    SetupState,
)
from strategy_engine.sweep_retest.profile import (
    BUFFER_PIP,
    BUFFER_TICK,
    PROFILE_CRYPTO_PERP,
    PROFILE_FOREX,
    REFERENCE_ASIAN_SESSION,
    REFERENCE_PREVIOUS_DAY,
    MarketProfile,
    filter_previous_day_candles,
    previous_utc_day_window,
)
from strategy_engine.sweep_retest.retest import find_retest
from strategy_engine.sweep_retest.state_store import SweepRetestStateStore
from strategy_engine.sweep_retest.sweep import SWEEP_HIGH, SWEEP_LOW, find_qualified_sweep
from strategy_engine.sweep_retest.targets import build_target_plan, forex_sl_buffer_price
from strategy_engine.sweep_retest.trend import h1_trend_direction

UTC = dt.timezone.utc
CFG = MarketStructureConfig(swing_length=1, close_break=True, default_analysis_count=50)
STRATEGY_ID = "ST_LIQUIDITY_SWEEP_RETEST_V1"

LONDON_WINDOW = (time(7, 0), time(10, 0))
CRYPTO_WINDOW = (time(13, 30), time(16, 0))

FOREX_PROFILE = MarketProfile(PROFILE_FOREX, ("EURUSD", "GBPUSD"), REFERENCE_ASIAN_SESSION, "Asian", BUFFER_PIP, (LONDON_WINDOW,))
CRYPTO_PROFILE = MarketProfile(PROFILE_CRYPTO_PERP, ("BTCUSDT", "ETHUSDT"), REFERENCE_PREVIOUS_DAY, "PreviousDay", BUFFER_TICK, (CRYPTO_WINDOW,))

EURUSD_META = SymbolMeta(
    symbol="EURUSD", tick_size=0.00001, tick_value=1.0, contract_size=100000,
    volume_min=0.01, volume_max=50.0, volume_step=0.01, digits=5, point=0.00001,
)
BTCUSDT_META = crypto_symbol_meta("BTCUSDT")
ETHUSDT_META = crypto_symbol_meta("ETHUSDT")


def _c(minute, o, h, l, cl, hour=7, day=5):
    return Candle(time=dt.datetime(2026, 1, day, hour, minute, tzinfo=UTC), open=o, high=h, low=l, close=cl, volume=1.0)


# ============================================================================= FOREX
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
EURUSD_SL_BUFFER = forex_sl_buffer_price(EURUSD_META, 2.5)


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
    candle = _c(15, 1.1005, 1.1080, 1.1055, 1.1070)
    sweep = find_qualified_sweep([candle], ASIAN_HIGH, ASIAN_LOW)
    assert sweep is None


# --------------------------------------------------------------------------- 4/5: H1 gating

def test_high_sweep_rejected_by_bullish_h1_direction():
    assert h1_trend_direction(H1_BULLISH, CFG) == "LONG_ONLY"
    candles = _short_sequence()
    sweep = find_qualified_sweep(candles, ASIAN_HIGH, ASIAN_LOW, required_direction=SWEEP_LOW)
    assert sweep is None


def test_low_sweep_rejected_by_bearish_h1_direction():
    assert h1_trend_direction(H1_BEARISH, CFG) == "SHORT_ONLY"
    candle = _c(15, 1.0750, 1.0760, 1.0650, 1.0720)
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
    plan = build_target_plan("SHORT", entry=1.0940, sweep_extreme=1.1080, ref_mid=1.0925,
                              ref_high=ASIAN_HIGH, ref_low=ASIAN_LOW, stop_buffer_price=EURUSD_SL_BUFFER)
    assert plan.stop_loss == pytest.approx(1.1080 + 2.5 * 0.0001)


def test_correct_sweep_extreme_stop_loss_long():
    plan = build_target_plan("LONG", entry=1.0810, sweep_extreme=1.0750, ref_mid=1.0925,
                              ref_high=ASIAN_HIGH, ref_low=ASIAN_LOW, stop_buffer_price=EURUSD_SL_BUFFER)
    assert plan.stop_loss == pytest.approx(1.0750 - 2.5 * 0.0001)


# --------------------------------------------------------------------------- 11/12: geometry guard

def test_invalid_tp1_geometry_rejected_short():
    plan = build_target_plan("SHORT", entry=1.0900, sweep_extreme=1.1080, ref_mid=1.0950,
                              ref_high=ASIAN_HIGH, ref_low=ASIAN_LOW, stop_buffer_price=EURUSD_SL_BUFFER)
    assert plan.status == "NO_TRADE_TARGET_GEOMETRY"


def test_tp2_below_minimum_r_multiple_rejected():
    plan = build_target_plan("SHORT", entry=1.0940, sweep_extreme=1.1080, ref_mid=1.0925,
                              ref_high=ASIAN_HIGH, ref_low=1.0930, stop_buffer_price=EURUSD_SL_BUFFER)
    assert plan.status == "NO_TRADE_TARGET_GEOMETRY"


def test_valid_geometry_accepted_with_sufficient_r():
    plan = build_target_plan("SHORT", entry=1.0940, sweep_extreme=1.1080, ref_mid=1.0925,
                              ref_high=ASIAN_HIGH, ref_low=ASIAN_LOW, stop_buffer_price=EURUSD_SL_BUFFER)
    assert plan.status == "VALID"
    assert plan.tp2_r_multiple >= 1.5


# --------------------------------------------------------------------------- 13/14: TP1/breakeven transitions

def test_tp1_50_percent_transition():
    state = SetupState(setup_id="s1", strategy_id=STRATEGY_ID, symbol="EURUSD", state=STATE_POSITION_OPEN,
                        reason_code="POSITION_OPEN", entry=1.0940, stop_loss=1.1105)
    result = transition_tp1_hit(state, tp1_volume_pct=0.5)
    assert result.state == STATE_TP1_HIT
    assert result.evidence["tp1_close_pct"] == 0.5
    assert result.evidence["sl_moved_to_breakeven"] is True


def test_breakeven_moves_stop_to_entry():
    state = SetupState(setup_id="s1", strategy_id=STRATEGY_ID, symbol="EURUSD", state=STATE_TP1_HIT,
                        reason_code="TP1_REACHED", entry=1.0940, stop_loss=1.1105)
    result = transition_runner_active(state)
    assert result.state == STATE_RUNNER_ACTIVE
    assert result.stop_loss == pytest.approx(1.0940)


# --------------------------------------------------------------------------- 15/16/17: guards

def test_one_open_position_blocks_new_entry(tmp_path):
    guard = OpenPositionGuard(JsonKeyValueStore(str(tmp_path / "open_positions.json")))
    guard.register_open("pos-1", "ST_ASIAN_SWEEP_5R_V1", "GBPUSD")
    assert guard.is_blocked() is True

    result = evaluate_setup(**_forex_kwargs(open_position_guard=guard))
    assert result.state == STATE_BLOCKED_OPEN_POSITION


def test_daily_loss_circuit_breaker_blocks_after_minus_2r(tmp_path):
    guard = DailyLossGuard(JsonKeyValueStore(str(tmp_path / "daily_r.json")), STRATEGY_ID)
    day = dt.date(2026, 1, 5)
    guard.record_trade_result(day, -1.0)
    guard.record_trade_result(day, -1.0)
    assert guard.is_blocked(day) is True

    result = evaluate_setup(**_forex_kwargs(daily_loss_guard=guard))
    assert result.state == STATE_BLOCKED_DAILY_LOSS


def test_daily_loss_circuit_breaker_resets_next_trading_day(tmp_path):
    guard = DailyLossGuard(JsonKeyValueStore(str(tmp_path / "daily_r.json")), STRATEGY_ID)
    day1 = dt.date(2026, 1, 5)
    day2 = dt.date(2026, 1, 6)
    guard.record_trade_result(day1, -2.0)
    assert guard.is_blocked(day1) is True
    assert guard.is_blocked(day2) is False
    assert guard.realized_r(day2) == 0.0


# ------------------------------------------------------ 17b: strategy_qualified / tradability
# (remediation Gap 2 -- engine.py's own two-layer result model)

def test_guard_blocked_setup_still_reports_strategy_qualified_true(tmp_path):
    guard = OpenPositionGuard(JsonKeyValueStore(str(tmp_path / "open_positions.json")))
    guard.register_open("pos-1", "ST_ASIAN_SWEEP_5R_V1", "GBPUSD")

    result = evaluate_setup(**_forex_kwargs(open_position_guard=guard))
    assert result.state == STATE_BLOCKED_OPEN_POSITION
    assert result.strategy_qualified is True  # the opportunity genuinely existed
    assert result.tradability_blocked is True
    assert result.tradability_reason == STATE_BLOCKED_OPEN_POSITION
    # Full qualification evidence is preserved, not erased by the guard block.
    assert result.entry is not None and result.stop_loss is not None and result.volume is not None


def test_unblocked_entry_ready_reports_qualified_and_tradable():
    result = evaluate_setup(**_forex_kwargs())
    assert result.state == STATE_ENTRY_READY
    assert result.strategy_qualified is True
    assert result.tradability_blocked is False
    assert result.tradability_reason is None


def test_non_qualifying_setup_reports_strategy_qualified_false():
    flat_h1 = _h1_candles([1.1000] * 10, step_minutes=60)
    result = evaluate_setup(**_forex_kwargs(h1_candles=flat_h1))
    assert result.state == STATE_NO_TRADE_DIRECTION
    assert result.strategy_qualified is False
    assert result.tradability_blocked is False
    assert result.tradability_reason is None


def test_sweep_search_after_skips_earlier_sweep_in_window():
    """Remediation Gap 1's own extension point: sweep_search_after lets a caller lock
    onto a LATER sweep candidate in the same window, without re-discovering an earlier
    one -- the exact mechanism occurrence_enumerator.py builds on."""
    candles = _short_sequence()
    first_sweep = find_qualified_sweep(candles, ASIAN_HIGH, ASIAN_LOW)
    assert first_sweep is not None

    result_default = evaluate_setup(**_forex_kwargs())
    assert result_default.sweep_time == first_sweep.candle_time

    result_after = evaluate_setup(**_forex_kwargs(sweep_search_after=first_sweep.candle_time))
    # No second sweep exists in this fixture past the first one -> falls back to WAITING_SWEEP.
    assert result_after.state in ("WAITING_SWEEP", "SESSION_EXPIRED")
    assert result_after.strategy_qualified is False


# --------------------------------------------------------------------------- full Forex pipeline / replay

def _forex_kwargs(**overrides):
    kwargs = dict(
        setup_id="EURUSD:2026-01-05:LONDON", strategy_id=STRATEGY_ID, symbol="EURUSD",
        trading_day=dt.date(2026, 1, 5), profile=FOREX_PROFILE, reference_candles=_asian_candles(),
        reference_expected_bar_count=1, h1_candles=H1_BEARISH, m5_candles=_short_sequence(),
        execution_windows=[LONDON_WINDOW], equity=10000.0, symbol_meta=EURUSD_META, risk_percent=0.5,
        stop_buffer_price=EURUSD_SL_BUFFER, market_structure_config=CFG,
    )
    kwargs.update(overrides)
    return kwargs


def test_semantic_replay_reference_sweep_mss_retest_proposal():
    """The required small deterministic replay: REFERENCE -> SWEEP -> MSS -> RETEST -> PROPOSAL."""
    result = evaluate_setup(**_forex_kwargs())
    assert result.state == STATE_ENTRY_READY
    assert result.direction == "SHORT"
    assert result.profile_id == PROFILE_FOREX
    assert result.ref_high == pytest.approx(ASIAN_HIGH)
    assert result.entry == pytest.approx(1.0940)
    assert result.stop_loss == pytest.approx(1.1080 + 2.5 * 0.0001)
    assert result.tp1 == pytest.approx(result.ref_mid)
    assert result.tp2 == pytest.approx(ASIAN_LOW)
    assert result.tp2_r_multiple >= 1.5
    assert result.volume is not None and result.volume > 0


def test_no_trade_direction_when_h1_neutral():
    flat_h1 = _h1_candles([1.1000] * 10, step_minutes=60)
    result = evaluate_setup(**_forex_kwargs(h1_candles=flat_h1))
    assert result.state == STATE_NO_TRADE_DIRECTION


def test_waiting_mss_state_before_confirmation():
    truncated = [x for x in _short_sequence() if x.time <= dt.datetime(2026, 1, 5, 7, 25, tzinfo=UTC)]
    result = evaluate_setup(**_forex_kwargs(m5_candles=truncated))
    assert result.state == STATE_WAITING_MSS


def test_waiting_retest_state_after_mss_before_retest():
    truncated = [x for x in _short_sequence() if x.time <= dt.datetime(2026, 1, 5, 7, 30, tzinfo=UTC)]
    result = evaluate_setup(**_forex_kwargs(m5_candles=truncated))
    assert result.state == STATE_WAITING_RETEST


# --------------------------------------------------------------------------- 18: idempotency

def test_duplicate_replay_is_idempotent(tmp_path):
    runtime = SweepRetestRuntime(SweepRetestStateStore(str(tmp_path / "state.json")))
    first = runtime.evaluate(**_forex_kwargs())
    second = runtime.evaluate(**_forex_kwargs())
    assert first.state == second.state == STATE_ENTRY_READY
    assert first.entry == second.entry
    assert first.volume == second.volume


def test_duplicate_replay_never_reprocesses_a_terminal_setup(tmp_path):
    runtime = SweepRetestRuntime(SweepRetestStateStore(str(tmp_path / "state.json")))
    flat_h1 = _h1_candles([1.1000] * 10, step_minutes=60)
    first = runtime.evaluate(**_forex_kwargs(h1_candles=flat_h1))
    assert first.state == STATE_NO_TRADE_DIRECTION
    second = runtime.evaluate(**_forex_kwargs(h1_candles=H1_BULLISH))
    assert second.state == STATE_NO_TRADE_DIRECTION
    assert second.evaluated_at == first.evaluated_at


# --------------------------------------------------------------------------- 19/20: restart safety

def test_restart_during_waiting_mss_preserves_and_continues(tmp_path):
    state_path = str(tmp_path / "state.json")
    truncated = [x for x in _short_sequence() if x.time <= dt.datetime(2026, 1, 5, 7, 25, tzinfo=UTC)]

    runtime_before_restart = SweepRetestRuntime(SweepRetestStateStore(state_path))
    before = runtime_before_restart.evaluate(**_forex_kwargs(m5_candles=truncated))
    assert before.state == STATE_WAITING_MSS

    runtime_after_restart = SweepRetestRuntime(SweepRetestStateStore(state_path))
    persisted = runtime_after_restart.store.load("EURUSD:2026-01-05:LONDON")
    assert persisted is not None
    assert persisted.state == STATE_WAITING_MSS

    after = runtime_after_restart.evaluate(**_forex_kwargs())
    assert after.state == STATE_ENTRY_READY


def test_restart_during_waiting_retest_preserves_and_continues(tmp_path):
    state_path = str(tmp_path / "state.json")
    truncated = [x for x in _short_sequence() if x.time <= dt.datetime(2026, 1, 5, 7, 30, tzinfo=UTC)]

    runtime_before_restart = SweepRetestRuntime(SweepRetestStateStore(state_path))
    before = runtime_before_restart.evaluate(**_forex_kwargs(m5_candles=truncated))
    assert before.state == STATE_WAITING_RETEST

    runtime_after_restart = SweepRetestRuntime(SweepRetestStateStore(state_path))
    persisted = runtime_after_restart.store.load("EURUSD:2026-01-05:LONDON")
    assert persisted is not None
    assert persisted.state == STATE_WAITING_RETEST

    after = runtime_after_restart.evaluate(**_forex_kwargs())
    assert after.state == STATE_ENTRY_READY


# --------------------------------------------------------------------------- lifecycle chain sanity

def test_full_lifecycle_transition_chain_from_entry_ready():
    result = evaluate_setup(**_forex_kwargs())
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


# ============================================================================= CRYPTO
# Previous UTC day (2026-01-04): PDH=42000, PDL=40700 (widened vs. the plain sweep/mss/
# retest unit fixtures below so the full-engine test clears the 1.5R geometry guard).
# Today (2026-01-05), within the 13:30-16:00 UTC strategy activity window: a HIGH sweep
# of PDH, MSS confirms on the 3rd post-sweep candle (after one intrabar-only penetration),
# retest at 14:05 -- same shape as the Forex fixture, crypto price scale.

BTC_PDH_UNIT, BTC_PDL_UNIT = 42000.0, 41000.0  # for the plain sweep/mss/retest unit tests
BTC_PDH, BTC_PDL = 42000.0, 40700.0  # for the full-engine ENTRY_READY test (valid 1.5R)


def _btc_high_sweep_sequence():
    return [
        _c(30, 41700, 41710, 41690, 41700, hour=13),
        _c(35, 41680, 41685, 41600, 41650, hour=13),   # swing low candidate ~41600
        _c(40, 41660, 41720, 41655, 41710, hour=13),   # rally
        _c(45, 41710, 42150, 41500, 41550, hour=13),   # SWEEP: high>42000, close<42000
        _c(50, 41550, 41650, 41580, 41630, hour=13),   # intrabar only: low<41600, close above
        _c(55, 41630, 41650, 41610, 41620, hour=13),   # still above
        _c(0, 41620, 41625, 41400, 41450, hour=14),    # closes below 41600 -> MSS
        _c(5, 41450, 41650, 41400, 41500, hour=14),    # retest: high>=41600
        _c(10, 41500, 41510, 41300, 41350, hour=14),
    ]


def _btc_low_sweep_sequence():
    return [
        _c(30, 41300, 41310, 41290, 41300, hour=13),
        _c(35, 41320, 41420, 41315, 41400, hour=13),   # swing high candidate ~41420
        _c(40, 41340, 41345, 41290, 41300, hour=13),   # pullback
        _c(45, 40950, 40970, 40800, 41050, hour=13),   # SWEEP: low<41000, close>41000
        _c(50, 41050, 41450, 41020, 41400, hour=13),   # intrabar only: high>41420, close<41420
        _c(55, 41400, 41415, 41380, 41410, hour=13),   # still below
        _c(0, 41410, 41460, 41405, 41450, hour=14),    # closes above 41420 -> MSS
        _c(5, 41450, 41460, 41400, 41430, hour=14),    # retest: low<=41420
        _c(10, 41430, 41440, 41300, 41350, hour=14),
    ]


def _prev_day_candles(high, low, mid=None):
    mid_open = mid if mid is not None else (high + low) / 2.0
    return [Candle(time=dt.datetime(2026, 1, 4, 12, 0, tzinfo=UTC), open=mid_open, high=high, low=low, close=mid_open, volume=1.0)]


def test_btc_pdh_high_sweep_detected():
    sweep = find_qualified_sweep(_btc_high_sweep_sequence(), BTC_PDH_UNIT, BTC_PDL_UNIT)
    assert sweep is not None
    assert sweep.direction == SWEEP_HIGH
    assert sweep.extreme_price == pytest.approx(42150.0)


def test_btc_pdl_low_sweep_detected():
    sweep = find_qualified_sweep(_btc_low_sweep_sequence(), BTC_PDH_UNIT, BTC_PDL_UNIT)
    assert sweep is not None
    assert sweep.direction == SWEEP_LOW
    assert sweep.extreme_price == pytest.approx(40800.0)


def test_eth_pdh_high_sweep_detected():
    # Reuses the BTC HIGH-sweep candle shape (the sweep rule is symbol-agnostic; only the
    # tick/symbol-meta side differs for ETH, exercised separately below).
    eth_pdh, eth_pdl = 2500.0, 2400.0
    candles = [
        _c(30, 2470, 2471, 2469, 2470, hour=13),
        _c(35, 2468, 2469, 2450, 2465, hour=13),
        _c(40, 2466, 2472, 2465, 2471, hour=13),
        _c(45, 2471, 2515, 2440, 2445, hour=13),  # SWEEP: high>2500, close<2500
    ]
    sweep = find_qualified_sweep(candles, eth_pdh, eth_pdl)
    assert sweep is not None
    assert sweep.direction == SWEEP_HIGH
    assert sweep.extreme_price == pytest.approx(2515.0)


def test_crypto_wick_outside_but_close_outside_is_not_a_sweep():
    candle = _c(45, 41950, 42150, 42000, 42100, hour=13)  # close (42100) still above PDH (42000)
    sweep = find_qualified_sweep([candle], BTC_PDH_UNIT, BTC_PDL_UNIT)
    assert sweep is None


def test_h1_trend_mismatch_blocks_crypto_high_sweep():
    assert h1_trend_direction(H1_BULLISH, CFG) == "LONG_ONLY"
    sweep = find_qualified_sweep(_btc_high_sweep_sequence(), BTC_PDH_UNIT, BTC_PDL_UNIT, required_direction=SWEEP_LOW)
    assert sweep is None


def test_crypto_mss_requires_closed_m5_close_beyond_swing():
    candles = _btc_high_sweep_sequence()
    sweep = find_qualified_sweep(candles, BTC_PDH_UNIT, BTC_PDL_UNIT)
    up_to = [x for x in candles if x.time <= sweep.candle_time]
    intrabar_only = [x for x in candles if x.time == dt.datetime(2026, 1, 5, 13, 50, tzinfo=UTC)]
    assert find_mss(sweep, up_to, intrabar_only, CFG) is None  # intrabar penetration only -> no MSS

    after = [x for x in candles if x.time > sweep.candle_time]
    mss = find_mss(sweep, up_to, after, CFG)
    assert mss is not None
    assert mss.kind == MSS_BEARISH
    assert mss.broken_swing_price == pytest.approx(41600.0)


def test_crypto_stop_buffer_uses_tick_semantics_not_pip_semantics():
    buffer_price = crypto_sl_buffer_price("BTCUSDT", buffer_ticks=10)
    assert buffer_price == pytest.approx(0.1 * 10)  # BTCUSDT tick size, NOT a Forex pip
    assert BTCUSDT_META.tick_size == pytest.approx(0.1)
    assert ETHUSDT_META.tick_size == pytest.approx(0.01)

    plan = build_target_plan("SHORT", entry=41600.0, sweep_extreme=42150.0, ref_mid=41350.0,
                              ref_high=BTC_PDH, ref_low=BTC_PDL, stop_buffer_price=buffer_price)
    assert plan.stop_loss == pytest.approx(42150.0 + 1.0)  # +10 ticks, not a pip-scaled offset


def test_previous_day_utc_boundary_correctness():
    now = dt.datetime(2026, 1, 5, 14, 30, tzinfo=UTC)
    start, end = previous_utc_day_window(now)
    assert start == dt.datetime(2026, 1, 4, 0, 0, tzinfo=UTC)
    assert end == dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC)

    candles = [
        Candle(time=dt.datetime(2026, 1, 3, 23, 59, tzinfo=UTC), open=1, high=1, low=1, close=1),  # before window
        Candle(time=dt.datetime(2026, 1, 4, 0, 0, tzinfo=UTC), open=2, high=2, low=2, close=2),  # inclusive start
        Candle(time=dt.datetime(2026, 1, 4, 23, 55, tzinfo=UTC), open=3, high=3, low=3, close=3),  # inside
        Candle(time=dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC), open=4, high=4, low=4, close=4),  # exclusive end
    ]
    filtered = filter_previous_day_candles(candles, now)
    assert [c.close for c in filtered] == [2, 3]


def _crypto_kwargs(**overrides):
    kwargs = dict(
        setup_id="BTCUSDT:2026-01-05:ACTIVITY", strategy_id=STRATEGY_ID, symbol="BTCUSDT",
        trading_day=dt.date(2026, 1, 5), profile=CRYPTO_PROFILE, reference_candles=_prev_day_candles(BTC_PDH, BTC_PDL),
        h1_candles=H1_BEARISH, m5_candles=_btc_high_sweep_sequence(), execution_windows=[CRYPTO_WINDOW],
        equity=10000.0, symbol_meta=BTCUSDT_META, risk_percent=0.5,
        stop_buffer_price=crypto_sl_buffer_price("BTCUSDT"), market_structure_config=CFG,
    )
    kwargs.update(overrides)
    return kwargs


def test_crypto_semantic_replay_reference_sweep_mss_retest_proposal():
    result = evaluate_setup(**_crypto_kwargs())
    assert result.state == STATE_ENTRY_READY
    assert result.direction == "SHORT"
    assert result.profile_id == PROFILE_CRYPTO_PERP
    assert result.ref_high == pytest.approx(BTC_PDH)
    assert result.ref_low == pytest.approx(BTC_PDL)
    assert result.entry == pytest.approx(41600.0)
    assert result.stop_loss == pytest.approx(42150.0 + 1.0)
    assert result.tp1 == pytest.approx(result.ref_mid)
    assert result.tp2 == pytest.approx(BTC_PDL)
    assert result.tp2_r_multiple >= 1.5
    assert result.volume is not None and result.volume > 0


# --------------------------------------------------------------------------- global guard is asset-agnostic

def test_global_position_lock_is_asset_agnostic_eurusd_blocks_btcusdt(tmp_path):
    guard = OpenPositionGuard(JsonKeyValueStore(str(tmp_path / "open_positions.json")))
    guard.register_open("pos-eurusd-1", STRATEGY_ID, "EURUSD")
    assert guard.is_blocked() is True

    # An otherwise-valid BTCUSDT setup is blocked purely because SOME position (a
    # different asset, same shared guard) is already open -- concurrency is combined
    # across profiles, not tracked per-asset.
    result = evaluate_setup(**_crypto_kwargs(open_position_guard=guard))
    assert result.state == STATE_BLOCKED_OPEN_POSITION


def test_daily_loss_circuit_breaker_combines_forex_and_crypto(tmp_path):
    guard = DailyLossGuard(JsonKeyValueStore(str(tmp_path / "daily_r.json")), STRATEGY_ID)
    day = dt.date(2026, 1, 5)
    guard.record_trade_result(day, -1.0)  # a Forex loss
    guard.record_trade_result(day, -1.0)  # a Crypto loss -- same combined ledger
    assert guard.is_blocked(day) is True

    forex_result = evaluate_setup(**_forex_kwargs(daily_loss_guard=guard))
    crypto_result = evaluate_setup(**_crypto_kwargs(daily_loss_guard=guard))
    assert forex_result.state == STATE_BLOCKED_DAILY_LOSS
    assert crypto_result.state == STATE_BLOCKED_DAILY_LOSS


# ============================================================================= execution adapter

def test_crypto_adapter_is_not_implemented_and_never_sends_an_order():
    adapter = select_adapter(PROFILE_CRYPTO_PERP)
    assert isinstance(adapter, CryptoExecutionAdapter)
    result = adapter.submit(proposal=None, user_confirmed=True)
    assert isinstance(result, AdapterSubmitResult)
    assert result.status == "NOT_IMPLEMENTED"


def test_mt5_adapter_is_a_placeholder_not_a_real_execution_path():
    adapter = select_adapter(PROFILE_FOREX)
    assert isinstance(adapter, MT5ExecutionAdapter)
    with pytest.raises(NotImplementedError):
        adapter.submit(proposal=None, user_confirmed=True)
