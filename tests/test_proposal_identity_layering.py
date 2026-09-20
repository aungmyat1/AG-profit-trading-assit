"""P2 focused tests: proposal identity layering audit
(AG_SCHEDULER_AND_LARGE_SMC_WATCH_HARDENING_V1).

Proves the reported duplicate-proposal problem is a LAYER COLLAPSE (proposal identity
derived from observation identity), that the three layers resolve deterministically and
separately, and that the audit is read-only and fails closed. Does not assert any
change to frozen canonical behavior -- no test here requires `_decision_id`, the FX
adapter's `proposal_envelope_id`, or `ProposalLedger` keying to differ from today.
"""
from __future__ import annotations

import ast
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
import sys

sys.path.insert(0, str(REPO_ROOT / "src"))

from proposal_envelope.identity_audit import (  # noqa: E402
    IDENTITY_LAYER_SOURCES,
    LAYER_LOGICAL_SETUP,
    LAYER_OBSERVATION,
    LAYER_PROPOSAL,
    SOURCE_CANONICAL_SETUP_ID,
    SOURCE_DERIVED_SSC_COMPOSITE,
    IdentityResolutionError,
    audit_ledger_file,
    audit_ledger_records,
    resolve_identity_layers,
)

LEDGER_PATH = REPO_ROOT / "state" / "proposal_ledger" / "proposal_ledger.json"

SETUP_ID = "ST_ASIAN_SWEEP_5R_V1:LONDON_NEWYORK:EURUSD:2026-09-15"


def _fx_record(*, envelope_id: str, asof: str, entry: float = 1.15397,
               direction: str = "SHORT", stop: float = 1.15416,
               targets=(1.15264, 1.15302), setup_id: str = SETUP_ID,
               data_version: str | None = None) -> dict:
    """Mirrors the exact persisted shape of an FX ledger record (see the real ledger's
    `current` dicts) -- only the fields the identity layers read plus geometry."""
    return {
        "proposal_envelope_id": envelope_id,
        "confirmation_evidence": {"setup_id": setup_id},
        "data_provenance": {
            "data_version": data_version or f"SNAPSHOT-EURUSD-{asof[:10]}-deadbeef",
            "market_data_asof": asof,
        },
        "direction": direction,
        "entry": entry,
        "stop": stop,
        "targets": list(targets),
    }


def test_three_identity_layers_are_distinct_concepts():
    """The three layers must be separately named and separately sourced -- collapsing
    any two is the defect being audited."""
    assert len({LAYER_LOGICAL_SETUP, LAYER_OBSERVATION, LAYER_PROPOSAL}) == 3
    assert set(IDENTITY_LAYER_SOURCES) == {LAYER_LOGICAL_SETUP, LAYER_OBSERVATION, LAYER_PROPOSAL}
    assert "setup_id" in IDENTITY_LAYER_SOURCES[LAYER_LOGICAL_SETUP]
    assert "data_version" in IDENTITY_LAYER_SOURCES[LAYER_OBSERVATION]
    assert "proposal_envelope_id" in IDENTITY_LAYER_SOURCES[LAYER_PROPOSAL]


def test_logical_setup_identity_is_stable_across_observations():
    """Two polls of the SAME setup at different times share LOGICAL SETUP identity but
    differ in OBSERVATION and PROPOSAL identity. This is exactly the observed
    production pattern that inflates the ledger."""
    a = resolve_identity_layers(_fx_record(
        envelope_id="FX:DECISION-EURUSD-aaa", asof="2026-09-15T12:30:00+00:00"))
    b = resolve_identity_layers(_fx_record(
        envelope_id="FX:DECISION-EURUSD-bbb", asof="2026-09-15T12:45:00+00:00"))

    assert a.logical_setup_id == b.logical_setup_id == SETUP_ID
    assert a.observation_id != b.observation_id
    assert a.proposal_envelope_id != b.proposal_envelope_id


def test_resolution_is_deterministic():
    """Same record -> identical layers, across repeated calls (replay/restart safe)."""
    record = _fx_record(envelope_id="FX:DECISION-EURUSD-ccc", asof="2026-09-15T13:00:00+00:00")
    assert resolve_identity_layers(record) == resolve_identity_layers(record)


