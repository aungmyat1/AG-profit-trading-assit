"""Deterministic execution-critical integrity hash over a TradeProposal.

An ExecutionApproval authorizes exactly the proposal shown in the Telegram ticket --
never a regenerated or mutated one. This module computes a canonical SHA-256 over the
frozen set of execution-critical fields (spec section 16/17) so a later mismatch is
detected mechanically rather than trusted. This reuses the same canonicalization
technique already established in this repo (post_asian_pilot.fingerprint /
historical_replay.stage1 -- sort_keys, compact separators, no float/str ambiguity
tricks beyond what json.dumps already gives), not a new invented scheme.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional

from execution.adapter import TradeProposal

# The exact, frozen field list this hash covers -- spec section 16/17. Anything NOT in
# this list (e.g. a future cosmetic/report-only field added to TradeProposal) never
# affects the hash, so adding such a field elsewhere in the codebase can never silently
# invalidate every in-flight approval.
INTEGRITY_FIELDS = (
    "setup_id",
    "strategy_id",
    "profile_id",
    "symbol",
    "direction",
    "entry",
    "stop_loss",
    "tp1",
    "tp2",
    "volume",
    "risk_amount",
    "risk_percent",
)


def _canonical_payload(proposal: TradeProposal) -> Dict[str, Any]:
    return {field_name: getattr(proposal, field_name) for field_name in INTEGRITY_FIELDS}


def compute_proposal_hash(proposal: TradeProposal) -> str:
    canonical = json.dumps(_canonical_payload(proposal), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_proposal_integrity(proposal: TradeProposal, expected_hash: str) -> bool:
    """True only if `proposal`'s execution-critical fields exactly match the hash
    recorded at approval-creation time. Never raises -- a mismatch is an expected,
    reportable outcome (PROPOSAL_INTEGRITY_MISMATCH), not a crash."""
    return compute_proposal_hash(proposal) == expected_hash
