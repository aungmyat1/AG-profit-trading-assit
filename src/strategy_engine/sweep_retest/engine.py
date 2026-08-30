"""Orchestration for ST_SESSION_SWEEP_RETEST_V1.

Pipeline (spec):
  Asian reference box (strategy_engine.session.build_reference_box, REUSED)
    -> execution window gate (this strategy's own 07:00-10:00 / 12:00-15:00 UTC windows)
    -> H1 trend filter (trend.py, wraps market_structure.structural_breaks_for_candles, REUSED)
    -> M5 sweep detection (sweep.py, this strategy's own rule -- see its docstring)
    -> M5 MSS confirmation (mss.py, wraps market_structure.smc_adapter.full_swings, REUSED)
    -> M5 retest trigger with TTL (retest.py, this strategy's own rule)
    -> SL/TP + target-geometry guard (targets.py)
    -> position sizing (execution.risk.size_position, REUSED)
  Guards (execution.position_guard / execution.daily_loss_guard, NEW shared pieces) are
  checked up front, before any candle work, since a blocked setup never needs evaluating.

evaluate_setup() is a pure function of its candle-history inputs -- calling it twice with
identical inputs produces a bit-identical SetupState (no MT5 call, no wall-clock read
inside the pipeline itself). That purity is what makes SweepRetestRuntime (below)
restart-safe: a persisted SetupState is just a cached result of this same deterministic
computation, so a fresh process recomputes (or, once terminal, simply replays) the same
answer -- see state_store.py.

Only ever produces a SetupState up to ENTRY_READY or a terminal NO_TRADE/BLOCKED/EXPIRED
reason. Never sends an order -- ORDER_SUBMITTED/POSITION_OPEN/TP1_HIT/RUNNER_ACTIVE/
TP2_HIT/STOPPED are reached only via the explicit lifecycle transition helpers below,
called by the execution layer AFTER a human/assistant has actually opened a position
through the existing execution.executor/mt5.management_gateway path -- this module never
calls those itself (spec: "Execution Safety ... No real-money execution changes").
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from typing import Optional, Sequence

from execution.daily_loss_guard import DailyLossGuard
from execution.position_guard import OpenPositionGuard
from execution.risk import size_position
from market_structure.config import load_market_structure_config
from market_structure.models import MarketStructureConfig
from mt5.symbol_resolver import SymbolMeta
from strategy_engine.session import Candle, build_reference_box

from .config import SweepRetestStrategyConfig
from .models import (
    STATE_BLOCKED_DAILY_LOSS,
    STATE_BLOCKED_OPEN_POSITION,
    STATE_ENTRY_READY,
    STATE_MSS_CONFIRMED,
    STATE_NO_TRADE_DIRECTION,
    STATE_NO_TRADE_TARGET_GEOMETRY,
    STATE_POSITION_OPEN,
    STATE_RUNNER_ACTIVE,
    STATE_SESSION_EXPIRED,
    STATE_SETUP_EXPIRED,
    STATE_STOPPED,
    STATE_SWEEP_DETECTED,
    STATE_TP1_HIT,
    STATE_TP2_HIT,
    STATE_WAITING_MSS,
    STATE_WAITING_REFERENCE,
    STATE_WAITING_RETEST,
    STATE_WAITING_SWEEP,
    STATE_WAITING_WINDOW,
    TERMINAL_STATES,
    SetupState,
)
from .mss import find_mss
from .retest import ENTRY_TTL_M5_BARS, find_retest
from .state_store import SweepRetestStateStore
from .sweep import SWEEP_HIGH, SWEEP_LOW, find_qualified_sweep
from .targets import GEOMETRY_VALID, build_target_plan
from .trend import DIRECTION_LONG_ONLY, DIRECTION_SHORT_ONLY, h1_trend_direction


def _in_windows(t: datetime, windows: Sequence[tuple]) -> bool:
    tod = t.time()
    return any(start <= tod < end for start, end in windows)


def evaluate_setup(
    setup_id: str,
    strategy_id: str,
    symbol: str,
    trading_day: date,
    asian_candles: Sequence[Candle],
    asian_expected_bar_count: int,
    h1_candles: Sequence[Candle],
    m5_candles: Sequence[Candle],
    execution_windows: Sequence[tuple],  # [(time_start, time_end), ...] UTC, half-open
    equity: float,
    symbol_meta: SymbolMeta,
    risk_percent: float,
    sl_buffer_pips: float,
    entry_ttl_m5_bars: int = ENTRY_TTL_M5_BARS,
    market_structure_config: Optional[MarketStructureConfig] = None,
    daily_loss_guard: Optional[DailyLossGuard] = None,
    open_position_guard: Optional[OpenPositionGuard] = None,
    session_window_closed: bool = False,
    now: Optional[datetime] = None,
) -> SetupState:
    """m5_candles: ALL closed M5 candles from the end of the Asian reference session up
    to "now", chronological -- this function itself filters to execution-window candles
    for sweep scanning, and reuses the full (unfiltered) series for MSS/retest lookups
    around whatever sweep candle it finds, since a swing/MSS/retest may legitimately
    straddle a window boundary."""
    base = dict(setup_id=setup_id, strategy_id=strategy_id, symbol=symbol, evaluated_at=now)
    config = market_structure_config or load_market_structure_config()

    if daily_loss_guard is not None and daily_loss_guard.is_blocked(trading_day):
        return SetupState(**base, state=STATE_BLOCKED_DAILY_LOSS, reason_code=STATE_BLOCKED_DAILY_LOSS)
    if open_position_guard is not None and open_position_guard.is_blocked():
        return SetupState(**base, state=STATE_BLOCKED_OPEN_POSITION, reason_code=STATE_BLOCKED_OPEN_POSITION)

    box = build_reference_box("Asian", asian_candles, asian_expected_bar_count) if asian_candles else None
    if box is None or not box.session_complete:
        return SetupState(**base, state=STATE_WAITING_REFERENCE, reason_code="ASIAN_SESSION_INCOMPLETE")

    direction_gate = h1_trend_direction(h1_candles, config)
    if direction_gate == DIRECTION_LONG_ONLY:
        required_sweep_direction = SWEEP_LOW
        trade_direction = "LONG"
    elif direction_gate == DIRECTION_SHORT_ONLY:
        required_sweep_direction = SWEEP_HIGH
        trade_direction = "SHORT"
    else:
        return SetupState(
            **base, state=STATE_NO_TRADE_DIRECTION, reason_code=STATE_NO_TRADE_DIRECTION,
            asian_high=box.session_high, asian_low=box.session_low, asian_mid=box.session_mid,
        )

    box_evidence = dict(asian_high=box.session_high, asian_low=box.session_low, asian_mid=box.session_mid, direction=trade_direction)

    window_candles = [c for c in m5_candles if _in_windows(c.time, execution_windows)]
    if not window_candles:
        return SetupState(**base, state=STATE_WAITING_WINDOW, reason_code="EXECUTION_WINDOW_NOT_REACHED", **box_evidence)

    sweep = find_qualified_sweep(window_candles, box.session_high, box.session_low, required_sweep_direction)
    if sweep is None:
        if session_window_closed:
            return SetupState(**base, state=STATE_SESSION_EXPIRED, reason_code="NO_QUALIFIED_SWEEP_IN_WINDOW", **box_evidence)
        return SetupState(**base, state=STATE_WAITING_SWEEP, reason_code="NO_QUALIFIED_SWEEP_YET", **box_evidence)

    sweep_evidence = dict(
        **box_evidence, sweep_level=sweep.swept_level, sweep_extreme=sweep.extreme_price, sweep_time=sweep.candle_time,
    )

    candles_up_to_sweep = [c for c in m5_candles if c.time <= sweep.candle_time]
    candles_after_sweep = [c for c in m5_candles if c.time > sweep.candle_time]

    mss = find_mss(sweep, candles_up_to_sweep, candles_after_sweep, config)
    if mss is None:
        if not candles_after_sweep:
            return SetupState(**base, state=STATE_SWEEP_DETECTED, reason_code="AWAITING_MSS_CANDLES", **sweep_evidence)
        return SetupState(**base, state=STATE_WAITING_MSS, reason_code="MSS_NOT_YET_CONFIRMED", **sweep_evidence)

    mss_evidence = dict(**sweep_evidence, broken_swing_price=mss.broken_swing_price, mss_time=mss.confirmed_at)

    candles_after_mss = [c for c in m5_candles if c.time > mss.confirmed_at]
    retest = find_retest(mss, candles_after_mss, entry_ttl_m5_bars)
    if retest is None:
        if len(candles_after_mss) >= entry_ttl_m5_bars:
            return SetupState(**base, state=STATE_SETUP_EXPIRED, reason_code=STATE_SETUP_EXPIRED, **mss_evidence)
        return SetupState(**base, state=STATE_WAITING_RETEST, reason_code="RETEST_NOT_YET_FOUND", **mss_evidence)

    plan = build_target_plan(
        trade_direction, retest.entry_price, sweep.extreme_price, box.session_mid, box.session_high, box.session_low,
        symbol_meta, sl_buffer_pips,
    )
    plan_evidence = dict(
        **mss_evidence, entry=plan.entry, stop_loss=plan.stop_loss, tp1=plan.tp1, tp2=plan.tp2,
        risk_distance=plan.risk_distance, tp2_r_multiple=plan.tp2_r_multiple,
    )
    if plan.status != GEOMETRY_VALID:
        return SetupState(**base, state=STATE_NO_TRADE_TARGET_GEOMETRY, reason_code=STATE_NO_TRADE_TARGET_GEOMETRY, **plan_evidence)

    volume, risk_amount, size_reason = size_position(plan.entry, plan.stop_loss, equity, risk_percent, symbol_meta)
    if size_reason is not None:
        return SetupState(**base, state=STATE_NO_TRADE_TARGET_GEOMETRY, reason_code=size_reason, **plan_evidence)

    return SetupState(
        **base, state=STATE_ENTRY_READY, reason_code="RETEST_CONFIRMED",
        volume=volume, risk_amount=risk_amount, **plan_evidence,
    )


# --------------------------------------------------------------------- position lifecycle
# Pure, idempotent transitions for the post-entry states. These record what the execution
# layer has ALREADY done (an order was actually sent, TP1 actually filled, ...); this
# module never triggers those actions itself -- see this file's module docstring.

def transition_order_submitted(state: SetupState) -> SetupState:
    if state.state in TERMINAL_STATES or state.state != STATE_ENTRY_READY:
        return state
    return replace(state, state="ORDER_SUBMITTED", reason_code="ORDER_SUBMITTED")


def transition_position_open(state: SetupState) -> SetupState:
    if state.state != "ORDER_SUBMITTED":
        return state
    return replace(state, state=STATE_POSITION_OPEN, reason_code=STATE_POSITION_OPEN)


def transition_tp1_hit(state: SetupState, tp1_volume_pct: float) -> SetupState:
    """50% partial close at TP1 (spec) then move SL to breakeven -- see this package's
    docstring / status report for why this is NOT routed through
    trade_management.rules.evaluate_partial_profit (that rule's PARTIAL_CLOSE_FRACTION is
    frozen at 0.75, "not user-configurable in V1" per its own docstring, so it cannot
    serve a 50% partial without touching that shared, explicitly-frozen contract)."""
    if state.state != STATE_POSITION_OPEN:
        return state
    return replace(
        state, state=STATE_TP1_HIT, reason_code="TP1_REACHED",
        evidence={**state.evidence, "tp1_close_pct": tp1_volume_pct, "sl_moved_to_breakeven": True},
    )


def transition_runner_active(state: SetupState) -> SetupState:
    if state.state != STATE_TP1_HIT:
        return state
    return replace(state, state=STATE_RUNNER_ACTIVE, reason_code=STATE_RUNNER_ACTIVE, stop_loss=state.entry)


def transition_tp2_hit(state: SetupState) -> SetupState:
    if state.state != STATE_RUNNER_ACTIVE:
        return state
    return replace(state, state=STATE_TP2_HIT, reason_code=STATE_TP2_HIT)


def transition_stopped(state: SetupState) -> SetupState:
    if state.state in TERMINAL_STATES:
        return state
    return replace(state, state=STATE_STOPPED, reason_code=STATE_STOPPED)


class SweepRetestRuntime:
    """Restart-safe wrapper: persists every evaluate_setup() result keyed by setup_id and
    refuses to re-evaluate a setup_id already in a terminal state -- a duplicate/replayed
    call for the same setup_id is a no-op once terminal (idempotency), and a call after a
    process restart simply reloads (or recomputes, bit-identically -- see module
    docstring) the same in-flight state rather than losing progress."""

    def __init__(self, store: Optional[SweepRetestStateStore] = None):
        self.store = store or SweepRetestStateStore()

    def evaluate(self, **kwargs) -> SetupState:
        setup_id = kwargs["setup_id"]
        prior = self.store.load(setup_id)
        if prior is not None and prior.state in TERMINAL_STATES:
            return prior
        computed = evaluate_setup(**kwargs)
        self.store.save(computed)
        return computed
