"""Canonical evidence envelope for candidate validation outputs (mission section
23). Every OOS/walk-forward/parity output this package produces should be bound
through here rather than passed around as a bare dataclass with no identity --
same intent as `proposal_envelope.models.CanonicalProposal` for proposals, applied
here to VALIDATION evidence instead. This is additive: it does not replace or
duplicate `validation_framework`'s lifecycle/governance model (`models.py`,
`StrategyValidationRecord`) -- that remains the sole promotion-eligibility
authority. This envelope only carries evidence identity/provenance for candidate
artifacts before they are handed to that framework.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from post_asian_pilot.fingerprint import fingerprint

from .models import NOT_AVAILABLE

EVIDENCE_TYPE_OOS = "OOS"
EVIDENCE_TYPE_WALK_FORWARD = "WALK_FORWARD"
EVIDENCE_TYPE_SIGNAL_PARITY = "SIGNAL_PARITY"
EVIDENCE_TYPE_TRADE_PARITY = "TRADE_PARITY"
EVIDENCE_TYPE_ECONOMIC_PARITY = "ECONOMIC_PARITY"


@dataclass(frozen=True)
class CandidateEvidenceEnvelope:
    strategy_id: str
    strategy_version: str
    candidate_id: str
    config_fingerprint: str
    dataset_fingerprint: str
    evidence_type: str
    generated_at: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    git_commit: str = NOT_AVAILABLE
    envelope_fingerprint: str = ""

    def with_fingerprint(self) -> "CandidateEvidenceEnvelope":
        computed = fingerprint({
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "candidate_id": self.candidate_id,
            "config_fingerprint": self.config_fingerprint,
            "dataset_fingerprint": self.dataset_fingerprint,
            "evidence_type": self.evidence_type,
            "payload": self.payload,
        })
        return CandidateEvidenceEnvelope(
            strategy_id=self.strategy_id, strategy_version=self.strategy_version,
            candidate_id=self.candidate_id, config_fingerprint=self.config_fingerprint,
            dataset_fingerprint=self.dataset_fingerprint, evidence_type=self.evidence_type,
            generated_at=self.generated_at, payload=self.payload, git_commit=self.git_commit,
            envelope_fingerprint=computed,
        )


def build_envelope(
    *, strategy_id: str, strategy_version: str, candidate_id: str, config_fingerprint: str,
    dataset_fingerprint: str, evidence_type: str, generated_at: str,
    payload: Mapping[str, Any], git_commit: str = NOT_AVAILABLE,
) -> CandidateEvidenceEnvelope:
    envelope = CandidateEvidenceEnvelope(
        strategy_id=strategy_id, strategy_version=strategy_version, candidate_id=candidate_id,
        config_fingerprint=config_fingerprint, dataset_fingerprint=dataset_fingerprint,
        evidence_type=evidence_type, generated_at=generated_at, payload=payload, git_commit=git_commit,
    )
    return envelope.with_fingerprint()
