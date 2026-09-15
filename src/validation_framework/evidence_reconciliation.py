"""Fail-closed evidence-lineage reconciliation (Cycle-1 remediation P1-04/P1-05).

Answers exactly one question per artifact: does its recorded lineage (hash, strategy
id/version) match the CURRENT authoritative/frozen source it claims to be evidence for?
Never repairs, edits, or regenerates the artifact itself -- classification only. Six
classifications, matching the roadmap's own taxonomy:

    COUNTING          -- verified current, may satisfy a gate
    NON_COUNTING       -- verified but explicitly excluded from satisfying a gate
                          (e.g. bound to a superseded/draft hash, or a terminal-but-
                          preserved artifact like HYP_002 Attempt 1)
    PRE_REMEDIATION    -- known issue, awaiting an owner-authorized repair action
    STALE              -- was once valid evidence, superseded by a later artifact for
                          the same identity
    INVALID            -- lineage fields present but internally inconsistent/malformed
    UNKNOWN            -- insufficient information to classify at all

UNKNOWN and INVALID must never be treated as COUNTING by any caller -- enforced by
`satisfies_gate`, the single function callers should use to turn a classification into
a gate-input boolean, so "never let unknown lineage become PASS evidence" is one
function's responsibility, not re-implemented at every call site.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


class EvidenceClassification(str, Enum):
    COUNTING = "COUNTING"
    NON_COUNTING = "NON_COUNTING"
    NON_COUNTING_LINEAGE_MISMATCH = "NON_COUNTING_LINEAGE_MISMATCH"
    PRE_REMEDIATION = "PRE_REMEDIATION"
    STALE = "STALE"
    INVALID = "INVALID"
    UNKNOWN = "UNKNOWN"


# Standardized reason constant for the exact P1-05 failure mode: an artifact's recorded
# hash matches a KNOWN superseded/draft value rather than the current frozen one.
REASON_POPULATION_BOUND_TO_SUPERSEDED_PREREGISTRATION = "POPULATION_BOUND_TO_SUPERSEDED_PREREGISTRATION"


@dataclass(frozen=True)
class LineageVerificationResult:
    artifact_path: str
    classification: EvidenceClassification
    reason: str


def verify_lineage(
    artifact_path: str,
    recorded_hash: Optional[str],
    frozen_hash: Optional[str],
    superseded_hashes: Tuple[str, ...] = (),
) -> LineageVerificationResult:
    """Pure, read-only comparison -- takes hashes the caller already extracted from
    artifacts (this function opens no file itself, so it can never mutate one).

    - `frozen_hash` absent -> UNKNOWN (nothing authoritative to check against).
    - `recorded_hash` absent -> UNKNOWN (artifact has no lineage claim to verify).
    - exact match -> COUNTING.
    - matches a known-superseded/draft hash -> NON_COUNTING_LINEAGE_MISMATCH, reason
      REASON_POPULATION_BOUND_TO_SUPERSEDED_PREREGISTRATION.
    - matches neither -> INVALID (a lineage claim that is simply wrong, not merely
      outdated).
    """
    if frozen_hash is None:
        return LineageVerificationResult(artifact_path, EvidenceClassification.UNKNOWN,
                                          "no frozen/authoritative hash available to verify against")
    if recorded_hash is None:
        return LineageVerificationResult(artifact_path, EvidenceClassification.UNKNOWN,
                                          "artifact has no recorded lineage hash")
    if recorded_hash == frozen_hash:
        return LineageVerificationResult(artifact_path, EvidenceClassification.COUNTING,
                                          "recorded hash matches the frozen authoritative hash")
    if recorded_hash in superseded_hashes:
        return LineageVerificationResult(
            artifact_path, EvidenceClassification.NON_COUNTING_LINEAGE_MISMATCH,
            REASON_POPULATION_BOUND_TO_SUPERSEDED_PREREGISTRATION + ": artifact is bound "
            "to a superseded/draft hash, not the frozen authoritative one -- preserved "
            "as historical evidence, excluded from satisfying any gate",
        )
    return LineageVerificationResult(
        artifact_path, EvidenceClassification.INVALID,
        "recorded hash matches neither the frozen authoritative hash nor any known "
        "superseded hash",
    )


def verify_version_match(
    artifact_path: str,
    recorded_strategy_version: Optional[str],
    current_strategy_version: str,
) -> LineageVerificationResult:
    """Same fail-closed discipline for strategy_version binding. A version mismatch is
    always at least STALE (evidence for a real, but no-longer-current, version) --
    never silently reinterpreted as evidence for the current version."""
    if recorded_strategy_version is None:
        return LineageVerificationResult(artifact_path, EvidenceClassification.UNKNOWN,
                                          "artifact has no recorded strategy_version")
    if recorded_strategy_version == current_strategy_version:
        return LineageVerificationResult(artifact_path, EvidenceClassification.COUNTING,
                                          "recorded strategy_version matches current version")
    return LineageVerificationResult(
        artifact_path, EvidenceClassification.STALE,
        f"recorded strategy_version {recorded_strategy_version!r} != current "
        f"{current_strategy_version!r}",
    )


def satisfies_gate(result: LineageVerificationResult) -> bool:
    """The single place "does this classification satisfy a gate" is decided. Only
    COUNTING satisfies -- NON_COUNTING/PRE_REMEDIATION/STALE/INVALID/UNKNOWN never do,
    regardless of how compelling the underlying numbers look."""
    return result.classification == EvidenceClassification.COUNTING
