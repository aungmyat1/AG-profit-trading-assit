"""One evaluation cycle: for each pilot-universe symbol, freeze/reuse the Asian snapshot,
gate on the execution window and new-closed-M15-only, evaluate the strategy (via
strategy_engine.evaluate(), never E1/E2/E3 discovery or execution.executor/mt5_gateway),
normalize to a PostAsianDecision, resolve the cross-symbol tie-break, apply the daily
governor, and persist everything. Orchestration only -- every computation delegates to an
already-existing, already-verified module (see each imported function's own docstring).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import List, Optional, Tuple

import session_clock as sc
from execution_runtime.data_provider import fetch_equity
from mt5.market_data import MarketDataError, get_candles
from mt5.symbol_resolver import SymbolMeta, SymbolMetaError, get_symbol_meta
from strategy_engine.engine import evaluate as evaluate_strategy
from strategy_engine.loader import load_strategy
from strategy_engine.models import StrategyConfig

from .decision import (
    PostAsianDecision,
    STATUS_DATA_ERROR,
    STATUS_READY,
    STATUS_WATCH,
    data_error_decision,
    map_trade_signal_to_decision,
    watch_decision,
)
from .governor import PORTFOLIO_ELIGIBLE, evaluate_daily_governor
from .pilot_config import PilotConfig, load_pilot_config
from .proposal import PostAsianEntryProposal, build_entry_proposal
from .snapshot import AsianSessionSnapshot, build_asian_session_snapshot
from .store import PilotStores, decision_from_record, save_decision, save_proposal, save_snapshot
from .tiebreak import RESULT_CLAIMED, resolve_tiebreak


@dataclass(frozen=True)
class PairResult:
    symbol: str
    decision: PostAsianDecision
    portfolio_state: str
    portfolio_reason_code: Optional[str]
    proposal: Optional[PostAsianEntryProposal]


@dataclass(frozen=True)
class PilotCycleResult:
    pilot_config: PilotConfig
    strategy: StrategyConfig
    evaluation_time: dt.datetime
    trading_date: dt.date
    pairs: Tuple[PairResult, ...]
    tiebreak_status: str


def _asian_bounds(trading_date: dt.date, reference_session_name: str) -> Tuple[dt.datetime, dt.datetime, int]:
    start, end = sc.get_session_bounds(trading_date, reference_session_name)
    expected = sc.expected_bar_count(reference_session_name, "M15")
    return start, end, expected


def _evaluate_pair(
    pilot: PilotConfig, strategy: StrategyConfig, symbol: str, trading_date: dt.date,
    now: dt.datetime, stores: PilotStores,
) -> PairResult:
    ref_start, ref_end, expected_bars = _asian_bounds(trading_date, pilot.reference_session_name)
    window_start = dt.datetime.combine(trading_date, dt.time.fromisoformat(pilot.execution_window_start_utc),
                                       tzinfo=dt.timezone.utc)
    window_end = dt.datetime.combine(trading_date, dt.time.fromisoformat(pilot.execution_window_end_utc),
                                     tzinfo=dt.timezone.utc)

    if now < ref_end:
        decision = watch_decision(strategy.strategy_id, strategy.version, symbol, trading_date,
                                  pilot.reference_session_name, now, "WAITING_REFERENCE_SESSION_COMPLETION",
                                  valid_until=ref_end)
        save_decision(stores.decision_store, decision)
        return PairResult(symbol, decision, "ELIGIBLE", None, None)

    try:
        asian_candles = get_candles(symbol, "M15", ref_start, ref_end)
    except MarketDataError as exc:
        decision = data_error_decision(strategy.strategy_id, strategy.version, symbol, trading_date,
                                       pilot.reference_session_name, now, (exc.reason_code,))
        save_decision(stores.decision_store, decision)
        return PairResult(symbol, decision, "ELIGIBLE", None, None)

    snap_result = build_asian_session_snapshot(
        strategy.strategy_id, symbol, trading_date, pilot.reference_session_name,
        ref_start, ref_end, asian_candles, expected_bars, as_of=now,
    )
    if snap_result.status == "DATA_ERROR":
        decision = data_error_decision(strategy.strategy_id, strategy.version, symbol, trading_date,
                                       pilot.reference_session_name, now, snap_result.reason_codes)
        save_decision(stores.decision_store, decision)
        return PairResult(symbol, decision, "ELIGIBLE", None, None)

    snapshot: AsianSessionSnapshot = snap_result.snapshot
    save_snapshot(stores.snapshot_store, snapshot)

    if now < window_start:
        decision = watch_decision(strategy.strategy_id, strategy.version, symbol, trading_date,
                                  pilot.reference_session_name, now, "WAITING_EXECUTION_WINDOW_OPEN",
                                  valid_until=window_start)
        save_decision(stores.decision_store, decision)
        return PairResult(symbol, decision, "ELIGIBLE", None, None)

    try:
        post_candles = get_candles(symbol, "M15", window_start, min(now, window_end))
    except MarketDataError as exc:
        decision = data_error_decision(strategy.strategy_id, strategy.version, symbol, trading_date,
                                       pilot.reference_session_name, now, (exc.reason_code,))
        save_decision(stores.decision_store, decision)
        return PairResult(symbol, decision, "ELIGIBLE", None, None)

    if not post_candles or not stores.bar_tracker.is_new_bar(symbol, "M15", post_candles[-1].time):
        # No new closed M15 since the last evaluation -- return last persisted decision,
        # never re-evaluate the same bar (spec: "same candle polled repeatedly -> no
        # repeated evaluation").
        cached = stores.decision_store.get(
            f"{strategy.strategy_id}|{symbol}|{trading_date.isoformat()}|{pilot.reference_session_name}")
        if cached is not None:
            decision = decision_from_record(cached)
        else:
            decision = watch_decision(strategy.strategy_id, strategy.version, symbol, trading_date,
                                      pilot.reference_session_name, now, "WAITING_CLOSED_M15_CONFIRMATION",
                                      valid_until=window_end)
        return PairResult(symbol, decision, "ELIGIBLE", None, None)

    signal = evaluate_strategy(strategy, pilot.pair_id, symbol, trading_date, list(asian_candles), expected_bars,
                               post_session_candles=list(post_candles))
    decision = map_trade_signal_to_decision(signal, snapshot.snapshot_id, now, window_end)
    save_decision(stores.decision_store, decision)
    stores.bar_tracker.mark_processed(symbol, "M15", post_candles[-1].time)
    return PairResult(symbol, decision, "ELIGIBLE", None, None)


def run_pilot_cycle(
    pilot_path: str = None, now: Optional[dt.datetime] = None,
) -> PilotCycleResult:
    pilot = load_pilot_config(pilot_path) if pilot_path else load_pilot_config()
    strategy = load_strategy(pilot.strategy_source_path)
    now = now or dt.datetime.now(dt.timezone.utc)
    trading_date = now.date()
    stores = PilotStores.default(pilot.strategy_id)

    results = [_evaluate_pair(pilot, strategy, symbol, trading_date, now, stores) for symbol in pilot.universe]

    ready = [r.decision for r in results if r.decision.status == STATUS_READY]
    tb = resolve_tiebreak(ready)

    final: List[PairResult] = []
    for r in results:
        if r.decision.status != STATUS_READY:
            final.append(r)
            continue

        if tb.status != RESULT_CLAIMED or tb.claimed_symbol != r.symbol:
            final.append(PairResult(r.symbol, r.decision, "BLOCKED",
                                    tb.reason_code or "BLOCKED_DAILY_TRADE_LIMIT", None))
            continue

        gate = evaluate_daily_governor(strategy.strategy_id, trading_date, r.symbol,
                                       stores.open_position_guard, stores.daily_loss_guard,
                                       stores.trade_slot, pilot.strategy_daily_loss_limit_r)
        if gate.portfolio_state != PORTFOLIO_ELIGIBLE:
            final.append(PairResult(r.symbol, r.decision, gate.portfolio_state, gate.reason_code, None))
            continue

        try:
            equity = fetch_equity()
            symbol_meta: SymbolMeta = get_symbol_meta(r.symbol)
        except (MarketDataError, SymbolMetaError) as exc:
            reason = getattr(exc, "reason_code", "ACCOUNT_DATA_MISSING")
            final.append(PairResult(r.symbol, r.decision, "BLOCKED", reason, None))
            continue

        prop_result = build_entry_proposal(r.decision, strategy, equity, symbol_meta,
                                           pilot.risk_per_trade_pct, r.decision.session_snapshot_id)
        if prop_result.status != "READY" or prop_result.proposal is None:
            final.append(PairResult(r.symbol, r.decision, "BLOCKED", prop_result.reason_code, None))
            continue

        save_proposal(stores.proposal_store, prop_result.proposal)
        stores.trade_slot.claim(strategy.strategy_id, trading_date, r.symbol,
                                prop_result.proposal.setup_id, now)
        final.append(PairResult(r.symbol, r.decision, "ELIGIBLE", None, prop_result.proposal))

    return PilotCycleResult(pilot, strategy, now, trading_date, tuple(final), tb.status)
