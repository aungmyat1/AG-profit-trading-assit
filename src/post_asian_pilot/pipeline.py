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

import logging

import session_clock as sc
from execution_runtime.data_provider import fetch_equity
from runtime_state.store import StateStoreCorrupted
from mt5.market_data import MarketDataError, get_candles
from mt5.symbol_resolver import SymbolMeta, SymbolMetaError, get_symbol_meta
from strategy_engine.engine import evaluate as evaluate_strategy
from strategy_engine.loader import load_strategy
from strategy_engine.models import StrategyConfig

from proposal_envelope.adapters.fx_adapter import to_canonical_proposal as fx_to_canonical_proposal
from proposal_envelope.formation_gate import apply_formation_gate
from proposal_envelope.ledger import ProposalLedger
from proposal_envelope.models import PROPOSAL_READY
from strategy_contract.decision import from_fx_decision
from strategy_contract.market_snapshot import MarketSnapshot, from_real_candle

from .fingerprint import fingerprint as _config_fingerprint

from .decision import (
    PostAsianDecision,
    STATUS_DATA_ERROR,
    STATUS_READY,
    STATUS_WATCH,
    data_error_decision,
    map_trade_signal_to_decision,
    watch_decision,
)
import dataclasses

from .governor import PORTFOLIO_ELIGIBLE, PORTFOLIO_SELECTED, evaluate_daily_governor
from .monitor import (
    COUNTER_DATA_ERRORS,
    COUNTER_DUPLICATE_SUPPRESSED,
    COUNTER_NEW_CLOSED_M15,
    COUNTER_PROPOSALS_CREATED,
    COUNTER_READY_TRANSITIONS,
    COUNTER_RESTART_RECOVERY,
    COUNTER_SNAPSHOT_CONFLICTS,
)
from .pilot_config import DEFAULT_RELEASE_CONFIG_PATH, PilotConfig, load_pilot_config, load_raw_yaml
from .proposal import PostAsianEntryProposal, build_entry_proposal
from .snapshot import AsianSessionSnapshot, build_asian_session_snapshot
from .store import (
    DEFAULT_STATE_DIR,
    PilotStores,
    SnapshotImmutabilityViolation,
    decision_from_record,
    save_decision,
    save_proposal,
    save_snapshot,
)
from .tiebreak import order_candidates

logger = logging.getLogger("post_asian_pilot.pipeline")


@dataclass(frozen=True)
class PairResult:
    symbol: str
    decision: PostAsianDecision
    portfolio_state: str
    portfolio_reason_code: Optional[str]
    proposal: Optional[PostAsianEntryProposal]
    # WP11A (AG_CANONICAL_R2_R4_PROPOSAL_PIPELINE_V1): the REAL MarketSnapshot for the
    # exact closed candle that produced `decision` THIS cycle -- only set on a genuine
    # fresh evaluation (the "new closed M15" branch of _evaluate_pair), never on the
    # cached/restart-recovery branch, which re-reads an already-persisted native
    # decision rather than fetching fresh data. None means "no fresh REAL provenance
    # this cycle" -- the canonical pipeline correctly skips formation for that case
    # rather than reconstructing/guessing a snapshot after the fact.
    market_snapshot: Optional[MarketSnapshot] = None


