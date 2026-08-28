"""FIVE_SKILL_ASSISTANT_RUNTIME_V1 -- the generic Trade Assistant analysis runtime.

`analyze_market(request)` is the second public runtime entry point in this package,
sibling to `assistant.runtime.evaluate()` (the strategy-execution path). Neither
supersedes the other -- see FIVE_SKILL_ASSISTANT_RUNTIME_V1_SPEC.md's "Strategy
independence" section. This module never requires a `strategy_id` and never touches
`strategy_manager`/`execution`.

Data flow:

    AssistantAnalysisRequest
            |
            v
    assistant.market_data.market_snapshot()   <- built ONCE, reused for every downstream need
            |
    +-------+-------+-------+
    v       v       v       v
 Structure S/D  Liquidity  (each requested independently; each still owns its own
    |       |       |       internal candle retrieval -- see "Known limitations" below)
    +-------+-------+
            v
   Entry & Confirmation (only if requested; auto-includes Structure+Liquidity as its
                          own declared upstream dependencies, per ENTRY_CONFIRMATION_V1's
                          own contract -- not "running everything")
            |
            v
   Trade Management (only if request.candidate is supplied -- independent of whether
                      any market skill was requested at all)
            |
            v
    FiveSkillAnalysisResult
"""
from __future__ import annotations

from datetime import datetime, timezone

from entry_confirmation import (
    CandidateDirection,
    ConfirmationState,
    EntryConfirmationRequest,
    OverallState,
    evaluate_entry_confirmation,
)
from liquidity import liquidity_result as _liquidity_result
from market_structure import analyze_structure
from supply_demand import fair_value_gaps_for, validated_order_blocks_for
from trade_management import TradeManagementRequest, evaluate_trade_management

from .analysis_models import (
    CONTEXT_UNAVAILABLE,
    OVERALL_BLOCKED,
    OVERALL_PARTIAL,
    OVERALL_READY,
    REQUESTABLE_MARKET_SKILLS,
    SKILL_BLOCKED,
    SKILL_ENTRY_CONFIRMATION,
    SKILL_LIQUIDITY,
    SKILL_MARKET_STRUCTURE,
    SKILL_NOT_REQUESTED,
    SKILL_NO_CANDIDATE,
    SKILL_PARTIAL,
    SKILL_READY,
    SKILL_SUPPLY_DEMAND,
    SKILL_TRADE_MANAGEMENT,
    SKILL_UNAVAILABLE,
    AssistantAnalysisRequest,
    FiveSkillAnalysisResult,
    SupplyDemandBundle,
)
from .market_data import market_snapshot

_MARKET_DATA_OK_STATUSES = {"OK"}


class InvalidAnalysisRequest(ValueError):
    pass


