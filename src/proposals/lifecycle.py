"""update_proposal_lifecycle() -- proposal identity/lifecycle tracking (spec sections
13-15, 45-46). `generate_proposals()` (gate.py) stays pure/stateless -- this module adds
persistence (reusing `runtime_state.store.JsonKeyValueStore`, the same primitive
`surveillance` already uses) so repeated polling of the SAME underlying setup does not
produce a fresh "CREATED" event every time, and so a setup that dies gets one precise
"INVALIDATED" transition instead of silently vanishing.

Lifecycle values (spec section 13): CREATED / STILL_VALID / UPDATED / INVALIDATED /
EXPIRED. EXPIRED is supported structurally (if a composed combination ever reports
`state == "EXPIRED"`, this module reports the SAME transition) but this module invents
no time-based expiry rule of its own -- none exists anywhere in entry_confirmation
today (`EntryModelState.EXPIRED` is a frozen enum value no evaluator currently assigns);
see docs/status/SMC_ASSISTANT_READY_TO_USE_V1_STATUS.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple

from entry_confirmation.entry_models_v1 import EntryModelState, SMCConditionalEntryAnalysis

from .gate import generate_proposals
from .identity import proposal_id_for, reference_key_for, setup_id as _setup_id
from .models import (
    LIFECYCLE_CREATED,
    LIFECYCLE_EXPIRED,
    LIFECYCLE_INVALIDATED,
    LIFECYCLE_STILL_VALID,
    LIFECYCLE_UPDATED,
    STATUS_ENTRY_CANDIDATE_INVALIDATED,
    SMCTradeProposal,
)

_TERMINAL = (LIFECYCLE_INVALIDATED, LIFECYCLE_EXPIRED)

# Fields that define "meaningful entry metadata" (spec section 13) -- deliberately
# excludes evidence/reason text and snapshot-scoped identifiers, so cosmetic/wording
# changes never trigger a spurious UPDATED.
_SIGNATURE_FIELDS = ("entry_type", "entry_low", "entry_high", "entry_reference",
                     "invalidation_price", "invalidation_source_type")


@dataclass(frozen=True)
class ProposalLifecycleUpdate:
    setup_id: str
    lifecycle: str
    proposal: SMCTradeProposal
    changed_fields: Tuple[str, ...] = field(default_factory=tuple)


def _signature(proposal: SMCTradeProposal) -> Dict[str, object]:
    return {f: getattr(proposal, f) for f in _SIGNATURE_FIELDS}


def _changed_fields(old_sig: Dict[str, object], new_sig: Dict[str, object]) -> Tuple[str, ...]:
    return tuple(f for f in _SIGNATURE_FIELDS if old_sig.get(f) != new_sig.get(f))


def update_proposal_lifecycle(analysis: SMCConditionalEntryAnalysis, store) -> Tuple[ProposalLifecycleUpdate, ...]:
    """`store` is a runtime_state.store.JsonKeyValueStore (or any get/put-compatible
    object), keyed by setup_id -- injected, same convention as
    surveillance.update_surveillance."""
    updates = []
    seen_setup_ids = set()

    current_ready = generate_proposals(analysis)
    for proposal in current_ready:
        seen_setup_ids.add(proposal.setup_id)
        prior = store.get(proposal.setup_id)
        new_sig = _signature(proposal)

        if prior is None or prior.get("lifecycle") in _TERMINAL:
            lifecycle, changed = LIFECYCLE_CREATED, ()
        elif prior.get("signature") != new_sig:
            lifecycle, changed = LIFECYCLE_UPDATED, _changed_fields(prior.get("signature", {}), new_sig)
        else:
            lifecycle, changed = LIFECYCLE_STILL_VALID, ()

        final_proposal = SMCTradeProposal(**{**proposal.__dict__, "lifecycle": lifecycle, "changed_fields": changed})
        store.put(proposal.setup_id, {
            "setup_id": proposal.setup_id, "proposal_id": proposal.proposal_id, "lifecycle": lifecycle,
            "signature": new_sig, "snapshot_id": proposal.snapshot_id,
        })
        updates.append(ProposalLifecycleUpdate(setup_id=proposal.setup_id, lifecycle=lifecycle,
                                                 proposal=final_proposal, changed_fields=changed))

    # Previously-tracked, non-terminal setups that dropped out of this poll's READY set:
    # only report INVALIDATED/EXPIRED when a composed combination for that exact setup
    # explicitly says so this poll -- never inferred from mere absence (spec sections
    # 31/64: fail closed, no fabricated transition).
    for combo in analysis.combinations:
        if combo.state not in (EntryModelState.INVALIDATED.value, EntryModelState.EXPIRED.value):
            continue
        e_condition = analysis.e_conditions.get(combo.entry_condition)
        reference_key = reference_key_for(
            getattr(e_condition, "reference_type", None), getattr(e_condition, "reference_low", None),
            getattr(e_condition, "reference_high", None), getattr(e_condition, "reference_level", None),
        )
        setup = _setup_id(analysis.symbol, combo.combination, combo.direction, reference_key)
        if setup in seen_setup_ids:
            continue
        prior = store.get(setup)
        if prior is None or prior.get("lifecycle") in _TERMINAL:
            continue  # never tracked as an active proposal, or already terminal -- nothing new to report

        lifecycle = LIFECYCLE_INVALIDATED if combo.state == EntryModelState.INVALIDATED.value else LIFECYCLE_EXPIRED
        snapshot_time = analysis.snapshot_time.isoformat() if analysis.snapshot_time is not None else None
        dead_proposal = SMCTradeProposal(
            proposal_id=proposal_id_for(setup), setup_id=setup,
            snapshot_id=prior.get("snapshot_id", ""), snapshot_time=snapshot_time, symbol=analysis.symbol,
            combination=combo.combination, entry_condition=combo.entry_condition, maneuver=combo.maneuver,
            direction=combo.direction,
            reference_timeframe=combo.reference_timeframe, check_timeframe=combo.check_timeframe,
            confirmation_timeframe=combo.confirmation_timeframe, execution_timeframe=combo.execution_timeframe,
            entry_type=prior.get("signature", {}).get("entry_type"),
            entry_low=prior.get("signature", {}).get("entry_low"),
            entry_high=prior.get("signature", {}).get("entry_high"),
            entry_reference=prior.get("signature", {}).get("entry_reference"),
            invalidation_state=combo.invalidation,
            invalidation_price=combo.invalidation_price, invalidation_source_type=combo.invalidation_source_type,
            invalidation_reason=combo.invalidation_reason, invalidation_trigger=combo.invalidation_trigger,
            evidence=dict(combo.evidence), missing_conditions=combo.missing_conditions,
            status=STATUS_ENTRY_CANDIDATE_INVALIDATED, lifecycle=lifecycle,
        )
        store.put(setup, {
            "setup_id": setup, "proposal_id": dead_proposal.proposal_id, "lifecycle": lifecycle,
            "signature": prior.get("signature", {}), "snapshot_id": dead_proposal.snapshot_id,
        })
        updates.append(ProposalLifecycleUpdate(setup_id=setup, lifecycle=lifecycle, proposal=dead_proposal))

    return tuple(updates)
