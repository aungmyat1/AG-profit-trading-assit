"""Tests for validation_framework.evidence_reconciliation (Cycle-1 remediation
P1-04/P1-05). Includes the adversarial cases required by the remediation brief plus a
read-only verification against the REAL HYP_001_GBPUSD_REPLICATION_R1 artifact that
motivated P1-05."""
from __future__ import annotations

import hashlib
import json
import os

from validation_framework.evidence_reconciliation import (
    EvidenceClassification,
    satisfies_gate,
    verify_lineage,
    verify_version_match,
)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

_FROZEN = "7ee1554cc041c950540f2c75931719e9fefd351d9c5fba5561fa87104c2eaa22"
_SUPERSEDED_DRAFT = "b401e9745e1be90b5a510e41c60923a79262fa9907a6dc49d7d92ee4c7a2853e"


def test_matching_hash_is_counting():
    result = verify_lineage("a.json", "abc", "abc")
    assert result.classification == EvidenceClassification.COUNTING
    assert satisfies_gate(result) is True


def test_superseded_draft_hash_is_non_counting_lineage_mismatch():
    result = verify_lineage("a.json", _SUPERSEDED_DRAFT, _FROZEN, superseded_hashes=(_SUPERSEDED_DRAFT,))
    assert result.classification == EvidenceClassification.NON_COUNTING_LINEAGE_MISMATCH
    assert "POPULATION_BOUND_TO_SUPERSEDED_PREREGISTRATION" in result.reason
    assert satisfies_gate(result) is False


def test_unrelated_wrong_hash_is_invalid_not_counting():
    result = verify_lineage("a.json", "deadbeef", _FROZEN, superseded_hashes=(_SUPERSEDED_DRAFT,))
    assert result.classification == EvidenceClassification.INVALID
    assert satisfies_gate(result) is False


def test_missing_frozen_hash_is_unknown():
    result = verify_lineage("a.json", "abc", None)
    assert result.classification == EvidenceClassification.UNKNOWN
    assert satisfies_gate(result) is False


def test_missing_recorded_hash_is_unknown():
    result = verify_lineage("a.json", None, _FROZEN)
    assert result.classification == EvidenceClassification.UNKNOWN
    assert satisfies_gate(result) is False


def test_unknown_never_satisfies_gate_exhaustive():
    for classification in EvidenceClassification:
        if classification != EvidenceClassification.COUNTING:
            from validation_framework.evidence_reconciliation import LineageVerificationResult
            r = LineageVerificationResult("x.json", classification, "synthetic")
            assert satisfies_gate(r) is False, f"{classification} incorrectly satisfies a gate"


def test_wrong_version_evidence_is_stale_not_counting():
    result = verify_version_match("a.json", "1.0.0", "1.1.0")
    assert result.classification == EvidenceClassification.STALE
    assert satisfies_gate(result) is False


def test_matching_version_is_counting():
    result = verify_version_match("a.json", "1.0.0", "1.0.0")
    assert result.classification == EvidenceClassification.COUNTING


def test_missing_version_is_unknown():
    result = verify_version_match("a.json", None, "1.0.0")
    assert result.classification == EvidenceClassification.UNKNOWN


# --- P1-05: real HYP_001_GBPUSD_REPLICATION_R1 lineage, verified read-only -----------

_GBPUSD_DIR = os.path.join(
    REPO_ROOT, "artifacts", "validation", "ST_SESSION_SWEEP_CONTINUATION_V1",
    "HYP_001_GBPUSD_REPLICATION_R1",
)
_MANIFEST_PATH = os.path.join(_GBPUSD_DIR, "POPULATION", "population_manifest.json")
_STATUS_PATH = os.path.join(_GBPUSD_DIR, "replication_status.json")


def _file_sha256(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def test_p1_05_gbpusd_population_manifest_is_lineage_mismatch():
    """Confirms DeepSeek's P1-05 finding directly from the real repository artifacts:
    the population manifest's preregistration_hash is the SUPERSEDED draft hash, not
    the frozen authoritative one recorded in replication_status.json."""
    if not (os.path.isfile(_MANIFEST_PATH) and os.path.isfile(_STATUS_PATH)):
        import pytest
        pytest.skip("HYP_001_GBPUSD_REPLICATION_R1 artifacts not present in this checkout")

    before_manifest_hash = _file_sha256(_MANIFEST_PATH)
    before_status_hash = _file_sha256(_STATUS_PATH)

    with open(_MANIFEST_PATH, encoding="utf-8") as fh:
        manifest = json.load(fh)
    with open(_STATUS_PATH, encoding="utf-8") as fh:
        status = json.load(fh)

    recorded_hash = manifest["preregistration_hash"]
    frozen_hash = status["preregistration"]["frozen_sha256"]
    superseded = (status["preregistration"]["draft_sha256_superseded"],)

    result = verify_lineage(_MANIFEST_PATH, recorded_hash, frozen_hash, superseded_hashes=superseded)

    assert result.classification == EvidenceClassification.NON_COUNTING_LINEAGE_MISMATCH
    assert satisfies_gate(result) is False

    # Immutability: reading and classifying must never modify the source artifacts.
    assert _file_sha256(_MANIFEST_PATH) == before_manifest_hash
    assert _file_sha256(_STATUS_PATH) == before_status_hash
