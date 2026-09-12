from __future__ import annotations

from external_candidate.evidence_envelope import EVIDENCE_TYPE_OOS, build_envelope
from external_candidate.models import NOT_AVAILABLE


def test_envelope_carries_full_identity():
    envelope = build_envelope(
        strategy_id="ST_X", strategy_version="1.1.0", candidate_id="C1",
        config_fingerprint="sha256:cfg", dataset_fingerprint="sha256:ds",
        evidence_type=EVIDENCE_TYPE_OOS, generated_at="2026-09-12T00:00:00+00:00",
        payload={"sample_size": 10},
    )
    assert envelope.strategy_id == "ST_X"
    assert envelope.git_commit == NOT_AVAILABLE
    assert envelope.envelope_fingerprint


def test_envelope_fingerprint_is_deterministic_and_content_sensitive():
    kwargs = dict(
        strategy_id="ST_X", strategy_version="1.1.0", candidate_id="C1",
        config_fingerprint="sha256:cfg", dataset_fingerprint="sha256:ds",
        evidence_type=EVIDENCE_TYPE_OOS, generated_at="2026-09-12T00:00:00+00:00",
    )
    e1 = build_envelope(**kwargs, payload={"sample_size": 10})
    e2 = build_envelope(**kwargs, payload={"sample_size": 10})
    e3 = build_envelope(**kwargs, payload={"sample_size": 11})
    assert e1.envelope_fingerprint == e2.envelope_fingerprint
    assert e1.envelope_fingerprint != e3.envelope_fingerprint