@dataclass(frozen=True)
class PilotCycleResult:
    pilot_config: PilotConfig
    strategy: StrategyConfig
    release_id: str
    evaluation_time: dt.datetime
    trading_date: dt.date
    pairs: Tuple[PairResult, ...]
    ledger_slots_used: int
    ledger_max_slots: int


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
        stores.counters.increment(strategy.strategy_id, trading_date, COUNTER_DATA_ERRORS)
        decision = data_error_decision(strategy.strategy_id, strategy.version, symbol, trading_date,
                                       pilot.reference_session_name, now, (exc.reason_code,))
        save_decision(stores.decision_store, decision)
        return PairResult(symbol, decision, "ELIGIBLE", None, None)

    snap_result = build_asian_session_snapshot(
        strategy.strategy_id, symbol, trading_date, pilot.reference_session_name,
        ref_start, ref_end, asian_candles, expected_bars, as_of=now,
    )
    if snap_result.status == "DATA_ERROR":
        stores.counters.increment(strategy.strategy_id, trading_date, COUNTER_DATA_ERRORS)
        decision = data_error_decision(strategy.strategy_id, strategy.version, symbol, trading_date,
                                       pilot.reference_session_name, now, snap_result.reason_codes)
        save_decision(stores.decision_store, decision)
        return PairResult(symbol, decision, "ELIGIBLE", None, None)

    snapshot: AsianSessionSnapshot = snap_result.snapshot
    try:
        save_snapshot(stores.snapshot_store, snapshot)
    except SnapshotImmutabilityViolation:
        # A legitimate DIFFERENT snapshot was computed for an identity already frozen --
        # fail closed, never overwrite the immutable frozen snapshot (spec section 9/10).
        stores.counters.increment(strategy.strategy_id, trading_date, COUNTER_SNAPSHOT_CONFLICTS)
        decision = data_error_decision(strategy.strategy_id, strategy.version, symbol, trading_date,
                                       pilot.reference_session_name, now, ("SNAPSHOT_IMMUTABILITY_VIOLATION",))
        save_decision(stores.decision_store, decision)
        return PairResult(symbol, decision, "ELIGIBLE", None, None)
    except StateStoreCorrupted:
        # The stored snapshot file itself is unreadable/malformed -- fail closed, never
        # silently regenerate/overwrite (spec section 11).
        decision = data_error_decision(strategy.strategy_id, strategy.version, symbol, trading_date,
                                       pilot.reference_session_name, now, ("ASIAN_SNAPSHOT_CORRUPT",))
        save_decision(stores.decision_store, decision)
        return PairResult(symbol, decision, "ELIGIBLE", None, None)

    if now < window_start:
        decision = watch_decision(strategy.strategy_id, strategy.version, symbol, trading_date,
                                  pilot.reference_session_name, now, "WAITING_EXECUTION_WINDOW_OPEN",
                                  valid_until=window_start)
        save_decision(stores.decision_store, decision)
        return PairResult(symbol, decision, "ELIGIBLE", None, None)

    try:
        post_candles = get_candles(symbol, "M15", window_start, min(now, window_end))
    except MarketDataError as exc:
        stores.counters.increment(strategy.strategy_id, trading_date, COUNTER_DATA_ERRORS)
        decision = data_error_decision(strategy.strategy_id, strategy.version, symbol, trading_date,
                                       pilot.reference_session_name, now, (exc.reason_code,))
        save_decision(stores.decision_store, decision)
        return PairResult(symbol, decision, "ELIGIBLE", None, None)

    if not post_candles or not stores.bar_tracker.is_new_bar(symbol, "M15", post_candles[-1].time):
        # No new closed M15 since the last evaluation -- return last persisted decision,
        # never re-evaluate the same bar (spec: "same candle polled repeatedly -> no
        # repeated evaluation"). Reconstructing a persisted READY here (restart or a
        # plain repeated poll) is exactly the recovery path spec section 5/7 requires --
        # decision_from_record() rebuilds the same authoritative signal, never re-runs
        # the strategy or invents evidence.
        cached = stores.decision_store.get(
            f"{strategy.strategy_id}|{symbol}|{trading_date.isoformat()}|{pilot.reference_session_name}")
        if cached is not None:
            decision = decision_from_record(cached)
            if decision.status == STATUS_READY:
                stores.counters.increment(strategy.strategy_id, trading_date, COUNTER_RESTART_RECOVERY)
        else:
            decision = watch_decision(strategy.strategy_id, strategy.version, symbol, trading_date,
                                      pilot.reference_session_name, now, "WAITING_CLOSED_M15_CONFIRMATION",
                                      valid_until=window_end)
        return PairResult(symbol, decision, "ELIGIBLE", None, None)

    stores.counters.increment(strategy.strategy_id, trading_date, COUNTER_NEW_CLOSED_M15)
    signal = evaluate_strategy(strategy, pilot.pair_id, symbol, trading_date, list(asian_candles), expected_bars,
                               post_session_candles=list(post_candles))
    decision = map_trade_signal_to_decision(signal, snapshot.snapshot_id, now, window_end)
    wrote = save_decision(stores.decision_store, decision)
    if wrote and decision.status == STATUS_READY:
        stores.counters.increment(strategy.strategy_id, trading_date, COUNTER_READY_TRANSITIONS)
    elif not wrote:
        stores.counters.increment(strategy.strategy_id, trading_date, COUNTER_DUPLICATE_SUPPRESSED)
    stores.bar_tracker.mark_processed(symbol, "M15", post_candles[-1].time)
    # WP11A: wrap the exact closed candle that drove this evaluation as REAL market-truth
    # provenance -- no second fetch, no reconstruction after the fact (see PairResult's
    # market_snapshot docstring).
    market_snapshot = from_real_candle(symbol, "M15", post_candles[-1])
    return PairResult(symbol, decision, "ELIGIBLE", None, None, market_snapshot)