def test_observation_identity_ignores_proposal_identity():
    """Observation identity is composed from setup + data provenance only. Renaming the
    proposal envelope must NOT change it (proving the layers are not conflated)."""
    a = resolve_identity_layers(_fx_record(
        envelope_id="FX:DECISION-EURUSD-xxx", asof="2026-09-15T14:00:00+00:00"))
    b = resolve_identity_layers(_fx_record(
        envelope_id="FX:DECISION-EURUSD-yyy", asof="2026-09-15T14:00:00+00:00"))
    assert a.observation_id == b.observation_id
    assert a.proposal_envelope_id != b.proposal_envelope_id


def test_duplicate_problem_reproduced_on_synthetic_poll_series():
    """Reproduces the reported defect deterministically: 11 polls of one unchanged
    setup (the exact real-world case, 12:30->15:00 M15 closes) persist 11 records with
    1 distinct geometry and 1 logical setup."""
    records = []
    for i in range(11):
        minute = 30 + i * 15
        hour = 12 + minute // 60
        asof = f"2026-09-15T{hour:02d}:{minute % 60:02d}:00+00:00"
        records.append(_fx_record(envelope_id=f"FX:DECISION-EURUSD-{i:02d}", asof=asof))

    audit = audit_ledger_records(records)

    assert audit.total_records == 11
    assert audit.distinct_logical_setups == 1
    assert audit.distinct_observations == 11
    assert audit.duplicate_records == 10
    assert audit.per_setup[0].distinct_geometries == 1
    assert audit.duplication_ratio == 11.0
    assert audit.duplicate_proposal_problem_reproduced is True


def test_genuinely_different_setups_are_not_collapsed():
    """Two distinct logical setups must NOT be merged by the audit -- the fix must not
    over-deduplicate and hide real setups."""
    records = [
        _fx_record(envelope_id="FX:D-1", asof="2026-09-15T12:30:00+00:00",
                   setup_id="ST_ASIAN_SWEEP_5R_V1:LONDON_NEWYORK:EURUSD:2026-09-15"),
        _fx_record(envelope_id="FX:D-2", asof="2026-09-15T12:30:00+00:00",
                   setup_id="ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:EURUSD:2026-09-16"),
    ]
    audit = audit_ledger_records(records)
    assert audit.distinct_logical_setups == 2
    assert audit.duplicate_records == 0
    assert audit.duplicate_proposal_problem_reproduced is False


def test_same_observation_different_geometry_is_flagged_not_merged():
    """The observed SSC pattern: one observation, two geometries. These are NOT the
    same setup state and must remain separately visible via distinct_geometries."""
    records = [
        _fx_record(envelope_id="FX:G-1", asof="2026-09-15T12:30:00+00:00",
                   entry=1.15397, stop=1.15416),
        _fx_record(envelope_id="FX:G-2", asof="2026-09-15T12:30:00+00:00",
                   entry=1.15420, stop=1.15450),
    ]
    audit = audit_ledger_records(records)
    assert audit.per_setup[0].distinct_observations == 1
    assert audit.per_setup[0].distinct_geometries == 2


def test_ssc_composite_identity_is_derived_and_flagged_non_authoritative():
    """The SSC adapter is the one family emitting no `confirmation_evidence.setup_id`.
    Its derived key must be explicitly flagged so it is never mistaken for the
    canonical field."""
    record = {
        "proposal_envelope_id": (
            "SSC:EURUSD|ASIAN_LONDON|2026-09-17|EURUSD-ASIAN_LONDON-20260917-SHORT"
            "|S1_SWEEP_REVERSAL|2026-09-17 08:00:00+00:00"),
        "confirmation_evidence": {},
        "setup_evidence": {"session_pair": "ASIAN_LONDON", "trading_date": "2026-09-17",
                           "setup_model": "S1_SWEEP_REVERSAL"},
        "data_provenance": {"market_data_asof": "2026-09-17T08:00:00+00:00"},
        "direction": "SHORT", "entry": 1.1, "stop": 1.2, "targets": [],
    }
    layers = resolve_identity_layers(record)
    assert layers.identity_source == SOURCE_DERIVED_SSC_COMPOSITE
    assert layers.logical_identity_is_authoritative is False
    # entry_time (the volatile field) must NOT appear in the logical key
    assert "08:00:00" not in layers.logical_setup_id
    assert layers.logical_setup_id.startswith("SSC:EURUSD:ASIAN_LONDON:2026-09-17:")


