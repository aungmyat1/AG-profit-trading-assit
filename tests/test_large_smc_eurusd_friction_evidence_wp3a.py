"""Tests for WP3A -- Large SMC EURUSD friction-policy empirical evidence collection.
Covers fx_friction_research.spread_evidence (read-only, offline-testable via
monkeypatch, no live terminal required) and the resulting friction_policy_contract.json
update. See docs/status/AG_LARGE_SMC_EURUSD_FRICTION_EVIDENCE_WP3A_STATUS.md."""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONTRACTS_DIR = os.path.join(
    REPO_ROOT, "artifacts", "validation", "ST_LARGE_SMC_V1", "EURUSD_ADMISSION_CONTRACTS",
)
SPREAD_EVIDENCE_MODULE = os.path.join(REPO_ROOT, "src", "fx_friction_research", "spread_evidence.py")

sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from fx_friction_research.spread_evidence import (  # noqa: E402
    SpreadObservation,
    capture_observation,
    raw_observations_hash,
    summarize,
)
from mt5.connection import MT5ConnectionError  # noqa: E402

# WP2's frozen commit -- the baseline this WP3A mission must not disturb.
WP2_COMMIT_SHA = "7581c42"


def _load_contract(filename):
    with open(os.path.join(CONTRACTS_DIR, filename), encoding="utf-8") as fh:
        return json.load(fh)


def _sample_observations():
    return [
        SpreadObservation("2026-09-15T20:00:00+00:00", "EURUSD", 1.15388, 1.15401, 0.00013, 1.3, "VantageMarkets-Demo"),
        SpreadObservation("2026-09-15T20:00:05+00:00", "EURUSD", 1.15387, 1.15401, 0.00014, 1.4, "VantageMarkets-Demo"),
        SpreadObservation("2026-09-15T20:00:10+00:00", "EURUSD", 1.15388, 1.15401, 0.00013, 1.3, "VantageMarkets-Demo"),
    ]