def _form_canonical_proposal(
    decision: PostAsianDecision, actionable_proposal: PostAsianEntryProposal,
    market_snapshot: Optional[MarketSnapshot], proposal_ledger: ProposalLedger,
    config_hash: Optional[str] = None, engine_release: Optional[str] = None,
) -> None:
    """WP11A (AG_CANONICAL_R2_R4_PROPOSAL_PIPELINE_V1): additive canonical-pipeline
    wiring. Reuses the existing WP4 decision adapter, WP7 fx proposal-envelope adapter,
    WP6 formation gate, and WP8 ledger exactly as built -- no new proposal identity, no
    reinterpretation of strategy logic, no execution call. Any exception here is caught
    and logged by the caller and MUST NEVER affect the native pipeline's own decision,
    proposal, governor, or ledger behavior -- this function has no return value and no
    side effect visible to the native pipeline, only to the separate canonical ledger.

    market_snapshot is None on the cached/restart-recovery path (no fresh REAL
    provenance this cycle) -- apply_formation_gate already fails closed on a missing
    snapshot (REASON_MISSING_MARKET_SNAPSHOT), so this still correctly forms no
    canonical proposal rather than guessing provenance.

    config_hash/engine_release (P8, this phase): caller-supplied from the two
    authoritative sources already computed elsewhere in this module --
    post_asian_pilot.fingerprint.fingerprint() over the strategy's own YAML (config_hash)
    and the release config's release_id (engine_release). Neither is recomputed or
    guessed here. git_commit is deliberately NEVER set (stays None) -- no authoritative
    runtime producer exists anywhere in this repository (P8 finding); no subprocess git
    call, CI assumption, or placeholder value is introduced."""
    strategy_decision = from_fx_decision(decision, market_snapshot=market_snapshot)
    envelope = fx_to_canonical_proposal(decision, actionable_proposal.trade_proposal)
    gated = apply_formation_gate(envelope, market_snapshot=market_snapshot)
    if gated.proposal_state == PROPOSAL_READY:
        gated = dataclasses.replace(
            gated, config_hash=config_hash, engine_release=engine_release, git_commit=None,
        )
        proposal_ledger.record_proposal(gated)
    else:
        logger.info(
            "WP11A canonical proposal formation rejected symbol=%s reasons=%s",
            decision.symbol, gated.reasons,
        )
    # strategy_decision is constructed to prove/exercise the WP4 propagation path end to
    # end in the live cycle; the canonical envelope/gate/ledger chain above is what
    # persists, matching the plan's "adapter may not reinterpret strategy logic" rule --
    # nothing about strategy_decision itself is persisted separately in this phase.
    del strategy_decision


