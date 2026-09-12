from __future__ import annotations

from external_candidate.version_guard import check_version_mutation


def test_no_known_binding_is_allowed():
    result = check_version_mutation("ST_X", "1.0.0", "sha256:abc", known_version_fingerprints=None)
    assert result.ok


def test_identical_fingerprint_is_allowed_as_resubmission():
    known = {("ST_X", "1.0.0"): "sha256:abc"}
    result = check_version_mutation("ST_X", "1.0.0", "sha256:abc", known)
    assert result.ok


def test_different_fingerprint_under_same_version_is_rejected():
    known = {("ST_X", "1.0.0"): "sha256:abc"}
    result = check_version_mutation("ST_X", "1.0.0", "sha256:xyz", known)
    assert not result.ok
    assert "different fingerprint" in result.reason
