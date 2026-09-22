"""PANEL_R5C: fail-closed reconciliation of a durable execution decision
(execution.durable_idempotency.DurableExecutionRecord, R5B-R1, frozen) against
broker-observation evidence, without ever submitting an order.

R5C answers exactly one question: "given a durable local decision and available
broker observation evidence, what can the system safely conclude about that decision
without submitting another order?" It is OBSERVE -> MATCH -> CLASSIFY -> RECONCILE,
never OBSERVE -> NOT_FOUND -> RESUBMIT -- absence of broker evidence is never treated
as proof that a submission never occurred (see reconcile_decision's own handling of
STATE_NOT_FOUND: it never mutates the durable record).

Reuses, rather than reimplements, two already-established repository patterns:
  - execution.crypto_reconciliation.reconcile()'s own shape: a pure function over
    caller-supplied evidence, returning a typed, fail-closed outcome (never a bare
    Optional collapsing "found" and "lookup failed" into the same falsy shape). This
    module's STATE_MATCHED/STATE_NOT_FOUND/STATE_AMBIGUOUS mirror that module's
    STATE_CONFIRMED_OPEN/STATE_CONFIRMED_ABSENT/STATE_AMBIGUOUS one-for-one; two extra
    outcomes (STATE_BROKER_UNAVAILABLE, STATE_CONFLICT) are split out because R5C's
    mission explicitly requires "conflicting broker ID" and "broker query failed" to be
    distinguishable from a generic ambiguous-evidence case.
  - execution.lifecycle.reconcile_open_positions()'s own idiom: broker-position/deal
    lookups are INJECTED callables (positions_lookup/deals_lookup), never imported
    directly from mt5.account/mt5.deals here -- this keeps this module import-graph-free
    of anything MT5-specific, let alone anything with write/order_send capability, and
    keeps it unit-testable without a live MT5 terminal, exactly like that module already
    is. Production wiring (passing the real mt5.account.positions/mt5.deals.
    deals_for_symbol as those callables) is documented, not implemented, here -- this
    package adds no HTTP/scheduler wiring (out of scope, see the mission brief).
  - the exact same broker-comment identity tag execution.executor._comment_tag() /
    execution.lifecycle._COMMENT_TAG_PREFIX already write/read ("AGT:<command_id>",
    truncated to MT5's 31-character comment limit) -- reproduced byte-for-byte in
    comment_tag_for() below (not imported: both of those modules carry write-capable
    import graphs -- execution.executor imports order_send-adjacent code,
    execution.lifecycle is imported by callers that also drive close_position -- this
    module must never transitively import either).

R5C authorizes NOTHING beyond reading broker state and, only for a deterministic,
non-conflicting MATCH, advancing a durable record along an edge
execution.durable_idempotency.ALLOWED_TRANSITIONS (R5B-R1, frozen) ALREADY permits:
SUBMISSION_PENDING|SUBMISSION_UNKNOWN -> BROKER_ACCEPTED, or BROKER_ACCEPTED ->
RECONCILED. No new state, no new edge, and no lifecycle-graph modification was
required or made. It never calls order_send, submit, place_order, execute_order, or
any MT5 write function -- see tests/test_execution_reconciliation_no_submit.py's
static sweep and mock-based proof.

Identity-matching caveat (inherited, not introduced, by this module -- documented per
the mission's own "never use weak heuristics" instruction): the AGT: comment tag is
truncated to 31 characters by MT5's own comment field limit. For a long decision_id
(e.g. a UUID), `f"AGT:OWNER_DECISION:{decision_id}"[:31]` may truncate the decision_id
itself, which COULD in principle collide with a different decision_id sharing the same
truncated prefix. This module cannot retroactively fix that pre-existing convention
(changing it would touch execution.executor/execution.lifecycle, out of this bounded
package's scope), but it never compounds the risk: matching requires an EXACT tag
equality (never executor.py's looser "tag in comment" substring check), and if more
than one DISTINCT broker record (by ticket) matches the same tag, the outcome is
STATE_AMBIGUOUS, never an arbitrary pick of one.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence

from execution.durable_idempotency import (
    STATE_BROKER_ACCEPTED,
    STATE_RECONCILED,
    STATE_SUBMISSION_PENDING,
    STATE_SUBMISSION_UNKNOWN,
    DurableExecutionRecord,
    DurableExecutionStore,
)

# --------------------------------------------------------------------------- outcomes
# Mirrors execution.crypto_reconciliation's STATE_CONFIRMED_OPEN/STATE_CONFIRMED_ABSENT/
# STATE_AMBIGUOUS one-for-one (STATE_MATCHED == CONFIRMED_OPEN, STATE_NOT_FOUND ==
# CONFIRMED_ABSENT), plus two outcomes that module's crypto-only shape does not need to
# distinguish: STATE_BROKER_UNAVAILABLE (a lookup itself failed -- never collapsed into
# "not found") and STATE_CONFLICT (a persisted broker_order_id disagrees with observed
# evidence -- never silently overwritten).
STATE_MATCHED = "MATCHED"
STATE_NOT_FOUND = "NOT_FOUND"
STATE_AMBIGUOUS = "AMBIGUOUS"
STATE_BROKER_UNAVAILABLE = "BROKER_UNAVAILABLE"
STATE_EVIDENCE_INSUFFICIENT = "EVIDENCE_INSUFFICIENT"
STATE_CONFLICT = "CONFLICT"

ALL_OUTCOMES = frozenset({
    STATE_MATCHED, STATE_NOT_FOUND, STATE_AMBIGUOUS, STATE_BROKER_UNAVAILABLE,
    STATE_EVIDENCE_INSUFFICIENT, STATE_CONFLICT,
})

REASON_NO_DURABLE_RECORD = "NO_DURABLE_RECORD"
REASON_NO_COMMAND_ID = "NO_COMMAND_ID"
REASON_NOT_APPLICABLE_FROM_STATE = "NOT_APPLICABLE_FROM_STATE"
REASON_POSITION_LOOKUP_FAILED = "POSITION_LOOKUP_FAILED"
REASON_DEAL_LOOKUP_FAILED = "DEAL_LOOKUP_FAILED"
REASON_MULTIPLE_DISTINCT_BROKER_RECORDS = "MULTIPLE_DISTINCT_BROKER_RECORDS"
REASON_BROKER_ORDER_ID_MISMATCH = "BROKER_ORDER_ID_MISMATCH"

# Only these current states have any broker-side effect that could exist yet to
# reconcile against. PREPARED/AUTHORIZED (nothing was ever submitted) and REJECTED
# (terminal, never resurrected -- R5B-R1) are deliberately OUT of scope: this is a
# documented scope boundary, not an oversight (see module docstring / status doc).
RECONCILIATION_APPLICABLE_STATES = frozenset({
    STATE_SUBMISSION_PENDING, STATE_SUBMISSION_UNKNOWN, STATE_BROKER_ACCEPTED, STATE_RECONCILED,
})

_COMMENT_TAG_PREFIX = "AGT:"
_COMMENT_TAG_MAX_LENGTH = 31


def comment_tag_for(command_id: str) -> str:
    """Byte-for-byte identical to execution.executor._comment_tag(command_id) /
    execution.lifecycle._COMMENT_TAG_PREFIX's own convention -- reproduced here (not
    imported) so this module's import graph stays free of any write-capable module. See
    the module docstring's "Identity-matching caveat" for the truncation this inherits."""
    return f"{_COMMENT_TAG_PREFIX}{command_id}"[:_COMMENT_TAG_MAX_LENGTH]


