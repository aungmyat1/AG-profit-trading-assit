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


class OwnerDecisionProposalAuthorityConflict(OwnerDecisionStoreUnavailable):
    """R5C fail-closed signal: the persisted ledger already contains two DIFFERENT
    decision_ids for the SAME proposal_envelope_id whose terminal owner outcomes
    disagree (one AUTHORIZED, the other OWNER_REJECTED). This is impossible under
    normal R5C operation (OwnerDecisionStore.commit_terminal_decision only ever lets
    ONE terminal decision_id per proposal_envelope_id become durable) so it can only
    arise from pre-R5C data or direct file tampering. Per P7: never arbitrarily pick a
    winner and continue -- the whole store is unavailable until a human resolves the
    contradiction. Subclasses OwnerDecisionStoreUnavailable so existing callers that
    already catch that family fail closed here too without any code change."""


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
REASON_PROPOSAL_ALREADY_DECIDED = "PROPOSAL_ALREADY_DECIDED"


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
    more than one process against the same owner-decision store today.

    R5C (PANEL_R5C_PROPOSAL_DECISION_UNIQUENESS): adds `_proposal_index`, an in-memory
    Dict[proposal_envelope_id, decision_id] pointing at the ONE authoritative terminal
    owner decision for that proposal (either the AUTHORIZED decision, or the genuine
    OWNER_REJECTED decision -- never a validation-failure rejection such as
    NON_DEMO_ENVIRONMENT_REJECTED/PROPOSAL_NOT_READY/DEMO_NOT_AUTHORIZED/etc, since
    those never represent a completed owner action on the proposal and must not block a
    later, correctly-formed request from getting a real evaluation). No new persisted
    file: `_proposal_index` is 100% reconstructed from `_decisions` on every load (see
    `_load_from_disk`), so this is fully backward-compatible with existing persisted
    ledgers and needs no migration. Establishing a proposal's authority and recording
    its decision_id happen atomically under `self._lock` in `commit_terminal_decision`
    -- the same primitive `put_if_absent` already used for decision_id uniqueness,
    extended rather than duplicated, so proposal-level uniqueness gets the identical
    same-process concurrency guarantee for free."""

    def __init__(self, path: Optional[str] = None) -> None:
        self._lock = threading.Lock()
        self._decisions: Dict[str, ExecutionDecision] = {}
        self._proposal_index: Dict[str, str] = {}
        self._persist: Optional[JsonKeyValueStore] = (
            JsonKeyValueStore(path) if path else None
        )
        if self._persist is not None:
            self._load_from_disk()

    @staticmethod
    def _is_terminal_owner_outcome(outcome: ExecutionDecision) -> bool:
        """True only for a GENUINE completed owner action: an AUTHORIZED approval, or
        an explicit REJECT (reason_code == REASON_OWNER_REJECTED). Every other
        REJECTED reason_code (MALFORMED_DECISION, NON_DEMO_ENVIRONMENT_REJECTED,
        PROPOSAL_NOT_READY, DEMO_NOT_AUTHORIZED, BROKER_MUTATION_BLOCKED,
        SYMBOL_MISMATCH, PROPOSAL_STALE, PROPOSAL_MALFORMED,
        PROPOSAL_ALREADY_DECIDED) is a validation/gating failure on an attempted
        request, never a completed owner decision about the proposal, and must never
        establish or be measured against proposal-level authority."""
        if outcome.status == EXECUTION_DECISION_AUTHORIZED:
            return True
        return outcome.status == EXECUTION_DECISION_REJECTED and outcome.reason_code == REASON_OWNER_REJECTED

    def _load_from_disk(self) -> None:
        try:
            raw = self._persist.all()
        except StateStoreCorrupted as exc:
            raise OwnerDecisionStoreUnavailable(
                f"OWNER_DECISION_STORE_UNAVAILABLE: {exc}"
            ) from exc
        for decision_id, record in raw.items():
            self._decisions[decision_id] = _deserialize_execution_decision(record)

        # Deterministic reconstruction of proposal-level authority (P6/P7). Iteration
        # order here is `raw.items()`'s own order -- JsonKeyValueStore persists with
        # `sort_keys=True`, so this is alphabetical by decision_id, not write order;
        # that is fine because the ONLY tie we ever resolve without failing closed is
        # two terminal decisions that AGREE (both AUTHORIZED, or both OWNER_REJECTED)
        # for the same proposal -- in which case the two records are not contradictory
        # and either one may stand as the recorded authority. Two terminal decisions
        # that DISAGREE (one AUTHORIZED, one OWNER_REJECTED) for the same proposal can
        # only come from pre-R5C data or file tampering (post-R5C,
        # commit_terminal_decision never lets a second one durably form) -- fail closed
        # rather than silently pick a side (P7).
        for decision_id, outcome in self._decisions.items():
            if not self._is_terminal_owner_outcome(outcome):
                continue
            existing_decision_id = self._proposal_index.get(outcome.proposal_envelope_id)
            if existing_decision_id is None:
                self._proposal_index[outcome.proposal_envelope_id] = decision_id
                continue
            existing_outcome = self._decisions[existing_decision_id]
            if existing_outcome.status != outcome.status:
                raise OwnerDecisionProposalAuthorityConflict(
                    "OWNER_DECISION_PROPOSAL_AUTHORITY_CONFLICT: proposal "
                    f"{outcome.proposal_envelope_id!r} has two conflicting terminal "
                    f"owner decisions on disk: {existing_decision_id!r} "
                    f"({existing_outcome.status}) vs {decision_id!r} ({outcome.status})."
                )
            # Same status (agreeing duplicate) -- keep whichever was indexed first;
            # not a contradiction, nothing to fail closed over.

    def get(self, decision_id: str) -> Optional[ExecutionDecision]:
        with self._lock:
            return self._decisions.get(decision_id)

    def proposal_authority(self, proposal_envelope_id: str) -> Optional[ExecutionDecision]:
        """Returns the current authoritative terminal ExecutionDecision for this
        proposal_envelope_id, or None if the proposal has no recorded owner decision
        yet. Read-only convenience for callers/tests; evaluate_owner_decision itself
        relies on the atomic check-and-set inside `commit_terminal_decision`, not on a
        separate read-then-write against this method, to stay race-safe (P5)."""
        with self._lock:
            decision_id = self._proposal_index.get(proposal_envelope_id)
            if decision_id is None:
                return None
            return self._decisions[decision_id]

    def put_if_absent(self, outcome: ExecutionDecision) -> ExecutionDecision:
        """Returns the WINNING record for outcome.decision_id -- either the one just
        inserted, or (if another call already recorded one first) that earlier one,
        unchanged. Never overwrites an existing entry, in memory or on disk. Used for
        every validation-failure rejection (never a terminal owner outcome -- those go
        through `commit_terminal_decision` instead so they also get the proposal-level
        uniqueness check)."""
        with self._lock:
            existing = self._decisions.get(outcome.decision_id)
            if existing is not None:
                return existing
            self._decisions[outcome.decision_id] = outcome
            if self._persist is not None:
                self._persist.put(outcome.decision_id, _serialize_execution_decision(outcome))
            return outcome

    def commit_terminal_decision(self, candidate: ExecutionDecision) -> ExecutionDecision:
        """The ONE atomic gate for a GENUINE completed owner action (AUTHORIZED, or
        REJECTED with reason_code == REASON_OWNER_REJECTED) -- enforces BOTH decision_id
        idempotency (like put_if_absent) AND proposal-level at-most-one-authority
        (R5C), as a single lock-protected check-and-set so two racing decision_ids for
        the SAME proposal can never both durably win (P5).

        Semantics (P3):
          - decision_id already decided -> return that prior record unchanged (exact
            replay, points B).
          - proposal has no authority yet -> `candidate` becomes the proposal's
            authority; durably recorded under its own decision_id (points A).
          - proposal already has authority with the SAME semantic action (both
            AUTHORIZED, or both OWNER_REJECTED) -> `candidate` is discarded; the
            EXISTING authoritative outcome is returned unchanged, and nothing new is
            recorded under `candidate.decision_id` (point D: no duplicate authority).
          - proposal already has authority with the OPPOSITE semantic action -> fail
            closed: a new REJECTED record with reason_code PROPOSAL_ALREADY_DECIDED is
            durably recorded under `candidate.decision_id` (so ITS OWN replay stays
            idempotent) but the proposal's existing authority is never touched (point
            E)."""
        with self._lock:
            existing_by_id = self._decisions.get(candidate.decision_id)
            if existing_by_id is not None:
                return existing_by_id

            existing_decision_id = self._proposal_index.get(candidate.proposal_envelope_id)
            if existing_decision_id is None:
                self._decisions[candidate.decision_id] = candidate
                self._proposal_index[candidate.proposal_envelope_id] = candidate.decision_id
                if self._persist is not None:
                    self._persist.put(
                        candidate.decision_id, _serialize_execution_decision(candidate)
                    )
                return candidate

            existing_outcome = self._decisions[existing_decision_id]
            if existing_outcome.status == candidate.status:
                # Same semantic action already authoritative -- replay it verbatim,
                # never mint a second authority for this proposal.
                return existing_outcome

            # Opposite semantic action -- fail closed. The original authority is never
            # mutated; this new decision_id durably records its own rejection so a
            # replay of THIS SAME decision_id is idempotent too.
            conflict = ExecutionDecision(
                decision_id=candidate.decision_id,
                proposal_envelope_id=candidate.proposal_envelope_id,
                status=EXECUTION_DECISION_REJECTED,
                reason_code=REASON_PROPOSAL_ALREADY_DECIDED,
                reasons=(
                    f"proposal {candidate.proposal_envelope_id!r} already has an "
                    f"authoritative owner decision ({existing_decision_id!r}, "
                    f"status={existing_outcome.status}); conflicting "
                    f"{candidate.status} action rejected.",
                ),
            )
            self._decisions[candidate.decision_id] = conflict
            if self._persist is not None:
                self._persist.put(candidate.decision_id, _serialize_execution_decision(conflict))
            return conflict


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
        # Genuine terminal owner action -- goes through the proposal-level atomic gate
        # (R5C), not the plain decision_id-only put_if_absent.
        return store.commit_terminal_decision(_reject(decision, REASON_OWNER_REJECTED))

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
    # Genuine terminal owner action -- goes through the proposal-level atomic gate
    # (R5C), not the plain decision_id-only put_if_absent.
    return store.commit_terminal_decision(authorized)
