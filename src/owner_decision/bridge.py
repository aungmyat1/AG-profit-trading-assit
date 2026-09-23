"""evaluate_owner_decision(): the ONLY function that turns an explicit OwnerDecision
into an ExecutionDecision for a CanonicalProposal-sourced (Post-Asian / Large-SMC)
opportunity. Fail-closed at every step; never calls execution.executor,
execution.mt5_gateway, or assistant.commands.execute_command -- it stops at producing
an AUTHORIZED-but-UNCONFIRMED TradeCommand template (see owner_decision.models.
ExecutionDecision docstring) for a separate, explicitly-user-confirmed call site to
pass into that existing gate.

Reuses, rather than reimplements:
  assistant.canonical_proposal_adapter -- CanonicalProposal -> TradeCandidate/
                                           TradeProposal -> TradeCommand template
                                           (already execution-free, already audited).
  assistant.commands.build_proposal_from_canonical -- persists the TradeProposal into
                                           the SAME store execute_command() reads, so a
                                           later execute_command(proposal_id=...) call
                                           can resolve it.

Fail-closed invariants enforced here (PANEL_R3_OWNER_DECISION_BRIDGE P6/P7/P8/P9):
  - REJECT can never produce an AUTHORIZED ExecutionDecision.
  - A malformed/unknown action fails closed (never defaults to approve).
  - A missing decision_id/proposal_envelope_id fails closed.
  - environment must read exactly "DEMO" -- anything else (including "LIVE" or a typo)
    is rejected. This is an ADDITIONAL check, layered on top of -- never a replacement
    for -- the existing account.allow_live_trading / account.is_demo gates already
    enforced deeper in execution.mt5_gateway.
  - envelope.proposal_state must be PROPOSAL_READY.
  - envelope.demo_authorized must be True and envelope.broker_mutation_blocked must be
    False -- the existing strategy-governance fields on CanonicalProposal
    (AG_MULTI_STRATEGY_PROPOSAL_AND_WATCH_READINESS_V1_2), sourced from
    strategies/registry.yaml via proposal_envelope.strategy_authority. Never bypassed,
    never inferred True from anything else in this module.
  - envelope.plan_expires_at, if present and already in the past at evaluation time,
    fails closed as stale -- the original thesis is never silently refreshed.
  - decision.symbol must match envelope.symbol (identity cross-check).
  - decision_id is idempotent: replaying the same decision_id returns the SAME
    previously-computed ExecutionDecision, never re-derives or re-authorizes.

Nothing in this module can be reached by a scheduler, a watch/alert loop, a GET
request, or the mere act of viewing/selecting a proposal -- it is only ever invoked
with an OwnerDecision the caller constructed from an explicit owner action.
"""
from __future__ import annotations

import dataclasses
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from assistant.canonical_proposal_adapter import (
    CanonicalProposalMalformed,
    CanonicalProposalNotReady,
    trade_command_template,
)
from assistant.commands import build_proposal_from_canonical
from execution.models import ExecutionSource, TradeCommand
from proposal_envelope.models import CanonicalProposal, PROPOSAL_READY
from runtime_state.store import JsonKeyValueStore, StateStoreCorrupted

from .models import (
    ENVIRONMENT_DEMO,
    EXECUTION_DECISION_AUTHORIZED,
    EXECUTION_DECISION_REJECTED,
    OWNER_ACTION_REJECT,
    OWNER_ACTIONS,
    ExecutionDecision,
    OwnerDecision,
)

DEFAULT_OWNER_DECISION_STORE_PATH = "state/owner_decisions/owner_decisions.json"


class OwnerDecisionStoreUnavailable(RuntimeError):
    """P10-equivalent fail-closed signal: the on-disk owner-decision ledger exists but
    could not be read (corrupt/truncated/unreadable). Never interpreted as "no prior
    decisions exist" -- a caller must stop, not silently start from an empty store and
    risk re-authorizing a decision that was already REJECTED, or minting a second
    lineage for a decision_id that already has a durable AUTHORIZED outcome."""


def _serialize_execution_decision(outcome: ExecutionDecision) -> Dict[str, Any]:
    """Plain-dict form for runtime_state.store.JsonKeyValueStore (this repo's
    established atomic JSON persistence convention -- see proposal_envelope.ledger and
    execution.durable_idempotency for the same pattern). ExecutionSource is a str Enum
    so it serializes as its plain string value with no extra handling."""
    trade_command = None
    if outcome.trade_command is not None:
        trade_command = dataclasses.asdict(outcome.trade_command)
    return {
        "decision_id": outcome.decision_id,
        "proposal_envelope_id": outcome.proposal_envelope_id,
        "status": outcome.status,
        "reason_code": outcome.reason_code,
        "reasons": list(outcome.reasons),
        "trade_command": trade_command,
    }


