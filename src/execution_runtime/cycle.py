"""Per-symbol closed-M5-bar event cycle for AG_DAYTRADING_RUNTIME_V1.

    new CLOSED M5 candle -> evaluate_setup() (ST_LIQUIDITY_SWEEP_RETEST_V1) -> not
    ENTRY_READY: persist + stop -> ENTRY_READY: TradeProposal.from_setup_state() ->
    ExecutionRuntimeContext.coordinator.submit(proposal, user_confirmed=...)

Every capability this module calls already exists elsewhere -- this is orchestration
only: strategy_engine.sweep_retest.SweepRetestRuntime for the pure evaluate/persist
pipeline, execution.bar_tracker.LastClosedBarStore for closed-bar dedup (spec EVENT
MODEL), execution.adapter.TradeProposal / execution.runtime_context.ExecutionRuntimeContext
for the one shared execution boundary. No MT5 call is made directly by this module --
candle/equity/symbol-meta retrieval is always INJECTED by the caller (production: real
mt5.market_data/mt5.account/mt5.symbol_resolver functions; tests: fixtures), same
dependency-injection idiom execution/executor.py and execution/coordinator.reconcile()
already use for their own MT5 reads.

user_confirmed is always forwarded, never defaulted or inferred here (spec: "Explicit
confirmation stays mandatory -- do NOT add an auto-confirm flag"): an automated poll loop
must always call this with user_confirmed=False, which surfaces CONFIRMATION_REQUIRED and
stops -- the *separate*, explicit, operator-driven confirm step (scripts/
run_ag_execution_runtime.py --confirm <setup_id>) is the only caller ever allowed to pass
True, and even then only for a setup_id this cycle already produced.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, List, Optional, Sequence

from execution.adapter import TradeProposal
from execution.bar_tracker import LastClosedBarStore
from execution.coordinator import CoordinatorResult
from execution.runtime_context import ExecutionRuntimeContext
from market_structure.models import MarketStructureConfig
from mt5.symbol_resolver import SymbolMeta
from strategy_engine.session import Candle
from strategy_engine.sweep_retest.config import ProfileConfig, SweepRetestStrategyConfig
from strategy_engine.sweep_retest.engine import SweepRetestRuntime
from strategy_engine.sweep_retest.models import STATE_ENTRY_READY, SetupState

from . import events

M5 = "M5"

# Candle-fetch callables injected by the caller -- see module docstring.
ReferenceCandlesFn = Callable[[str, ProfileConfig, datetime], Sequence[Candle]]
H1CandlesFn = Callable[[str], Sequence[Candle]]
M5CandlesFn = Callable[[str], Sequence[Candle]]
SymbolMetaFn = Callable[[str], SymbolMeta]
StopBufferFn = Callable[[str, ProfileConfig], float]
EquityFn = Callable[[], float]


@dataclass(frozen=True)
class CycleResult:
    symbol: str
    status: str  # NO_NEW_BAR / EVALUATED / SUBMITTED
    setup_state: Optional[SetupState] = None
    coordinator_result: Optional[CoordinatorResult] = None


def _trading_day(m5_candles: Sequence[Candle], now: Optional[datetime]) -> date:
    if m5_candles:
        return m5_candles[-1].time.date()
    return (now or datetime.now(tz=None)).date()


def _emit_transition_events(symbol: str, prior: Optional[SetupState], new: SetupState) -> None:
    """Compact, meaningful-transition-only logging (spec LOGGING). Detects "first time
    this evidence field appeared" rather than hardcoding one event per raw state name, so
    it works identically for the Forex and Crypto profiles without a second mapping."""
    if prior is not None and prior.state == new.state and prior.evaluated_at == new.evaluated_at:
        return  # terminal-state replay (SweepRetestRuntime short-circuit) -- nothing new happened

    def _first_time(field: str) -> bool:
        return getattr(new, field, None) is not None and (prior is None or getattr(prior, field, None) is None)

    if _first_time("ref_high"):
        events.emit(events.EVENT_REFERENCE_READY, symbol=symbol, setup_id=new.setup_id,
                     ref_high=new.ref_high, ref_low=new.ref_low, ref_mid=new.ref_mid)
    if _first_time("sweep_time"):
        events.emit(events.EVENT_SWEEP_DETECTED, symbol=symbol, setup_id=new.setup_id,
                     sweep_level=new.sweep_level, sweep_extreme=new.sweep_extreme, direction=new.direction)
    if _first_time("broken_swing_price"):
        events.emit(events.EVENT_MSS_CONFIRMED, symbol=symbol, setup_id=new.setup_id,
                     broken_swing_price=new.broken_swing_price)
    if new.state == STATE_ENTRY_READY and (prior is None or prior.state != STATE_ENTRY_READY):
        events.emit(events.EVENT_RETEST_READY, symbol=symbol, setup_id=new.setup_id, entry=new.entry)
        events.emit(events.EVENT_ENTRY_READY, symbol=symbol, setup_id=new.setup_id, direction=new.direction,
                     entry=new.entry, stop_loss=new.stop_loss, tp1=new.tp1, tp2=new.tp2, volume=new.volume)
    if new.state == "BLOCKED_OPEN_POSITION" and (prior is None or prior.state != new.state):
        events.emit(events.EVENT_BLOCKED_OPEN_POSITION, symbol=symbol, setup_id=new.setup_id)
    if new.state == "BLOCKED_DAILY_LOSS" and (prior is None or prior.state != new.state):
        events.emit(events.EVENT_BLOCKED_DAILY_LOSS, symbol=symbol, setup_id=new.setup_id)


def evaluate_and_route(
    *,
    symbol: str,
    profile_config: ProfileConfig,
    strategy_config: SweepRetestStrategyConfig,
    runtime: SweepRetestRuntime,
    bar_tracker: LastClosedBarStore,
    ctx: ExecutionRuntimeContext,
    fetch_m5_candles: M5CandlesFn,
    fetch_h1_candles: H1CandlesFn,
    fetch_reference_candles: ReferenceCandlesFn,
    symbol_meta: SymbolMeta,
    stop_buffer_price: float,
    equity: float,
    reference_expected_bar_count: Optional[int] = None,
    market_structure_config: Optional[MarketStructureConfig] = None,
    user_confirmed: bool = False,
    now: Optional[datetime] = None,
) -> CycleResult:
    """One symbol's closed-M5-bar event cycle. Never re-evaluates the same closed M5 bar
    twice (bar_tracker) and never re-submits a setup_id already routed to the coordinator
    (SweepRetestRuntime's own terminal-state short-circuit handles WAITING_*/ENTRY_READY;
    ExecutionCoordinator.submit's own journal.has_executed() check handles a repeated
    ENTRY_READY submission -- see coordinator.py's IDEMPOTENCY docstring)."""
    m5_candles = list(fetch_m5_candles(symbol))
    if not m5_candles:
        return CycleResult(symbol=symbol, status="NO_DATA")

    latest_bar_time = m5_candles[-1].time
    if not bar_tracker.is_new_bar(symbol, M5, latest_bar_time):
        return CycleResult(symbol=symbol, status="NO_NEW_BAR")

    trading_day = _trading_day(m5_candles, now)
    setup_id = f"{symbol}:{trading_day.isoformat()}"
    h1_candles = list(fetch_h1_candles(symbol))
    reference_candles = list(fetch_reference_candles(symbol, profile_config, now or latest_bar_time))

    prior = runtime.store.load(setup_id)
    setup_state = runtime.evaluate(
        setup_id=setup_id, strategy_id=strategy_config.strategy_id, symbol=symbol,
        trading_day=trading_day, profile=profile_config.profile,
        reference_candles=reference_candles, h1_candles=h1_candles, m5_candles=m5_candles,
        execution_windows=profile_config.profile.execution_windows, equity=equity,
        symbol_meta=symbol_meta, risk_percent=strategy_config.risk_percent,
        stop_buffer_price=stop_buffer_price, reference_expected_bar_count=reference_expected_bar_count,
        entry_ttl_m5_bars=strategy_config.entry_ttl_m5_bars, market_structure_config=market_structure_config,
        daily_loss_guard=ctx.daily_loss_guard, open_position_guard=ctx.open_position_guard,
        now=now,
    )
    bar_tracker.mark_processed(symbol, M5, latest_bar_time)
    _emit_transition_events(symbol, prior, setup_state)

    if setup_state.state != STATE_ENTRY_READY:
        return CycleResult(symbol=symbol, status="EVALUATED", setup_state=setup_state)

    proposal = TradeProposal.from_setup_state(setup_state)
    result = ctx.coordinator.submit(proposal, user_confirmed=user_confirmed, now=now)
    _emit_submit_event(symbol, result)
    return CycleResult(symbol=symbol, status="SUBMITTED", setup_state=setup_state, coordinator_result=result)


def _emit_submit_event(symbol: str, result: CoordinatorResult) -> None:
    if result.status == "CONFIRMATION_REQUIRED":
        events.emit(events.EVENT_CONFIRMATION_REQUIRED, symbol=symbol, setup_id=result.setup_id)
    elif result.status == "EXECUTION_DELEGATED":
        events.emit(events.EVENT_EXECUTED, symbol=symbol, setup_id=result.setup_id)
    elif result.status == "PROPOSAL_ONLY":
        events.emit(events.EVENT_PROPOSAL_ONLY, symbol=symbol, setup_id=result.setup_id)
    elif result.status == "BLOCKED_OPEN_POSITION":
        events.emit(events.EVENT_BLOCKED_OPEN_POSITION, symbol=symbol, setup_id=result.setup_id)
    elif result.status == "BLOCKED_DAILY_LOSS":
        events.emit(events.EVENT_BLOCKED_DAILY_LOSS, symbol=symbol, setup_id=result.setup_id)


def confirm_and_submit(
    *,
    symbol: str,
    setup_id: str,
    runtime: SweepRetestRuntime,
    ctx: ExecutionRuntimeContext,
    now: Optional[datetime] = None,
) -> CycleResult:
    """The ONLY path that may ever pass user_confirmed=True: re-loads the ALREADY-computed
    ENTRY_READY SetupState for `setup_id` (never recomputes it from fresh candles -- an
    explicit confirmation confirms the setup the operator was shown, not a new
    evaluation) and resubmits with explicit confirmation. Called only from an operator-
    driven entrypoint (scripts/run_ag_execution_runtime.py --confirm), never from the
    automated poll loop."""
    setup_state = runtime.store.load(setup_id)
    if setup_state is None or setup_state.state != STATE_ENTRY_READY:
        return CycleResult(symbol=symbol, status="NO_PENDING_ENTRY_READY_SETUP")
    proposal = TradeProposal.from_setup_state(setup_state)
    result = ctx.coordinator.submit(proposal, user_confirmed=True, now=now)
    _emit_submit_event(symbol, result)
    return CycleResult(symbol=symbol, status="SUBMITTED", setup_state=setup_state, coordinator_result=result)
