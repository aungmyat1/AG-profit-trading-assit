"""Cross-strategy SMC semantic safety checks.

This module validates evidence metadata; it never detects a setup and never promotes
evidence into a trade.  Strategy engines remain the only decision authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from typing import Optional, Tuple


class EvidenceAuthority(IntEnum):
    OBSERVATION = 1
    CONTEXT = 2
    CONFIRMATION = 3
    STRATEGY_DECISION = 4
    EXECUTION = 5


_TIMEFRAME_RANK = {"M1": 1, "M5": 2, "M15": 3, "M30": 4, "H1": 5, "H4": 6, "D1": 7}

REJECT_FUTURE_EVIDENCE = "REJECT_FUTURE_EVIDENCE"
REJECT_AUTHORITY_LEAKAGE = "REJECT_AUTHORITY_LEAKAGE"
REJECT_TIMEFRAME_LEAKAGE = "REJECT_TIMEFRAME_LEAKAGE"
REJECT_RETROSPECTIVE_QUALIFICATION = "REJECT_RETROSPECTIVE_QUALIFICATION"


@dataclass(frozen=True)
class SemanticEvidence:
    concept: str
    authority: EvidenceAuthority
    evidence_time: datetime
    decision_time: datetime
    timeframe: Optional[str] = None
    claims_trade_decision: bool = False
    overrides_timeframe: Optional[str] = None
    creates_past_qualification: bool = False


def validate_semantic_evidence(evidence: SemanticEvidence) -> Tuple[str, ...]:
    """Return deterministic rejection codes for cross-layer SMC authority leaks."""
    violations = []
    if evidence.evidence_time > evidence.decision_time:
        violations.append(REJECT_FUTURE_EVIDENCE)
    if evidence.creates_past_qualification:
        violations.append(REJECT_RETROSPECTIVE_QUALIFICATION)
    if evidence.claims_trade_decision and evidence.authority < EvidenceAuthority.STRATEGY_DECISION:
        violations.append(REJECT_AUTHORITY_LEAKAGE)
    if evidence.overrides_timeframe is not None:
        source_rank = _TIMEFRAME_RANK.get(evidence.timeframe or "")
        target_rank = _TIMEFRAME_RANK.get(evidence.overrides_timeframe)
        if source_rank is None or target_rank is None or source_rank < target_rank:
            violations.append(REJECT_TIMEFRAME_LEAKAGE)
    return tuple(violations)
