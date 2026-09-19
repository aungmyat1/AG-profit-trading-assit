"""SSC v1.0.1 POST-G2 AUTHORITY SYNCHRONIZATION -- narrow regression tests.

Proves the governance/context state is synchronized with the already-frozen DEV_002 G2
population:
  1. DEV_002 frozen identity binds correctly (population hash recomputed == recorded).
  2. The consumption registry marks DEV_002 CONSUMED (with prior history preserved).
  3. The SVOS context generator reports the current G2 frozen state.
  4. A population-hash mismatch fails closed (no PASS is manufactured).
  5. Protected evidence remains untouched (CONFIRM_001/HOLDOUT/OOS access_count = 0).
  6. G3 remains unsigned / not evaluated.
  7. Optimization remains ineligible.

Read-only: no replay, no optimization, no protected-data access, no strategy change.
"""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DEV002_DIR = REPO / "artifacts" / "validation" / "ST_SESSION_SWEEP_CONTINUATION_V1" / "SSC_V1_0_1_G2_DEV_002"
POPULATION_PATH = DEV002_DIR / "G2_POPULATION_V1.json"
MANIFEST_PATH = DEV002_DIR / "G2_POPULATION_MANIFEST_V1.json"
REGISTRY_PATH = REPO / "artifacts" / "validation" / "ST_SESSION_SWEEP_CONTINUATION_V1" / "SSC_V1_0_1_DATA_CONSUMPTION_REGISTRY_V1.json"
CTX_PATH = REPO / "artifacts" / "validation" / "ST_SESSION_SWEEP_CONTINUATION_V1" / "svos_context.json"
GENERATOR_PATH = REPO / "scripts" / "export_ssc_svos_context.py"

EXPECTED_HASH = "832e8e13c74a5401684a401cdbe4c42aa95e95661928fe596804068e7067ab5e"
EXPECTED_POPULATION_ID = "SSC_V1_0_1_G2_DEV_002_POPULATION_V1"


def _load_generator():
    spec = importlib.util.spec_from_file_location("export_ssc_svos_context", str(GENERATOR_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- 1. DEV_002 frozen identity binds correctly ---------------------------------------
def test_dev002_population_identity_binds():
    from research.session_lifecycle import population_hash

    pop = json.loads(POPULATION_PATH.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert pop["population_id"] == EXPECTED_POPULATION_ID
    assert pop["population_count"] == 22
    assert pop["population_sha256"] == EXPECTED_HASH
    assert population_hash(pop["occurrences"]) == EXPECTED_HASH
    assert manifest["population_sha256"] == EXPECTED_HASH
    assert manifest["population_count"] == 22


# --- 2. Consumption registry marks DEV_002 consumed -----------------------------------
def test_consumption_registry_marks_dev002_consumed():
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    rec = next(r for r in registry["records"] if r["dataset_id"] == "SSC_V1_0_1_G2_DEV_002")
    assert rec["status"] == "CONSUMED"
    assert rec["counting_status"] == "CONSUMED"
    assert rec["reusable_for_new_development"] is False
    events = rec["consumption_events"]
    assert len(events) == 1
    assert events[0]["consumption_event"] == "G2_POPULATION_FROZEN"
    assert events[0]["population_id"] == EXPECTED_POPULATION_ID
    assert events[0]["population_hash"] == EXPECTED_HASH
    assert events[0]["N"] == 22
    # prior history preserved, not erased
    assert rec["status_history"][0]["counting_status"] == "ACTIVE_G2_REPLAY_CANDIDATE"
    assert registry["post_g2_synchronization"]["population_hash"] == EXPECTED_HASH
    assert registry["summary"]["admissible_fresh_development_dataset_exists"] is False


# --- 3. Context generator reports the current G2 frozen state -------------------------
def test_context_generator_reports_g2_frozen_state():
    mod = _load_generator()
    ctx = mod.collect_context(now=datetime(2026, 9, 19, tzinfo=timezone.utc))
    assert ctx["gates"]["G2"]["status"] == "PASS"
    assert ctx["furthest_verified_gate"] is None  # G0/G1 still PARTIAL -> no advance
    g2 = ctx["g2_population"]
    assert g2["status"] == "POPULATION_FROZEN"
    assert g2["population_id"] == EXPECTED_POPULATION_ID
    assert g2["population_n"] == 22
    assert g2["population_hash"] == EXPECTED_HASH
    assert g2["population_hash_recomputed"] == EXPECTED_HASH
    assert g2["determinism"] == "PASS"


def test_generated_context_artifact_is_current():
    ctx = json.loads(CTX_PATH.read_text(encoding="utf-8"))
    assert ctx["g2_population"]["population_hash"] == EXPECTED_HASH
    assert ctx["g2_population"]["status"] == "POPULATION_FROZEN"
    assert ctx["hypothesis_status"] == "NO_NEW_HYPOTHESIS_JUSTIFIED"
    assert ctx["independent_replication"] == "BLOCKED_NO_ADMISSIBLE_REPLICATION_DATA"


# --- 4. Population hash mismatch fails closed ----------------------------------------
def test_population_hash_mismatch_fails_closed(monkeypatch):
    mod = _load_generator()
    monkeypatch.setattr(mod, "EXPECTED_G2_POPULATION_HASH", "0" * 64)
    with pytest.raises(ValueError):
        mod._read_g2_population_authority()


def test_population_n_mismatch_fails_closed(monkeypatch):
    mod = _load_generator()
    monkeypatch.setattr(mod, "EXPECTED_G2_POPULATION_N", 999)
    with pytest.raises(ValueError):
        mod._read_g2_population_authority()


def test_missing_population_artifact_fails_closed(monkeypatch):
    mod = _load_generator()
    monkeypatch.setattr(mod, "G2_POPULATION_PATH", "artifacts/does/not/exist.json")
    with pytest.raises(FileNotFoundError):
        mod._read_g2_population_authority()


# --- 5. Protected evidence remains untouched ------------------------------------------
def test_protected_evidence_untouched():
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    for protected_id in ("CONFIRM_001", "HOLDOUT", "OOS"):
        rec = next(r for r in registry["records"] if r["dataset_id"] == protected_id)
        assert rec["protected_status"] == "PROTECTED"
        assert "NONE" in rec["prior_consumption"]
        assert rec["reusable_for_new_development"] is False
    ctx = json.loads(CTX_PATH.read_text(encoding="utf-8"))
    assert ctx["holdout"]["sealed"] is True
    assert ctx["holdout"]["access_count"] == 0


# --- 6. G3 remains unsigned / not evaluated -------------------------------------------
def test_g3_remains_unsigned_not_evaluated():
    ctx = json.loads(CTX_PATH.read_text(encoding="utf-8"))
    assert ctx["gates"]["G3"]["status"] != "PASS"
    assert ctx["g3_verdict"] == "NOT_EVALUATED_UNSIGNED_CONTRACT"
    assert ctx["economic_gate"]["signed"] is False
    assert ctx["economic_gate"]["status"] == "PROPOSED"


# --- 7. Optimization remains ineligible ------------------------------------------------
def test_optimization_remains_ineligible():
    import yaml

    ctx = json.loads(CTX_PATH.read_text(encoding="utf-8"))
    assert ctx["optimization_eligible"] is False
    contract = yaml.safe_load(
        (REPO / "config" / "governance" / "optimization_admission_contract.yaml").read_text(encoding="utf-8")
    )
    assert contract["identity"]["status"] == "PROPOSED"
    assert contract["identity"]["signed_by"] is None