def analyze_market(request: AssistantAnalysisRequest) -> FiveSkillAnalysisResult:
    unknown = set(request.requested_skills) - set(REQUESTABLE_MARKET_SKILLS)
    if unknown:
        raise InvalidAnalysisRequest(f"Unknown requested_skills: {sorted(unknown)}")

    timestamp_utc = datetime.now(timezone.utc)
    requested = set(request.requested_skills)
    # Entry Confirmation declares Structure + Liquidity as its own upstream dependencies
    # (ENTRY_CONFIRMATION_V1_SPEC.md) -- requesting it resolves that dependency closure,
    # it does not mean "run everything."
    if SKILL_ENTRY_CONFIRMATION in requested:
        requested |= {SKILL_MARKET_STRUCTURE, SKILL_LIQUIDITY}

    # --- Market Context: built exactly once, reused for every downstream need below. ---
    snapshot = market_snapshot(request.symbol, request.timeframe)
    context_ready = snapshot.status in _MARKET_DATA_OK_STATUSES and snapshot.freshness in (None, "OK")
    market_context_status = "READY" if context_ready else (
        snapshot.freshness if snapshot.status == "OK" else snapshot.status
    )

    skill_statuses: dict = {}
    errors: list = []
    limitations: list = []

    if market_context_status != "READY":
        errors.append(f"{CONTEXT_UNAVAILABLE}: {market_context_status}")

    # --- Market Structure ---
    structure = None
    if SKILL_MARKET_STRUCTURE in requested:
        if not context_ready:
            skill_statuses[SKILL_MARKET_STRUCTURE] = SKILL_UNAVAILABLE
        else:
            structure = analyze_structure(request.symbol, request.timeframe)
            skill_statuses[SKILL_MARKET_STRUCTURE] = SKILL_READY if structure.status == "VALID" else SKILL_PARTIAL
    else:
        skill_statuses[SKILL_MARKET_STRUCTURE] = SKILL_NOT_REQUESTED

    # --- Supply & Demand ---
    supply_demand = None
    if SKILL_SUPPLY_DEMAND in requested:
        if not context_ready:
            skill_statuses[SKILL_SUPPLY_DEMAND] = SKILL_UNAVAILABLE
        else:
            # validated_order_blocks_for() returns a plain list (empty on failure, no
            # status of its own -- see SupplyDemandBundle's docstring); fair_value_gaps_for()
            # is the ZoneQueryResult that actually carries a status/reason_code.
            obs = tuple(validated_order_blocks_for(request.symbol, request.timeframe))
            fvgs = fair_value_gaps_for(request.symbol, request.timeframe)
            supply_demand = SupplyDemandBundle(validated_order_blocks=obs, fair_value_gaps=fvgs)
            skill_statuses[SKILL_SUPPLY_DEMAND] = SKILL_READY if fvgs.status == "OK" else SKILL_PARTIAL
    else:
        skill_statuses[SKILL_SUPPLY_DEMAND] = SKILL_NOT_REQUESTED

    # --- Liquidity ---
    liquidity = None
    if SKILL_LIQUIDITY in requested:
        if not context_ready:
            skill_statuses[SKILL_LIQUIDITY] = SKILL_UNAVAILABLE
        else:
            liquidity = _liquidity_result(request.symbol, request.timeframe)
            ok = liquidity.status in ("LIQUIDITY_OK", "NO_LIQUIDITY_LEVELS")
            skill_statuses[SKILL_LIQUIDITY] = SKILL_READY if ok else SKILL_PARTIAL
    else:
        skill_statuses[SKILL_LIQUIDITY] = SKILL_NOT_REQUESTED

    # --- Entry & Confirmation ---
    entry_confirmation = None
    if SKILL_ENTRY_CONFIRMATION in requested:
        if not context_ready:
            skill_statuses[SKILL_ENTRY_CONFIRMATION] = SKILL_UNAVAILABLE
        else:
            candidate_direction = (
                CandidateDirection(request.candidate.direction) if request.candidate else CandidateDirection.NONE
            )
            ec_request = EntryConfirmationRequest(
                symbol=request.symbol, timeframe=request.timeframe,
                candidate_direction=candidate_direction,
                requested_confirmations=request.requested_confirmations,
                candidate_candle=snapshot.latest_closed_candle,
                structure_result=structure, liquidity_result=liquidity,
            )
            entry_confirmation = evaluate_entry_confirmation(ec_request)
            # INDETERMINATE means at least one requested primitive is UNSIGNED_RULE/
            # UNAVAILABLE/INSUFFICIENT_DATA -- a real, visible limitation (e.g. the
            # displacement/rejection qualification gap), not a runtime failure. Any other
            # overall_state means every requested primitive resolved definitively.
            skill_statuses[SKILL_ENTRY_CONFIRMATION] = (
                SKILL_PARTIAL if entry_confirmation.overall_state == OverallState.INDETERMINATE else SKILL_READY
            )
            if entry_confirmation.overall_state == OverallState.INDETERMINATE:
                unsigned = [
                    k for k in entry_confirmation.requested_confirmations
                    if getattr(entry_confirmation, k).status == ConfirmationState.UNSIGNED_RULE
                ]
                if unsigned:
                    limitations.append(
                        f"entry_confirmation: {', '.join(unsigned)} qualification is UNSIGNED_RULE "
                        f"(measurement available, no owner-signed threshold) -- see ENTRY_CONFIRMATION_V1_SPEC.md."
                    )
    else:
        skill_statuses[SKILL_ENTRY_CONFIRMATION] = SKILL_NOT_REQUESTED

    # --- Trade Management: gated only by candidate presence, independent of requested_skills. ---
    trade_management = None
    if request.candidate is None:
        skill_statuses[SKILL_TRADE_MANAGEMENT] = SKILL_NO_CANDIDATE
    else:
        c = request.candidate
        current_price = c.current_price if c.current_price is not None else (snapshot.bid if context_ready else None)
        tm_request = TradeManagementRequest(
            symbol=request.symbol, direction=c.direction, entry_price=c.entry_price,
            stop_loss=c.stop_loss, take_profit=c.take_profit,
            risk_percent=c.risk_percent, risk_amount=c.risk_amount,
            equity=c.equity, symbol_meta=c.symbol_meta,
            current_price=current_price, management_policy=c.management_policy,
        )
        trade_management = evaluate_trade_management(tm_request)
        skill_statuses[SKILL_TRADE_MANAGEMENT] = (
            SKILL_READY if trade_management.overall_status == "READY" else SKILL_BLOCKED
        )

    considered = {k: v for k, v in skill_statuses.items() if v not in (SKILL_NOT_REQUESTED, SKILL_NO_CANDIDATE)}
    overall_status = _aggregate_overall(considered.values())

    return FiveSkillAnalysisResult(
        symbol=request.symbol, timeframe=request.timeframe, timestamp_utc=timestamp_utc,
        market_context_status=market_context_status,
        structure=structure, supply_demand=supply_demand, liquidity=liquidity,
        entry_confirmation=entry_confirmation, trade_management=trade_management,
        skill_statuses=skill_statuses, overall_status=overall_status,
        limitations=tuple(limitations), errors=tuple(errors),
    )


def _aggregate_overall(statuses) -> str:
    statuses = list(statuses)
    if not statuses:
        return OVERALL_READY
    if all(s == SKILL_READY for s in statuses):
        return OVERALL_READY
    if all(s in (SKILL_UNAVAILABLE, SKILL_BLOCKED) for s in statuses):
        return OVERALL_BLOCKED
    return OVERALL_PARTIAL
