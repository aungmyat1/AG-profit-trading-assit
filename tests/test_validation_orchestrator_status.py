"""Tests for validation_orchestrator.status -- AVO-WP1.

These tests inject fake collaborators (get_strategy/has_validation_adapter/
get_validation_record/list_strategies) rather than touching real repository files,
so fail-closed paths (missing evidence, contradictory evidence, unknown strategy) can
be exercised deterministically and in isolation. A separate small group of tests runs
against the REAL repository to prove strategy discovery/representation and execution
containment against the actual canonical files.
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from validation_orchestrator.status import (
    UnknownStrategyError,
    derive_all_status,
    derive_status,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
STATUS_MODULE_PATH = REPO_ROOT / "src" / "validation_orchestrator" / "status.py"
CLI_PATH = REPO_ROOT / "scripts" / "run_validation_orchestrator.py"
CAMPAIGN_DIR = (
    REPO_ROOT
    / "artifacts"
    / "validation"
    / "ST_LARGE_SMC_V1"
    / "EURUSD_ADMISSION_CONTRACTS"
    / "friction_campaign_wp3a1"
)
CAMPAIGN_MANIFEST = CAMPAIGN_DIR / "campaign_manifest.json"
CAMPAIGN_MANIFEST_HASH = CAMPAIGN_DIR / "campaign_manifest_hash.json"


def _entry(**overrides) -> dict:
    base = dict(
        strategy_id="ST_FAKE_V1",
        registered=True,
        active=True,
        research=True,
        demo_authorized=False,
        live_authorized=False,
        lifecycle_stage="FORWARD_RESEARCH",
        semantic_version="1.0.0",
    )
    base.update(overrides)
    return base


def _gate(name: str, status: str) -> dict:
    return {"gate_name": name, "status": status, "evidence_refs": []}


# ---------------------------------------------------------------------------
# 1. all-strategy discovery
# ---------------------------------------------------------------------------


def test_all_strategy_discovery_uses_list_strategies_not_a_hardcoded_list():
    entries = [_entry(strategy_id="ST_A_V1"), _entry(strategy_id="ST_B_V1"), _entry(strategy_id="SESSION_TRADE_V1")]

    statuses = derive_all_status(
        list_strategies=lambda: entries,
        has_validation_adapter=lambda sid: sid == "ST_A_V1",
        get_validation_record=lambda sid: {
            "semantic_version": "1.0.0",
            "lifecycle_stage": "FORWARD_RESEARCH",
            "promotion_blockers": [],
            "gates": [_gate("G0", "PASS")],
        },
    )

    assert [s.strategy_id for s in statuses] == ["ST_A_V1", "ST_B_V1", "SESSION_TRADE_V1"]
    assert statuses[0].validation_state == "GATES_ALL_PASS_NO_BLOCKERS"
    assert statuses[1].validation_state == "NO_VALIDATION_ADAPTER"
    assert statuses[2].validation_state == "NO_VALIDATION_ADAPTER"


# ---------------------------------------------------------------------------
# 2. selected-strategy status
# ---------------------------------------------------------------------------


def test_selected_strategy_status_reports_current_and_furthest_gate():
    entry = _entry(strategy_id="ST_LARGE_SMC_V1", lifecycle_stage="FORWARD_RESEARCH", semantic_version="1.0.7")
    record = {
        "semantic_version": "1.0.7",
        "lifecycle_stage": "FORWARD_RESEARCH",
        "promotion_blockers": ["SHADOW_ENTRY_PREFLIGHT"],
        "gates": [
            _gate("HISTORICAL_REPLAY", "PASS"),
            _gate("FRICTION_STRESS_TEST", "BLOCKED"),
            _gate("OOS_VALIDATION", "NOT_VERIFIED"),
        ],
    }

    status = derive_status(
        "ST_LARGE_SMC_V1",
        get_strategy=lambda sid: entry if sid == "ST_LARGE_SMC_V1" else None,
        has_validation_adapter=lambda sid: True,
        get_validation_record=lambda sid: record,
    )

    assert status.strategy_id == "ST_LARGE_SMC_V1"
    assert status.strategy_version == "1.0.7"
    assert status.lifecycle_stage == "FORWARD_RESEARCH"
    assert status.furthest_verified_gate == "HISTORICAL_REPLAY"
    assert status.current_gate == "FRICTION_STRESS_TEST"
    assert status.validation_state == "EVIDENCE_INCOMPLETE"
    assert "SHADOW_ENTRY_PREFLIGHT" in status.blocking_reasons
    assert status.next_safe_action == "CONTINUE_EVIDENCE_COLLECTION"


# ---------------------------------------------------------------------------
# 3. deterministic repeated evaluation
# ---------------------------------------------------------------------------


def test_repeated_evaluation_against_unchanged_evidence_is_semantically_identical():
    entry = _entry()
    record = {
        "semantic_version": "1.0.0",
        "lifecycle_stage": "FORWARD_RESEARCH",
        "promotion_blockers": [],
        "gates": [_gate("G0", "PASS"), _gate("G1", "FAIL")],
    }

    kwargs = dict(
        get_strategy=lambda sid: entry,
        has_validation_adapter=lambda sid: True,
        get_validation_record=lambda sid: record,
    )
    first = derive_status("ST_FAKE_V1", **kwargs)
    second = derive_status("ST_FAKE_V1", **kwargs)

    assert first.semantic_tuple() == second.semantic_tuple()
    # updated_at_utc is diagnostic only and is explicitly excluded from semantic_tuple();
    # it is still always populated.
    assert first.updated_at_utc
    assert second.updated_at_utc


def test_derive_all_status_is_deterministic_across_repeated_calls():
    entries = [_entry(strategy_id="ST_A_V1"), _entry(strategy_id="ST_B_V1")]
    kwargs = dict(
        list_strategies=lambda: entries,
        has_validation_adapter=lambda sid: False,
        get_validation_record=lambda sid: None,
    )
    first = [s.semantic_tuple() for s in derive_all_status(**kwargs)]
    second = [s.semantic_tuple() for s in derive_all_status(**kwargs)]
    assert first == second


# ---------------------------------------------------------------------------
# 4. missing evidence -> fail closed
# ---------------------------------------------------------------------------


def test_missing_evidence_raises_on_validation_record_error():
    entry = _entry()

    def _raise(strategy_id: str):
        raise FileNotFoundError("no such adapter evidence file")

    status = derive_status(
        "ST_FAKE_V1",
        get_strategy=lambda sid: entry,
        has_validation_adapter=lambda sid: True,
        get_validation_record=_raise,
    )

    assert status.validation_state == "EVIDENCE_ERROR"
    assert status.next_safe_action == "RESOLVE_EVIDENCE_ERROR"
    assert any("EVIDENCE_ERROR" in reason for reason in status.blocking_reasons)
    assert status.evidence_status == "NOT_TRACKED_BY_WP1"


# ---------------------------------------------------------------------------
# 5. contradictory evidence -> fail closed
# ---------------------------------------------------------------------------


def test_contradictory_evidence_fails_closed_not_trusted():
    """Simulates the real contradiction lifecycle_registry.LifecycleRegistryError
    guards against: strategy_lifecycle.yaml's semantic_version does not match the
    adapter's own SEMANTIC_VERSION. The real adapter raises in this situation; this
    orchestrator must never interpret that raise as anything but EVIDENCE_ERROR."""
    entry = _entry()

    def _raise_mismatch(strategy_id: str):
        raise RuntimeError(
            f"{strategy_id}: lifecycle registry semantic_version '1.0.0' does not match "
            "caller's semantic_version '1.0.1'"
        )

    status = derive_status(
        "ST_FAKE_V1",
        get_strategy=lambda sid: entry,
        has_validation_adapter=lambda sid: True,
        get_validation_record=_raise_mismatch,
    )

    assert status.validation_state == "EVIDENCE_ERROR"
    assert status.demo_authorized is False
    assert status.live_authorized is False


def test_adapter_reports_true_but_record_is_none_fails_closed():
    entry = _entry()

    status = derive_status(
        "ST_FAKE_V1",
        get_strategy=lambda sid: entry,
        has_validation_adapter=lambda sid: True,
        get_validation_record=lambda sid: None,
    )

    assert status.validation_state == "EVIDENCE_ERROR"


# ---------------------------------------------------------------------------
# 6. unknown strategy -> safe failure
# ---------------------------------------------------------------------------


def test_unknown_strategy_raises_rather_than_fabricating_status():
    with pytest.raises(UnknownStrategyError) as excinfo:
        derive_status("NOT_A_REAL_STRATEGY", get_strategy=lambda sid: None)
    assert excinfo.value.strategy_id == "NOT_A_REAL_STRATEGY"


def test_cli_reports_safe_failure_for_unknown_strategy():
    result = subprocess.run(
        [sys.executable, str(CLI_PATH), "--strategy", "NOT_A_REAL_STRATEGY"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["error"] == "STRATEGY_NOT_REGISTERED"
    assert payload["strategy_id"] == "NOT_A_REAL_STRATEGY"


# ---------------------------------------------------------------------------
# 7. Demo/Live flags faithfully read
# ---------------------------------------------------------------------------


def test_demo_and_live_authorized_flags_pass_through_unmodified():
    entry = _entry(demo_authorized=True, live_authorized=False)
    status = derive_status(
        "ST_FAKE_V1",
        get_strategy=lambda sid: entry,
        has_validation_adapter=lambda sid: False,
    )
    assert status.demo_authorized is True
    assert status.live_authorized is False

    entry2 = _entry(demo_authorized=False, live_authorized=True)
    status2 = derive_status(
        "ST_FAKE_V1",
        get_strategy=lambda sid: entry2,
        has_validation_adapter=lambda sid: False,
    )
    assert status2.demo_authorized is False
    assert status2.live_authorized is True


# ---------------------------------------------------------------------------
# 8. no execution-path imports/calls
# ---------------------------------------------------------------------------

_FORBIDDEN_SUBSTRINGS = (
    "order_send",
    "order_check",
    "mt5.management_gateway",
    "execution.executor",
    "execution.coordinator",
    "execution.mt5_gateway",
    "authorization.strategy_authority",
    "authorization.telegram_gateway",
    "import MetaTrader5",
    "import mt5",
)


@pytest.mark.parametrize("path", [STATUS_MODULE_PATH, CLI_PATH])
def test_no_execution_authority_substrings_in_source(path: Path):
    source = path.read_text(encoding="utf-8")
    for forbidden in _FORBIDDEN_SUBSTRINGS:
        assert forbidden not in source, f"{path} must not reference {forbidden!r}"


@pytest.mark.parametrize("path", [STATUS_MODULE_PATH, CLI_PATH])
def test_only_expected_modules_imported(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])

    forbidden_roots = {"mt5", "MetaTrader5", "execution", "authorization"}
    assert not (imported_roots & forbidden_roots), (
        f"{path} imports forbidden module root(s): {imported_roots & forbidden_roots}"
    )


def test_status_module_has_no_write_mode_file_access():
    """Static containment check: WP1 is read-only, so its own source must contain no
    write-mode file open, no os.remove/unlink, and no yaml/json dump-to-file calls."""
    source = STATUS_MODULE_PATH.read_text(encoding="utf-8")
    for forbidden in ('open(', 'os.remove', 'os.unlink', 'shutil.rmtree', '.dump(', 'yaml.safe_dump'):
        assert forbidden not in source, f"validation_orchestrator/status.py must not contain {forbidden!r}"


# ---------------------------------------------------------------------------
# 9. active campaign remains untouched
# ---------------------------------------------------------------------------


def test_frozen_wp3a1_campaign_manifest_untouched_by_full_status_run():
    before_manifest = CAMPAIGN_MANIFEST.read_bytes()
    before_hash = CAMPAIGN_MANIFEST_HASH.read_bytes()

    derive_all_status()

    assert CAMPAIGN_MANIFEST.read_bytes() == before_manifest
    assert CAMPAIGN_MANIFEST_HASH.read_bytes() == before_hash


def test_orchestrator_source_never_references_the_frozen_campaign_path():
    source = STATUS_MODULE_PATH.read_text(encoding="utf-8") + CLI_PATH.read_text(encoding="utf-8")
    assert "friction_campaign_wp3a1" not in source
    assert "LSMC_EURUSD_FRICTION_WP3A1_V1" not in source


# ---------------------------------------------------------------------------
# 10. existing validation authority unchanged (real-repo integration)
# ---------------------------------------------------------------------------


def test_real_repo_all_seven_registered_strategies_represented():
    statuses = derive_all_status()
    strategy_ids = {s.strategy_id for s in statuses}
    expected = {
        "ST_ASIAN_SWEEP_5R_V1",
        "SESSION_TRADE_V1",
        "SMC_3R_V1",
        "ST_LARGE_SMC_V1",
        "ST_LIQUIDITY_SWEEP_RETEST_V1",
        "ST_SESSION_SWEEP_CONTINUATION_V1",
        "R8_OBM_V1",
    }
    assert strategy_ids == expected


def test_real_repo_adapter_backed_strategies_are_not_no_adapter():
    for strategy_id in (
        "ST_ASIAN_SWEEP_5R_V1",
        "ST_LIQUIDITY_SWEEP_RETEST_V1",
        "ST_LARGE_SMC_V1",
        "ST_SESSION_SWEEP_CONTINUATION_V1",
    ):
        status = derive_status(strategy_id)
        assert status.validation_state != "NO_VALIDATION_ADAPTER"
        assert status.demo_authorized is False
        assert status.live_authorized is False


def test_real_repo_demo_authorized_true_only_for_session_trade_v1():
    statuses = {s.strategy_id: s for s in derive_all_status()}
    for strategy_id, status in statuses.items():
        if strategy_id == "SESSION_TRADE_V1":
            assert status.demo_authorized is True
        else:
            assert status.demo_authorized is False
        assert status.live_authorized is False