def test_collector_module_never_references_order_placement():
    """Static AST scan, same technique as
    tests/test_research_external_containment.py -- no order_send/order_check/
    execution.*/management_gateway name anywhere in the collector module."""
    with open(SPREAD_EVIDENCE_MODULE, encoding="utf-8") as fh:
        source = fh.read()
    tree = ast.parse(source)
    forbidden_names = {"order_send", "order_check", "mt5_gateway", "management_gateway"}
    used_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    used_attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    imported_modules = {
        alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    } | {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not (forbidden_names & used_names)
    assert not (forbidden_names & used_attrs)
    assert not any(m and m.startswith("execution") for m in imported_modules)


def test_missing_mt5_connection_fails_closed(monkeypatch):
    monkeypatch.setattr("fx_friction_research.spread_evidence.is_connected", lambda: False)
    with pytest.raises(MT5ConnectionError):
        capture_observation("EURUSD", 0.0001)


def test_spread_conversion_is_correct(monkeypatch):
    class FakeTick:
        time_utc = __import__("datetime").datetime(2026, 9, 15, 20, 0, 0, tzinfo=__import__("datetime").timezone.utc)
        bid = 1.15388
        ask = 1.15401

    class FakeAccount:
        server = "VantageMarkets-Demo"

    monkeypatch.setattr("fx_friction_research.spread_evidence.is_connected", lambda: True)
    monkeypatch.setattr("fx_friction_research.spread_evidence.get_tick", lambda symbol: FakeTick())
    monkeypatch.setattr("fx_friction_research.spread_evidence._mt5_account", lambda: FakeAccount())

    observation = capture_observation("EURUSD", 0.0001)
    assert observation.spread_price == pytest.approx(0.00013)
    assert observation.spread_pips == pytest.approx(1.3)
    assert observation.broker_server == "VantageMarkets-Demo"
    assert observation.source == "MT5_LIVE_TICK"


def test_summary_is_reproducible_and_order_independent():
    observations = _sample_observations()
    summary_a = summarize(observations)
    summary_b = summarize(list(reversed(observations)))
    assert summary_a == summary_b
    assert summary_a["sample_count"] == 3
    assert summary_a["minimum_pips"] == pytest.approx(1.3)
    assert summary_a["maximum_pips"] == pytest.approx(1.4)


def test_summary_rejects_empty_input():
    with pytest.raises(ValueError):
        summarize([])


def test_raw_observations_hash_is_deterministic_and_order_independent():
    observations = _sample_observations()
    hash_a = raw_observations_hash(observations)
    hash_b = raw_observations_hash(list(reversed(observations)))
    assert hash_a == hash_b

    mutated = _sample_observations()
    mutated[0] = SpreadObservation(
        mutated[0].timestamp_utc, mutated[0].symbol, mutated[0].bid, 9.99999,
        mutated[0].spread_price, mutated[0].spread_pips, mutated[0].broker_server,
    )
    assert raw_observations_hash(mutated) != hash_a


def test_friction_policy_commission_absence_remains_absence():
    """Adversarial: real EURUSD deal history for this account could not be retrieved
    (see status doc) -- commission must stay UNAVAILABLE/ASSUMED, never silently
    upgraded to BROKER_SPECIFIED/EMPIRICALLY_OBSERVED from a different symbol's data."""
    contract = _load_contract("friction_policy_contract.json")
    commission = contract["cost_components"]["commission_pips"]
    assert commission["classification"] in ("UNAVAILABLE", "ASSUMED")
    assert commission["classification"] not in ("BROKER_SPECIFIED", "EMPIRICALLY_OBSERVED", "OBSERVED")


def test_friction_policy_slippage_absence_remains_absence():
    """Adversarial: exactly one real EURUSD fill in the journal carries a computed
    slippage_points value -- n=1 is not a distribution, so slippage must stay
    UNAVAILABLE/ASSUMED, never EMPIRICALLY_OBSERVED from a single data point."""
    contract = _load_contract("friction_policy_contract.json")
    slippage = contract["cost_components"]["slippage_pips"]
    assert slippage["classification"] in ("UNAVAILABLE", "ASSUMED")
    assert slippage["classification"] != "EMPIRICALLY_OBSERVED"


def test_friction_policy_still_proposed_not_self_signed():
    contract = _load_contract("friction_policy_contract.json")
    assert contract["status"] == "PROPOSED"
    assert contract["owner_signature"] == "REQUIRED"


def test_friction_policy_stop_relationship_requires_owner_adjudication():
    contract = _load_contract("friction_policy_contract.json")
    relationship = contract["minimum_stop_friction_relationship"]
    assert relationship["status"] in ("UNRESOLVED", "OWNER_ADJUDICATION_REQUIRED")


def test_admission_still_blocked_on_same_three_reasons():
    """Adversarial: updating the friction contract's evidence fields must not change
    VALIDATION_ADMISSION's outcome for EURUSD -- status is still PROPOSED, so
    friction_policy_ref stays None and the same three reasons still block."""
    from onboard_large_smc_eurusd_admission_wp2 import build_large_smc_eurusd_profile_v2
    from validation_framework.validation_admission import (
        REASON_MISSING_FRICTION_POLICY,
        REASON_MISSING_HOLDOUT_BOUNDARY,
        REASON_MISSING_VALIDATION_POLICY,
        run_validation_admission,
    )

    profile = build_large_smc_eurusd_profile_v2()
    result = run_validation_admission(profile, symbol="EURUSD")
    assert set(result.reason_codes) == {
        REASON_MISSING_FRICTION_POLICY, REASON_MISSING_VALIDATION_POLICY, REASON_MISSING_HOLDOUT_BOUNDARY,
    }


def test_execution_authority_unchanged():
    from onboard_large_smc_eurusd_admission_wp2 import build_large_smc_eurusd_profile_v2

    profile = build_large_smc_eurusd_profile_v2()
    assert profile.execution_authority_metadata == {
        "demo_authorized": False, "live_authorized": False, "proposal_generation_authorized": False,
    }


def test_strategy_semantics_files_unchanged_by_this_mission():
    diff = subprocess.check_output(
        ["git", "diff", WP2_COMMIT_SHA, "--",
         "strategies/ST_LARGE_SMC_V1.yaml",
         "src/large_smc_research/",
         "src/validation_framework/adapters/large_smc_adapter.py"],
        cwd=REPO_ROOT, text=True,
    )
    assert diff == ""


def test_frozen_validation_core_unchanged_by_this_mission():
    diff = subprocess.check_output(
        ["git", "diff", WP2_COMMIT_SHA, "--",
         "src/validation_framework/ag_validation_methodology.py",
         "src/validation_framework/validation_gate_state.py",
         "src/validation_framework/evidence_reconciliation.py",
         "src/validation_framework/g2_population_identity.py",
         "src/validation_framework/g3_gate.py",
         "src/validation_framework/svos_context_export.py",
         "src/validation_framework/lifecycle_registry.py",
         "src/validation_framework/evaluator.py",
         "src/validation_framework/models.py",
         "src/validation_framework/validation_admission.py",
         "config/governance/strategy_lifecycle.yaml"],
        cwd=REPO_ROOT, text=True,
    )
    assert diff == ""


def test_execution_and_gateway_files_unchanged_by_this_mission():
    """Adversarial: this mission must not touch any order-placement-capable path."""
    diff = subprocess.check_output(
        ["git", "diff", WP2_COMMIT_SHA, "--",
         "src/execution/", "src/mt5/management_gateway.py", "src/mt5/mt5_gateway.py"],
        cwd=REPO_ROOT, text=True,
    )
    assert diff == ""