def _deserialize_execution_decision(record: Dict[str, Any]) -> ExecutionDecision:
    trade_command = None
    raw_command = record.get("trade_command")
    if raw_command is not None:
        data = dict(raw_command)
        data["source"] = ExecutionSource(data["source"])
        trade_command = TradeCommand(**data)
    return ExecutionDecision(
        decision_id=record["decision_id"],
        proposal_envelope_id=record["proposal_envelope_id"],
        status=record["status"],
        reason_code=record["reason_code"],
        reasons=tuple(record.get("reasons", ())),
        trade_command=trade_command,
    )

REASON_MALFORMED_DECISION = "MALFORMED_DECISION"
REASON_OWNER_REJECTED = "OWNER_REJECTED"
REASON_NON_DEMO_ENVIRONMENT = "NON_DEMO_ENVIRONMENT_REJECTED"
REASON_PROPOSAL_NOT_READY = "PROPOSAL_NOT_READY"
REASON_DEMO_NOT_AUTHORIZED = "DEMO_NOT_AUTHORIZED"
REASON_BROKER_MUTATION_BLOCKED = "BROKER_MUTATION_BLOCKED"
REASON_SYMBOL_MISMATCH = "SYMBOL_MISMATCH"
REASON_PROPOSAL_STALE = "PROPOSAL_STALE"
REASON_PROPOSAL_MALFORMED = "PROPOSAL_MALFORMED"


