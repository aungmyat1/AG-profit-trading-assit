"""ENTRY_CONFIRMATION_V1 engine -- the single public entry point for this capability.

MT5 -> market-data / market-structure / liquidity (each already normalized) ->
EntryConfirmationRequest (caller-assembled) -> evaluate_entry_confirmation() ->
EntryConfirmationResult.

This module never fetches market data, never re-detects structure/liquidity events,
and never calls execution/order_check/order_send -- see contract.py and
ENTRY_CONFIRMATION_V1_SPEC.md's "Architecture boundary" section.

Aggregation contract (`overall_state`, documented here because it is the one place
this package makes a judgment call beyond pure pass-through):

    - No requested confirmations                              -> INDETERMINATE
    - Any requested confirmation resolves to UNSIGNED_RULE,
      UNAVAILABLE, INSUFFICIENT_DATA, or ERROR                 -> INDETERMINATE
      (evidence is incomplete; aggregating PASS/FAIL over it would overstate confidence)
    - Otherwise, among requested confirmations (all PASS/FAIL):
        all PASS                                                -> CONFIRMED
        all FAIL                                                -> NOT_CONFIRMED
        mixed PASS/FAIL                                         -> PARTIAL

`overall_state` is never a trade decision -- see the package docstring in __init__.py.
"""
from __future__ import annotations

from .displacement import evaluate_displacement
from .liquidity_alignment import evaluate_liquidity_alignment
from .models import (
    ALL_CONFIRMATIONS,
    DISPLACEMENT,
    LIQUIDITY_RECLAIM,
    REJECTION,
    STRUCTURE_SHIFT,
    ConfirmationState,
    DisplacementEvidence,
    EntryConfirmationRequest,
    EntryConfirmationResult,
    LiquidityAlignment,
    OverallState,
    RejectionEvidence,
    StructureAlignment,
)
from .rejection import evaluate_rejection
from .structure_alignment import evaluate_structure_alignment

_INCOMPLETE_STATES = {
    ConfirmationState.UNSIGNED_RULE,
    ConfirmationState.UNAVAILABLE,
    ConfirmationState.INSUFFICIENT_DATA,
    ConfirmationState.ERROR,
}


def evaluate_entry_confirmation(request: EntryConfirmationRequest) -> EntryConfirmationResult:
    unknown = set(request.requested_confirmations) - set(ALL_CONFIRMATIONS)
    if unknown:
        raise ValueError(f"Unknown requested_confirmations: {sorted(unknown)}")

    requested = set(request.requested_confirmations)

    displacement = (
        evaluate_displacement(request.candidate_candle)
        if DISPLACEMENT in requested
        else DisplacementEvidence(status=ConfirmationState.NOT_REQUESTED)
    )
    structure_shift = (
        evaluate_structure_alignment(
            request.structure_result, request.candidate_direction, request.reference_time
        )
        if STRUCTURE_SHIFT in requested
        else StructureAlignment(status=ConfirmationState.NOT_REQUESTED,
                                 candidate_direction=request.candidate_direction.value)
    )
    liquidity_reclaim = (
        evaluate_liquidity_alignment(request.liquidity_result, request.candidate_direction)
        if LIQUIDITY_RECLAIM in requested
        else LiquidityAlignment(status=ConfirmationState.NOT_REQUESTED,
                                 candidate_direction=request.candidate_direction.value)
    )
    rejection = (
        evaluate_rejection(request.candidate_candle)
        if REJECTION in requested
        else RejectionEvidence(status=ConfirmationState.NOT_REQUESTED)
    )

    by_key = {
        DISPLACEMENT: displacement.status,
        STRUCTURE_SHIFT: structure_shift.status,
        LIQUIDITY_RECLAIM: liquidity_reclaim.status,
        REJECTION: rejection.status,
    }
    requested_states = [by_key[k] for k in request.requested_confirmations]

    missing_requirements = tuple(
        k for k in request.requested_confirmations
        if by_key[k] in (ConfirmationState.UNAVAILABLE, ConfirmationState.INSUFFICIENT_DATA)
    )

    overall_state = _aggregate(requested_states)

    rule_versions = tuple(sorted({
        rv for rv in (displacement.rule_version, rejection.rule_version) if rv
    }))

    return EntryConfirmationResult(
        symbol=request.symbol,
        timeframe=request.timeframe,
        candidate_direction=request.candidate_direction.value,
        status="EVALUATED",
        displacement=displacement,
        structure_shift=structure_shift,
        liquidity_reclaim=liquidity_reclaim,
        rejection=rejection,
        overall_state=overall_state,
        requested_confirmations=tuple(request.requested_confirmations),
        missing_requirements=missing_requirements,
        rule_versions=rule_versions,
    )


def _aggregate(requested_states) -> OverallState:
    if not requested_states:
        return OverallState.INDETERMINATE
    if any(s in _INCOMPLETE_STATES for s in requested_states):
        return OverallState.INDETERMINATE
    if all(s == ConfirmationState.PASS for s in requested_states):
        return OverallState.CONFIRMED
    if all(s == ConfirmationState.FAIL for s in requested_states):
        return OverallState.NOT_CONFIRMED
    return OverallState.PARTIAL
