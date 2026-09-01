"""SMC_TRADE_PROPOSAL_V1 -- deterministic, evidence-gated trade proposals over
SMC_CONDITIONAL_ENTRY_V2's composer output. See gate.py's module docstring for the
DETECTION != PROPOSAL != EXECUTION boundary this module preserves.
"""
from .explain import explain
from .gate import generate_proposals
from .identity import proposal_id_for, reference_key_for, setup_id, snapshot_id
from .lifecycle import ProposalLifecycleUpdate, update_proposal_lifecycle
from .occurrence_identity import candidate_occurrence_id, eligibility_interval_id
from .models import (
    LIFECYCLE_CREATED,
    LIFECYCLE_EXPIRED,
    LIFECYCLE_INVALIDATED,
    LIFECYCLE_STILL_VALID,
    LIFECYCLE_UPDATED,
    SMC_TRADE_PROPOSAL_V1,
    STATUS_ENTRY_CANDIDATE_INVALIDATED,
    STATUS_ENTRY_CANDIDATE_READY,
    SMCTradeProposal,
)

__all__ = [
    "generate_proposals", "explain", "update_proposal_lifecycle", "ProposalLifecycleUpdate",
    "setup_id", "proposal_id_for", "snapshot_id", "reference_key_for",
    "eligibility_interval_id", "candidate_occurrence_id",
    "SMCTradeProposal", "SMC_TRADE_PROPOSAL_V1",
    "STATUS_ENTRY_CANDIDATE_READY", "STATUS_ENTRY_CANDIDATE_INVALIDATED",
    "LIFECYCLE_CREATED", "LIFECYCLE_STILL_VALID", "LIFECYCLE_UPDATED", "LIFECYCLE_INVALIDATED", "LIFECYCLE_EXPIRED",
]