def _parse_iso8601(value: Optional[str]) -> Optional[datetime]:
    """Minimal, local ISO8601 parse -- mirrors assistant.canonical_proposal_adapter.
    _iso_to_datetime's own tolerance (naive timestamps treated as UTC) without
    importing that module's private helper across a package boundary."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


class OwnerDecisionStore:
    """Idempotency ledger keyed by decision_id. Lock-protected (a single
    threading.Lock guards the in-memory cache AND the optional durable write below) so
    two near-simultaneous submissions of the identical decision_id can never both "win"
    and produce two independent ExecutionDecisions -- matching
    execution.durable_idempotency.DurableExecutionStore's own same-process concurrency
    guarantee (a per-path lock inside JsonKeyValueStore; this store adds its own
    coarser lock on top so the in-memory dict and the on-disk file are updated as one
    unit from this class's point of view).

    PANEL_R3 shipped this as in-memory-only ("a restart loses it"). That is safe for
    ExecutionDecision.status == REJECTED (nothing to lose) but NOT for AUTHORIZED: an
    ordinary process restart between "owner clicked Confirm" and "a later, separately
    user-confirmed execute_command() call resolves this decision_id" would silently
    lose the PREPARED TradeCommand template and any caller retrying the identical HTTP
    request would re-run evaluate_owner_decision() against whatever the proposal
    envelope looks like NOW -- not what it looked like at the moment of the original
    approval. Passing `path` (the production default is
    DEFAULT_OWNER_DECISION_STORE_PATH, via api.app's singleton) makes this durable
    using runtime_state.store.JsonKeyValueStore -- the same atomic temp-file + os.
    replace convention already used by proposal_envelope.ledger.ProposalLedger and
    execution.durable_idempotency.DurableExecutionStore, so this introduces no new
    persistence mechanism. `path=None` (the default, unchanged for every existing
    caller/test) keeps the original pure in-memory behavior.

    Durability scope, precisely stated (matching DurableExecutionStore's own
    documented boundary): atomic file replacement and restart persistence under an
    ordinary process restart; no fsync (no power-loss guarantee); safe for concurrent
    THREADS within one process (JsonKeyValueStore's per-path lock plus this class's own
    lock); NOT cross-process or cross-machine safety -- nothing in this repository runs
    more than one process against the same owner-decision store today."""

    def __init__(self, path: Optional[str] = None) -> None:
        self._lock = threading.Lock()
        self._decisions: Dict[str, ExecutionDecision] = {}
        self._persist: Optional[JsonKeyValueStore] = (
            JsonKeyValueStore(path) if path else None
        )
        if self._persist is not None:
            self._load_from_disk()

    def _load_from_disk(self) -> None:
        try:
            raw = self._persist.all()
        except StateStoreCorrupted as exc:
            raise OwnerDecisionStoreUnavailable(
                f"OWNER_DECISION_STORE_UNAVAILABLE: {exc}"
            ) from exc
        for decision_id, record in raw.items():
            self._decisions[decision_id] = _deserialize_execution_decision(record)

    def get(self, decision_id: str) -> Optional[ExecutionDecision]:
        with self._lock:
            return self._decisions.get(decision_id)

    def put_if_absent(self, outcome: ExecutionDecision) -> ExecutionDecision:
        """Returns the WINNING record for outcome.decision_id -- either the one just
        inserted, or (if another call already recorded one first) that earlier one,
        unchanged. Never overwrites an existing entry, in memory or on disk."""
        with self._lock:
            existing = self._decisions.get(outcome.decision_id)
            if existing is not None:
                return existing
            self._decisions[outcome.decision_id] = outcome
            if self._persist is not None:
                self._persist.put(outcome.decision_id, _serialize_execution_decision(outcome))
            return outcome


_default_store = OwnerDecisionStore()


def _reject(decision: OwnerDecision, reason_code: str, *reasons: str) -> ExecutionDecision:
    return ExecutionDecision(
        decision_id=decision.decision_id,
        proposal_envelope_id=decision.proposal_envelope_id,
        status=EXECUTION_DECISION_REJECTED,
        reason_code=reason_code,
        reasons=reasons or (reason_code,),
    )


def evaluate_owner_decision(
    decision: OwnerDecision,
    envelope: Optional[CanonicalProposal],
    *,
    store: Optional[OwnerDecisionStore] = None,
    now: Optional[datetime] = None,
) -> ExecutionDecision:
    """Pure with respect to `envelope`/`decision` (never mutates either). Its one side
    effect on the AUTHORIZED path is build_proposal_from_canonical()'s existing,
    already-execution-free proposal-store write -- identical to what a caller of
    assistant.build_proposal_from_canonical would already trigger on its own (see that
    function's own docstring: "never itself execution authorization"). Never calls
    execute_command, execution.executor, or execution.mt5_gateway."""
    store = store or _default_store
    now = now or datetime.now(timezone.utc)

    if decision is None:
        raise ValueError("evaluate_owner_decision requires a decision.")

    # Idempotency FIRST -- a replayed decision_id must return the exact prior outcome,
    # never be re-evaluated, matching execution.executor's own "claimed command_id"
    # posture (P8: repeated submission of the same decision must never create a second,
    # independent authorization).
    if decision.decision_id:
        prior = store.get(decision.decision_id)
        if prior is not None:
            return prior

    if not decision.decision_id or not decision.proposal_envelope_id:
        return _reject(decision, REASON_MALFORMED_DECISION,
                        "decision_id and proposal_envelope_id are required.")

    if decision.action not in OWNER_ACTIONS:
        return store.put_if_absent(_reject(
            decision, REASON_MALFORMED_DECISION, f"unknown action {decision.action!r}.",
        ))

    if decision.action == OWNER_ACTION_REJECT:
        return store.put_if_absent(_reject(decision, REASON_OWNER_REJECTED))

    # From here on, action == APPROVE_DEMO. Every further check fails closed.
    if decision.environment != ENVIRONMENT_DEMO:
        return store.put_if_absent(_reject(
            decision, REASON_NON_DEMO_ENVIRONMENT,
            f"environment {decision.environment!r} is not DEMO.",
        ))

    if envelope is None:
        return store.put_if_absent(_reject(
            decision, REASON_PROPOSAL_NOT_READY,
            "no CanonicalProposal was found for this decision.",
        ))

    if envelope.proposal_envelope_id != decision.proposal_envelope_id:
        return store.put_if_absent(_reject(
            decision, REASON_MALFORMED_DECISION,
            "envelope identity does not match decision.proposal_envelope_id.",
        ))

    if envelope.symbol != decision.symbol:
        return store.put_if_absent(_reject(
            decision, REASON_SYMBOL_MISMATCH,
            f"decision.symbol {decision.symbol!r} != envelope.symbol {envelope.symbol!r}.",
        ))

    if envelope.proposal_state != PROPOSAL_READY:
        return store.put_if_absent(_reject(
            decision, REASON_PROPOSAL_NOT_READY, f"proposal_state={envelope.proposal_state!r}.",
        ))

    if not envelope.demo_authorized:
        return store.put_if_absent(_reject(
            decision, REASON_DEMO_NOT_AUTHORIZED,
            "strategy/version governance has not set demo_authorized=True for this "
            "proposal -- see strategies/registry.yaml.",
        ))

    if envelope.broker_mutation_blocked:
        return store.put_if_absent(_reject(decision, REASON_BROKER_MUTATION_BLOCKED))

    expires_at = _parse_iso8601(envelope.plan_expires_at)
    if expires_at is not None and now > expires_at:
        return store.put_if_absent(_reject(
            decision, REASON_PROPOSAL_STALE, f"plan_expires_at {envelope.plan_expires_at} has passed.",
        ))

    try:
        trade_proposal = build_proposal_from_canonical(envelope)
    except (CanonicalProposalNotReady, CanonicalProposalMalformed) as exc:
        return store.put_if_absent(_reject(decision, REASON_PROPOSAL_MALFORMED, str(exc)))

    command = trade_command_template(
        trade_proposal, command_id=f"OWNER_DECISION:{decision.decision_id}",
    )

    authorized = ExecutionDecision(
        decision_id=decision.decision_id,
        proposal_envelope_id=decision.proposal_envelope_id,
        status=EXECUTION_DECISION_AUTHORIZED,
        reason_code="OWNER_APPROVED_DEMO",
        trade_command=command,
    )
    return store.put_if_absent(authorized)
