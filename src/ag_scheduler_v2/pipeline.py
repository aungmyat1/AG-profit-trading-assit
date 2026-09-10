"""M15 processing pipeline (spec section 16). Orchestration only -- calls the
authoritative strategy_manager.evaluate() for signal semantics, never reimplements
S1/S2/S3/BOS/FVG/campaign-risk rules itself (spec section 17). No mock/placeholder
proposal is ever fabricated: a candidate exists only if strategy_manager.evaluate()
actually returned one (spec section 18).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace
from typing import Callable, Optional, Sequence

from assistant.models import STATUS_TRADE_CANDIDATE, STATUS_TRADE_READY, MODE_ANALYZE_ONLY
from strategy_manager.manager import ManagerResult, evaluate as strategy_manager_evaluate

from ag_scheduler_v2.cycle_identity import CompletedCycleStore, cycle_id
from ag_scheduler_v2.evidence import SchedulerIdentity, ShadowEvidenceRecord
from ag_scheduler_v2.m15_clock import BarAvailabilityResult, BarSettlementPolicy, confirm_bar_available
from ag_scheduler_v2.news_provider import CalendarFetchResult, EconomicCalendarProvider, currencies_for_symbol, fetch_relevant_events
from ag_scheduler_v2.news_risk import NewsRiskEvidence, NewsRiskWindow, evaluate_news_risk
from ag_scheduler_v2.priority import Candidate, PriorityConfig, compute_priority, rank_candidates

QUALIFYING_STRATEGY_STATUSES = frozenset({STATUS_TRADE_CANDIDATE, STATUS_TRADE_READY})

REASON_DATA_STALE = "DATA_STALE"
REASON_DUPLICATE_SKIP = "DUPLICATE_SKIP"


@dataclass(frozen=True)
class M15CycleOutcome:
    cycle_id: str
    symbol: str
    session_pair: str
    bar_close_utc: dt.datetime
    observation_mode: Optional[str]  # None if skipped before classification
    processed: bool
    skip_reason: Optional[str]
    evidence: Optional[ShadowEvidenceRecord]


def process_m15_cycle(
    *,
    strategy_id: str,
    strategy_id_alias: str,
    strategy_version: str,
    symbol: str,
    session_pair: str,
    cycle_label: str,  # the strategy_manager `cycle` argument, e.g. ASIAN_LONDON
    bar_close_utc: dt.datetime,
    now_utc: dt.datetime,
    is_recovered: bool,
    provider_latest_closed_bar_utc: Optional[dt.datetime],
    settlement_policy: BarSettlementPolicy,
    cycle_store: CompletedCycleStore,
    scheduler_identity: SchedulerIdentity,
    calendar_fetch: CalendarFetchResult,
    news_window: NewsRiskWindow,
    strategy_evaluator: Callable[[str, str, str, str], ManagerResult] = strategy_manager_evaluate,
) -> M15CycleOutcome:
    """One symbol's single M15 cycle end to end. `strategy_evaluator` defaults to the
    real strategy_manager.evaluate() but is injectable for tests, matching the house
    injectable-dependency convention (spec 41: never fabricate a result in production
    mode -- tests are the only place a stub evaluator belongs)."""
    cid = cycle_id(strategy_id=strategy_id_alias, symbol=symbol, session_pair=session_pair, bar_close_utc=bar_close_utc)

    classification = cycle_store.classify(
        strategy_id=strategy_id_alias, symbol=symbol, session_pair=session_pair,
        bar_close_utc=bar_close_utc, is_recovered=is_recovered,
    )
    if classification == "DUPLICATE_SKIP":
        return M15CycleOutcome(cid, symbol, session_pair, bar_close_utc, None, False, REASON_DUPLICATE_SKIP, None)
    observation_mode = classification

    availability = confirm_bar_available(
        bar_close_utc=bar_close_utc, provider_latest_closed_bar_utc=provider_latest_closed_bar_utc,
        now_utc=now_utc, policy=settlement_policy,
    )
    if not availability.available:
        return M15CycleOutcome(cid, symbol, session_pair, bar_close_utc, observation_mode, False, availability.reason_code, None)

    news_evidence = evaluate_news_risk(
        bar_close_utc=bar_close_utc, calendar_status=calendar_fetch.status, events=calendar_fetch.events, window=news_window,
    )

    manager_result = strategy_evaluator(strategy_id, symbol, cycle_label, MODE_ANALYZE_ONLY)
    strategy_result = manager_result.strategy_result
    qualified = strategy_result.status in QUALIFYING_STRATEGY_STATUSES

    record = ShadowEvidenceRecord(
        scheduler_identity=scheduler_identity,
        cycle_id=cid,
        symbol=symbol,
        session_pair=session_pair,
        bar_close_utc=bar_close_utc.astimezone(dt.timezone.utc).isoformat(),
        observation_mode=observation_mode,
        news_status=news_evidence.news_status,
        news_state=news_evidence.news_state,
        setup_type=strategy_result.setup,
        strategy_status=strategy_result.status,
        qualified=qualified,
        priority_status="NOT_RANKED",
        priority_score=None,
        priority_rank=None,
        priority_action=None,
        reason_codes=strategy_result.reason_codes,
        recorded_at_utc=now_utc.astimezone(dt.timezone.utc).isoformat(),
    )

    cycle_store.mark_completed(
        strategy_id=strategy_id_alias, symbol=symbol, session_pair=session_pair,
        bar_close_utc=bar_close_utc, observation_mode=observation_mode, now_utc=now_utc,
    )

    return M15CycleOutcome(cid, symbol, session_pair, bar_close_utc, observation_mode, True, None, record)


def rank_qualified_outcomes(
    outcomes: Sequence[M15CycleOutcome],
    candidates: Sequence[Candidate],
    *,
    history_by_symbol: dict,
    as_of_utc: dt.datetime,
    priority_config: PriorityConfig,
) -> tuple:
    """Simultaneous-opportunity analysis (spec 19-24): every qualified outcome is
    scored and ranked, but nothing is discarded -- ranking only annotates the evidence
    already produced by process_m15_cycle with priority metadata."""
    results = [
        compute_priority(cand, history_before_t=history_by_symbol.get(cand.symbol, ()), as_of_utc=as_of_utc, config=priority_config)
        for cand in candidates
    ]
    ranked = rank_candidates(candidates, results, config=priority_config)

    by_symbol = {rc.candidate.symbol: rc for rc in ranked}
    annotated = []
    for outcome in outcomes:
        if outcome.evidence is None or outcome.symbol not in by_symbol:
            annotated.append(outcome)
            continue
        rc = by_symbol[outcome.symbol]
        updated = replace(
            outcome.evidence,
            priority_status=rc.priority_result.priority_status,
            priority_score=rc.priority_result.priority_score,
            priority_rank=rc.rank,
            priority_action=rc.action,
        )
        annotated.append(M15CycleOutcome(
            outcome.cycle_id, outcome.symbol, outcome.session_pair, outcome.bar_close_utc,
            outcome.observation_mode, outcome.processed, outcome.skip_reason, updated,
        ))
    return tuple(annotated)


def requires_m1_fetch(outcome: M15CycleOutcome) -> bool:
    """M1 policy (spec 25): M1 never creates a setup, decision authority stays M15.
    Every qualified candidate requiring fill evidence gets an M1 fetch flag -- not only
    the top-ranked one, so validation evidence for other qualified setups is never
    destroyed by an optimization that only fetches the winner."""
    return outcome.evidence is not None and outcome.evidence.qualified