def run_pilot_cycle(
    pilot_path: str = None, now: Optional[dt.datetime] = None,
    proposal_ledger: Optional[ProposalLedger] = None,
    persist_canonical_proposal: bool = True,
) -> PilotCycleResult:
    pilot = load_pilot_config(pilot_path) if pilot_path else load_pilot_config()
    strategy = load_strategy(pilot.strategy_source_path)
    release_id = load_raw_yaml(DEFAULT_RELEASE_CONFIG_PATH).get("release_id", "AG_TRADE_ASSISTANT_V1_0_1")
    now = now or dt.datetime.now(dt.timezone.utc)
    trading_date = now.date()
    stores = PilotStores.default(pilot.strategy_id, pilot.state_dir or DEFAULT_STATE_DIR)
    proposal_ledger = proposal_ledger if proposal_ledger is not None else ProposalLedger()
    # P8: reuse the existing authoritative strategy-config fingerprint (same function
    # post_asian_pilot/report.py::release_fingerprints() already uses for
    # strategy_fingerprint) as WP11A's canonical config_hash -- no second hashing
    # algorithm. engine_release reuses release_id, already computed above.
    canonical_config_hash = _config_fingerprint(load_raw_yaml(pilot.strategy_source_path))

    results = [_evaluate_pair(pilot, strategy, symbol, trading_date, now, stores) for symbol in pilot.universe]

    ready = [r.decision for r in results if r.decision.status == STATUS_READY]
    ordered_ready = order_candidates(ready, priority=pilot.tie_break_priority)

    final_by_symbol: dict = {}
    market_snapshot_by_symbol: dict = {}
    for r in results:
        final_by_symbol[r.symbol] = r
        market_snapshot_by_symbol[r.symbol] = r.market_snapshot

    # Selection ordering (spec section 12/13): candidates claim slots in deterministic
    # ready_at order -- both may succeed (capacity 2, one slot per symbol), unlike the
    # old winner-take-all V1.0 tie-break. Claim-before-actionable-publication: the
    # proposal is only persisted as actionable once its exact identity atomically owns
    # a ledger slot.
    for decision in ordered_ready:
        symbol = decision.symbol
        try:
            equity = fetch_equity()
            symbol_meta: SymbolMeta = get_symbol_meta(symbol)
        except (MarketDataError, SymbolMetaError) as exc:
            reason = getattr(exc, "reason_code", "ACCOUNT_DATA_MISSING")
            final_by_symbol[symbol] = PairResult(symbol, decision, "BLOCKED", reason, None)
            continue

        # The swept level is the session boundary ON THE SIDE OF THE SWEEP -- SHORT
        # (upper sweep) swept box_high, LONG (lower sweep) swept box_low; the OPPOSITE
        # boundary is separately used as TP1 (execution.validator.leg1_take_profit).
        swept_level = (decision.signal.box_high if decision.signal.direction == "SHORT"
                      else decision.signal.box_low) if decision.signal else None
        prop_result = build_entry_proposal(decision, strategy, equity, symbol_meta,
                                           pilot.risk_per_trade_pct, decision.session_snapshot_id,
                                           swept_level=swept_level)
        if prop_result.status != "READY" or prop_result.proposal is None:
            final_by_symbol[symbol] = PairResult(symbol, decision, "BLOCKED", prop_result.reason_code, None)
            continue
        candidate_proposal = prop_result.proposal  # in-memory candidate -- not yet actionable

        gate = evaluate_daily_governor(strategy.strategy_id, trading_date, stores.daily_loss_guard,
                                       pilot.strategy_daily_loss_limit_r)
        if gate.portfolio_state != PORTFOLIO_ELIGIBLE:
            save_proposal(stores.proposal_store, candidate_proposal)  # evidence only, actionable=False
            final_by_symbol[symbol] = PairResult(symbol, decision, gate.portfolio_state, gate.reason_code,
                                                 candidate_proposal)
            continue

        claim = stores.ledger.try_claim(
            strategy.strategy_id, strategy.version, release_id, trading_date, symbol,
            candidate_proposal.setup_id, candidate_proposal.proposal_id, decision.ready_at, now,
        )
        if not claim.success:
            save_proposal(stores.proposal_store, candidate_proposal)  # evidence only, actionable=False
            final_by_symbol[symbol] = PairResult(symbol, decision, "BLOCKED", claim.reason_code,
                                                 candidate_proposal)
            continue

        actionable_proposal = dataclasses.replace(candidate_proposal, actionable=True)
        if save_proposal(stores.proposal_store, actionable_proposal):
            stores.counters.increment(strategy.strategy_id, trading_date, COUNTER_PROPOSALS_CREATED)
        final_by_symbol[symbol] = PairResult(symbol, decision, PORTFOLIO_SELECTED, None, actionable_proposal)

        # WP11A: additive canonical R2-R4 pipeline wiring. Deliberately isolated from the
        # native pipeline above -- any exception here is caught, logged, and never
        # propagated, so a bug in the canonical layer can never block, alter, or delay an
        # actionable native proposal or its governor/ledger claim.
        #
        # persist_canonical_proposal=False (observational callers only -- e.g.
        # scripts/run_post_asian_pilot.py --status) skips this entirely rather than
        # swapping in a throwaway ProposalLedger: _form_canonical_proposal() has no
        # return value and, per its own docstring, no side effect visible to the native
        # pipeline above -- so not calling it changes nothing else about this cycle's
        # result, only whether the separate durable canonical ledger gets a new record.
        if persist_canonical_proposal:
            try:
                _form_canonical_proposal(
                    decision, actionable_proposal, market_snapshot_by_symbol.get(symbol), proposal_ledger,
                    config_hash=canonical_config_hash, engine_release=release_id,
                )
            except Exception:  # noqa: BLE001 -- see docstring: must never affect native behavior
                logger.exception("WP11A canonical proposal formation failed for symbol=%s (native pipeline unaffected)", symbol)

    final = tuple(final_by_symbol[symbol] for symbol in pilot.universe)
    slots_used = stores.ledger.consumed_count(strategy.strategy_id, trading_date)
    return PilotCycleResult(pilot, strategy, release_id, now, trading_date, final,
                            slots_used, stores.ledger.max_slots)