def test_canonical_setup_id_is_flagged_authoritative():
    layers = resolve_identity_layers(_fx_record(envelope_id="FX:D-a", asof="2026-09-15T12:30:00+00:00"))
    assert layers.identity_source == SOURCE_CANONICAL_SETUP_ID
    assert layers.logical_identity_is_authoritative is True


def test_missing_logical_identity_fails_closed_not_silently_bucketed():
    """An unknown family with no setup_id must be REPORTED, never folded into a
    synthetic 'unknown' key that would conceal the gap."""
    record = {
        "proposal_envelope_id": "MYSTERY:abc",
        "confirmation_evidence": {},
        "setup_evidence": {},
        "data_provenance": {},
    }
    with pytest.raises(IdentityResolutionError, match="UNRESOLVABLE_LOGICAL_SETUP_IDENTITY"):
        resolve_identity_layers(record)


def test_missing_proposal_identity_fails_closed():
    with pytest.raises(IdentityResolutionError, match="UNRESOLVABLE_PROPOSAL_IDENTITY"):
        resolve_identity_layers({"confirmation_evidence": {"setup_id": SETUP_ID}})


def test_unresolvable_records_are_reported_and_excluded_from_counts():
    records = [
        _fx_record(envelope_id="FX:OK-1", asof="2026-09-15T12:30:00+00:00"),
        {"proposal_envelope_id": "MYSTERY:abc", "confirmation_evidence": {},
         "setup_evidence": {}, "data_provenance": {}},
    ]
    audit = audit_ledger_records(records)
    assert audit.total_records == 1
    assert len(audit.unresolvable) == 1


def test_audit_does_not_write_to_the_ledger_file():
    """The audit must be strictly read-only -- no frozen evidence may be mutated by a
    diagnostic run."""
    if not LEDGER_PATH.exists():
        pytest.skip("proposal ledger not present in this checkout")
    before = hashlib.sha256(LEDGER_PATH.read_bytes()).hexdigest()
    audit_ledger_file(str(LEDGER_PATH))
    after = hashlib.sha256(LEDGER_PATH.read_bytes()).hexdigest()
    assert before == after


def test_live_ledger_audit_is_internally_consistent():
    """Live-artifact assertions are structural, not exact, so this stays valid as the
    ledger grows. Asserts the audit's own accounting adds up."""
    if not LEDGER_PATH.exists():
        pytest.skip("proposal ledger not present in this checkout")
    audit = audit_ledger_file(str(LEDGER_PATH))
    assert audit.total_records == sum(s.proposal_records for s in audit.per_setup)
    assert audit.unresolvable == ()
    assert audit.distinct_logical_setups == len(audit.per_setup)
    assert audit.duplicate_records == audit.total_records - audit.distinct_logical_setups
    # distinct observations can never exceed records
    assert audit.distinct_observations <= audit.total_records


def test_audit_module_has_no_execution_or_mt5_order_reach():
    """Static boundary: this audit must never be able to place an order."""
    path = REPO_ROOT / "src" / "proposal_envelope" / "identity_audit.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    forbidden = {"execution.executor", "execution.coordinator", "execution.adapter",
                 "mt5.management_gateway", "MetaTrader5"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in forbidden, f"imports {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module not in forbidden, f"imports from {module}"
            assert not module.startswith("execution."), f"imports from {module}"


def test_audit_module_never_calls_order_functions():
    path = REPO_ROOT / "src" / "proposal_envelope" / "identity_audit.py"
    source = path.read_text(encoding="utf-8")
    for name in ("order_send", "order_check", "positions_close", "positions_modify"):
        assert name not in source