@dataclass(frozen=True)
class ReconciliationResult:
    """Always returned, never an exception for an expected/blocked outcome -- same
    convention as owner_decision.models.ExecutionDecision / authorization.store.
    ClaimResult elsewhere in this repository. `record` is the durable record AFTER this
    call: identical to the pre-call record whenever no transition occurred (every
    outcome except a definitive STATE_MATCHED advance)."""

    decision_id: str
    outcome: str
    reason_code: Optional[str] = None
    matched_broker_order_id: Optional[str] = None
    record: Optional[DurableExecutionRecord] = None


def reconcile_decision(
    store: DurableExecutionStore,
    decision_id: str,
    *,
    symbol: str,
    positions_lookup: Callable[..., Sequence[Any]],
    deals_lookup: Callable[..., Sequence[Any]],
) -> ReconciliationResult:
    """OBSERVE (positions_lookup/deals_lookup, injected -- never imported) -> MATCH
    (exact AGT: tag equality, never a substring check) -> CLASSIFY (one of the typed
    outcomes above) -> RECONCILE (advance the durable record ONLY along an edge
    execution.durable_idempotency.ALLOWED_TRANSITIONS already permits, and ONLY for a
    deterministic, non-conflicting match).

    Never calls, imports, or can reach order_send/submit/place_order/execute_order or
    any MT5 write function -- this function's own signature has no execution_handler/
    order-submission parameter to call even by mistake.

    Idempotent: calling this repeatedly with unchanged evidence converges on, and stays
    at, the same durable state (BROKER_ACCEPTED, then RECONCILED, then further calls
    reaffirm RECONCILED via R5B-R1's own same-state idempotent no-op -- never a second,
    divergent transition or identity mutation)."""
    record = store.get(decision_id)
    if record is None:
        return ReconciliationResult(decision_id, STATE_EVIDENCE_INSUFFICIENT, reason_code=REASON_NO_DURABLE_RECORD)

    if not record.command_id:
        return ReconciliationResult(
            decision_id, STATE_EVIDENCE_INSUFFICIENT, reason_code=REASON_NO_COMMAND_ID, record=record,
        )

    if record.state not in RECONCILIATION_APPLICABLE_STATES:
        return ReconciliationResult(
            decision_id, STATE_EVIDENCE_INSUFFICIENT,
            reason_code=f"{REASON_NOT_APPLICABLE_FROM_STATE}:{record.state}", record=record,
        )

    expected_tag = comment_tag_for(record.command_id)

    try:
        positions = list(positions_lookup(symbol=symbol))
    except Exception as exc:  # noqa: BLE001 -- the failure itself becomes a typed, fail-closed outcome
        return ReconciliationResult(
            decision_id, STATE_BROKER_UNAVAILABLE,
            reason_code=f"{REASON_POSITION_LOOKUP_FAILED}:{exc}", record=record,
        )
    try:
        deals = list(deals_lookup(symbol=symbol))
    except Exception as exc:  # noqa: BLE001
        return ReconciliationResult(
            decision_id, STATE_BROKER_UNAVAILABLE,
            reason_code=f"{REASON_DEAL_LOOKUP_FAILED}:{exc}", record=record,
        )

    position_matches = [p for p in positions if getattr(p, "comment", None) == expected_tag]
    # entry == 0 -> DEAL_ENTRY_IN (an opening deal), the SAME convention
    # execution.executor._reconcile_via_broker already uses to distinguish an opening
    # deal from a later close/partial of some other position.
    deal_matches = [
        d for d in deals
        if getattr(d, "comment", None) == expected_tag and getattr(d, "entry", None) == 0
    ]
    all_matches = position_matches + deal_matches
    matched_tickets = {str(getattr(m, "ticket", None)) for m in all_matches}

    if len(matched_tickets) > 1:
        return ReconciliationResult(
            decision_id, STATE_AMBIGUOUS, reason_code=REASON_MULTIPLE_DISTINCT_BROKER_RECORDS, record=record,
        )

    if not matched_tickets:
        # STATE_NOT_FOUND: absence of broker evidence is NEVER proof that submission
        # never occurred (mission P3) -- the durable record is deliberately left
        # completely unmutated. No downgrade to REJECTED, no advance, no rewind.
        return ReconciliationResult(decision_id, STATE_NOT_FOUND, record=record)

    observed_ticket = matched_tickets.pop()

    if record.broker_order_id is not None and record.broker_order_id != observed_ticket:
        # STATE_CONFLICT: never silently overwritten (P8). The durable record is left
        # completely unmutated -- this is a fail-closed report, not a correction.
        return ReconciliationResult(
            decision_id, STATE_CONFLICT, reason_code=REASON_BROKER_ORDER_ID_MISMATCH,
            matched_broker_order_id=observed_ticket, record=record,
        )

    # Deterministic, non-conflicting match. Advance ONLY along an edge R5B-R1's own
    # frozen ALLOWED_TRANSITIONS already permits -- never a new state, never a new edge.
    if record.state == STATE_BROKER_ACCEPTED:
        updated = store.transition(decision_id, state=STATE_RECONCILED)
    elif record.state == STATE_RECONCILED:
        # Already finalized; reaffirming is R5B-R1's own documented same-state
        # idempotent no-op, not a second, divergent transition.
        updated = store.transition(decision_id, state=STATE_RECONCILED)
    else:  # SUBMISSION_PENDING or SUBMISSION_UNKNOWN
        updated = store.transition(decision_id, state=STATE_BROKER_ACCEPTED, broker_order_id=observed_ticket)

    return ReconciliationResult(
        decision_id, STATE_MATCHED, matched_broker_order_id=observed_ticket, record=updated,
    )
