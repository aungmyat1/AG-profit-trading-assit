"""Owner-readable proposal tickets and no-proposal notices (DATA ONLY).

AG_FX_OPPORTUNITY_PROPOSAL_SLICE_V1 (2026-09-28): renders a CanonicalProposal
as a plain-text ticket a human owner can read, and renders an explicit
no-proposal notice when the audited ProposalEligibility authority did not
produce an ELIGIBLE decision.

This module renders TEXT. It interprets nothing operationally: the governance
fields (execution_authority, proposal_only, execution_eligible,
broker_mutation_blocked) are printed as data, exactly as they exist on the
envelope, and never used as conditions, permissions, or inputs to any
decision. There is no execution consumer in this repository -- a rendered
ticket confers no authority and triggers nothing.

Deliberately dependency-free (no imports beyond the standard library): the
renderer accepts the proposal/eligibility objects duck-typed, so it can never
become an import-cycle hazard or drag a capability surface into the proposal
package.
"""
from __future__ import annotations

from typing import Any

_TICKET_BANNER = (
    "=========================================================================\n"
    " AG TRADE PROPOSAL TICKET (DATA ONLY -- NOT AN ORDER, NOT AUTHORIZATION)\n"
    "=========================================================================\n"
)


def render_owner_ticket(proposal: Any) -> str:
    """Render one CanonicalProposal as an owner-readable text ticket.

    `proposal` is duck-typed: any object carrying the CanonicalProposal field
    names renders. Values are printed verbatim -- never recomputed, never
    reformatted into authority language.
    """
    lines: list[str] = [_TICKET_BANNER]
    lines.append(f"Proposal Envelope ID : {proposal.proposal_envelope_id}")
    lines.append(f"Strategy             : {proposal.strategy_id}")
    lines.append(f"Market / Symbol      : {proposal.market} / {proposal.symbol}")
    if getattr(proposal, "venue", None):
        lines.append(f"Venue                : {proposal.venue}")
    lines.append(f"Proposal State       : {proposal.proposal_state}")
    lines.append(f"Watcher State        : {proposal.watcher_state}")
    lines.append("")
    lines.append("--- Trade facts (as evaluated by the strategy) ---------------------")
    lines.append(f"Direction            : {proposal.direction}")
    lines.append(f"Entry                : {proposal.entry}")
    lines.append(f"Stop / Invalidation  : {proposal.stop}")
    targets = getattr(proposal, "targets", None) or ()
    targets_text = ", ".join(str(t) for t in targets) if targets else "(none recorded)"
    lines.append(f"Targets              : {targets_text}")
    if getattr(proposal, "risk_distance", None) is not None:
        lines.append(f"Risk Distance        : {proposal.risk_distance}")
    lines.append("")
    lines.append("--- Governance (recorded DATA -- not permissions) -------------------")
    lines.append(f"execution_authority  : {proposal.execution_authority}")
    lines.append(f"proposal_only        : {proposal.proposal_only}")
    lines.append(f"execution_eligible   : {proposal.execution_eligible}")
    lines.append(f"broker_mutation_blocked : {proposal.broker_mutation_blocked}")
    lines.append("")
    if getattr(proposal, "reason_codes", None):
        lines.append(f"Reason codes         : {tuple(proposal.reason_codes)}")
    lines.append(f"Source record        : {proposal.source_module}:{proposal.source_record_id}")
    lines.append("")
    lines.append(
        "This document confers no execution authority. No execution consumer\n"
        "exists in this repository; nothing reads this ticket as permission.\n"
        "Any action taken on it is the owner's own manual decision.\n"
    )
    return "\n".join(lines)


def render_no_proposal_notice(
    candidate: Any,
    eligibility: Any,
) -> str:
    """Render the explicit no-proposal outcome for one evaluated candidate.

    `eligibility` is duck-typed (ProposalEligibilityDecision field names).
    The notice always states the deterministic reason codes -- a silent
    no-proposal is not representable.
    """
    lines: list[str] = []
    lines.append("=========================================================================")
    lines.append(" NO PROPOSAL (explicit outcome of the audited eligibility authority)")
    lines.append("=========================================================================")
    lines.append(f"Candidate ID         : {candidate.candidate_id}")
    lines.append(f"Strategy             : {candidate.strategy_id}")
    lines.append(f"Market / Symbol      : {candidate.market} / {candidate.symbol}")
    lines.append(f"Funnel stage/outcome : {candidate.stage} / {candidate.outcome}")
    lines.append(f"Eligibility status   : {eligibility.status}")
    lines.append(f"Reason codes         : {tuple(eligibility.reason_codes)}")
    lines.append("")
    lines.append("No CanonicalProposal was formed and nothing was persisted to the")
    lines.append("proposal ledger for this candidate. This notice is data, not a")
    lines.append("deferred permission.\n")
    return "\n".join(lines)
