"""Tests for WP3A.1 -- the multi-session EURUSD friction evidence campaign
(manifest freeze, fixed-grid collection, missing-sample handling, aggregation, C10
descriptive ratios). See docs/status/AG_LARGE_SMC_EURUSD_FRICTION_CAMPAIGN_WP3A1_STATUS.md."""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CAMPAIGN_DIR = os.path.join(
    REPO_ROOT, "artifacts", "validation", "ST_LARGE_SMC_V1", "EURUSD_ADMISSION_CONTRACTS",
    "friction_campaign_wp3a1",
)

sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from fx_friction_research.spread_evidence import (  # noqa: E402
    MISSING_SOURCE,
    collect_fixed_grid,
    combine_hashes,
    raw_rows_hash,
    summarize_campaign_rows,
)
from fx_friction_research.c10_friction_ratios import C10_MIN_BUFFER_PIPS, friction_to_stop_ratios  # noqa: E402
from mt5.market_data import MarketDataError  # noqa: E402

from _lsmc_frozen_core import assert_large_smc_registry_projection_unchanged

WP3A_COMMIT_SHA = "fe4d526"

SCRIPT_FILES_NO_ORDER_PLACEMENT = (
    "freeze_eurusd_friction_campaign_manifest.py",
    "run_eurusd_friction_campaign_window.py",
    "aggregate_eurusd_friction_campaign.py",
)


def _load_manifest():
    with open(os.path.join(CAMPAIGN_DIR, "campaign_manifest.json"), encoding="utf-8") as fh:
        return json.load(fh)


def test_campaign_manifest_is_frozen_and_hash_matches():
    manifest = _load_manifest()
    with open(os.path.join(CAMPAIGN_DIR, "campaign_manifest_hash.json"), encoding="utf-8") as fh:
        hash_doc = json.load(fh)

    spec = importlib.util.spec_from_file_location(
        "freeze_manifest", os.path.join(REPO_ROOT, "scripts", "freeze_eurusd_friction_campaign_manifest.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    recomputed = module.canonical_hash(manifest)
    assert recomputed == hash_doc["campaign_manifest_hash"]
    assert manifest["frozen_before_collection"] is True
    assert manifest["campaign_id"] == "LSMC_EURUSD_FRICTION_WP3A1_V1"
    assert manifest["required_minimum_population"]["total_minimum_observations"] == 2400


def test_manifest_declares_no_adaptive_or_restart_behavior():
    manifest = _load_manifest()
    rules = manifest["collection_rules"]
    assert rules["adaptive_sampling"] is False
    assert rules["deletion_of_high_spread_samples"] is False
    assert rules["restart_of_unfavorable_windows"] is False


def test_freeze_script_refuses_to_overwrite_existing_manifest():
    """Adversarial: re-running the freeze script against the already-frozen manifest
    must refuse, never silently re-date/re-hash it."""
    result = subprocess.run(
        [sys.executable, os.path.join(REPO_ROOT, "scripts", "freeze_eurusd_friction_campaign_manifest.py")],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "already frozen" in result.stderr or "REFUSING" in result.stderr


def test_collect_fixed_grid_uses_absolute_schedule_not_adaptive_sleep(monkeypatch):
    """A slow capture must not compress the remaining grid -- tick i's target time is
    always start + i*interval, verified via a fake clock that advances unevenly."""
    calls = {"now": 0}
    fake_time = [0.0]

    def now_fn():
        import datetime as dt
        calls["now"] += 1
        return dt.datetime(2026, 9, 20, 5, 30, 0, tzinfo=dt.timezone.utc) + dt.timedelta(seconds=fake_time[0])

    def sleep_fn(seconds):
        fake_time[0] += seconds

    class FakeObservation:
        def __init__(self, ts):
            self.timestamp_utc = ts.isoformat()
            self.symbol = "EURUSD"
            self.bid = 1.1
            self.ask = 1.10013
            self.spread_price = 0.00013
            self.spread_pips = 1.3
            self.broker_server = "VantageMarkets-Demo"
            self.source = "MT5_LIVE_TICK"

    import fx_friction_research.spread_evidence as se

    def fake_capture(symbol, pip_size):
        fake_time[0] += 3.0  # capture itself takes 3s -- must not shrink the 5s grid
        return FakeObservation(now_fn())

    monkeypatch.setattr(se, "capture_observation", fake_capture)
    monkeypatch.setattr(se, "_mt5_account", lambda: type("A", (), {"login": 26088035})())

    rows = collect_fixed_grid(
        "EURUSD", 0.0001, "CAMP1", "WINDOW_A_ASIAN_REFERENCE", sample_count=5, interval_seconds=5.0,
        sleep_fn=sleep_fn, now_fn=now_fn,
    )
    assert len(rows) == 5
    assert all(r["source"] == "MT5_LIVE_TICK" for r in rows)
    # total elapsed must be >= 4 intervals (20s), since capture itself also advances the clock
    assert fake_time[0] >= 20.0


def test_missing_samples_are_recorded_not_dropped(monkeypatch):
    import fx_friction_research.spread_evidence as se

    def flaky_capture(symbol, pip_size):
        raise MarketDataError("DATA_MISSING", "no live quote")

    monkeypatch.setattr(se, "capture_observation", flaky_capture)

    rows = collect_fixed_grid(
        "EURUSD", 0.0001, "CAMP1", "WINDOW_A_ASIAN_REFERENCE", sample_count=3, interval_seconds=0.0,
        sleep_fn=lambda s: None,
    )
    assert len(rows) == 3
    assert all(r["source"] == MISSING_SOURCE for r in rows)
    assert all(r["bid"] is None and r["spread_pips"] is None for r in rows)
    assert all(r["missing_reason"] for r in rows)

    summary = summarize_campaign_rows(rows)
    assert summary["sample_count"] == 0
    assert summary["missing_sample_count"] == 3
    assert "median_pips" not in summary


def test_summarize_campaign_rows_reproducible_and_order_independent():
    rows = [
        {"source": "MT5_LIVE_TICK", "spread_pips": 1.3}, {"source": "MT5_LIVE_TICK", "spread_pips": 1.4},
        {"source": MISSING_SOURCE, "spread_pips": None}, {"source": "MT5_LIVE_TICK", "spread_pips": 1.35},
    ]
    a = summarize_campaign_rows(rows)
    b = summarize_campaign_rows(list(reversed(rows)))
    assert a == b
    assert a["sample_count"] == 3
    assert a["missing_sample_count"] == 1


def test_raw_rows_hash_deterministic_and_combine_hash_order_independent():
    rows_window_a = [
        {"window_id": "WINDOW_A_ASIAN_REFERENCE", "timestamp_utc": "2026-09-20T05:30:00+00:00", "v": 1},
        {"window_id": "WINDOW_A_ASIAN_REFERENCE", "timestamp_utc": "2026-09-20T05:30:05+00:00", "v": 2},
    ]
    hash_a = raw_rows_hash(rows_window_a)
    hash_b = raw_rows_hash(list(reversed(rows_window_a)))
    assert hash_a == hash_b

    combined_1 = combine_hashes([hash_a, "deadbeef"])
    combined_2 = combine_hashes(["deadbeef", hash_a])
    assert combined_1 == combined_2

    with pytest.raises(ValueError):
        combine_hashes([])


def test_c10_ratios_are_descriptive_only_and_never_change_c10():
    summary = {"median_pips": 1.3, "p90_pips": 1.4, "p95_pips": 1.4, "p99_pips": 1.4}
    ratios = friction_to_stop_ratios(summary)
    assert ratios["median_pips_to_min_buffer_ratio"] == pytest.approx(1.3 / 1.5)
    assert C10_MIN_BUFFER_PIPS == 1.5  # read-only reference, unchanged from strategies/ST_LARGE_SMC_V1.yaml


def test_commission_absence_remains_absence_wp6():
    with open(os.path.join(
        REPO_ROOT, "artifacts", "validation", "ST_LARGE_SMC_V1", "EURUSD_ADMISSION_CONTRACTS",
        "friction_policy_contract.json",
    ), encoding="utf-8") as fh:
        contract = json.load(fh)
    assert contract["cost_components"]["commission_pips"]["classification"] in ("UNAVAILABLE", "ASSUMED")


def test_slippage_absence_remains_absence_wp7():
    with open(os.path.join(
        REPO_ROOT, "artifacts", "validation", "ST_LARGE_SMC_V1", "EURUSD_ADMISSION_CONTRACTS",
        "friction_policy_contract.json",
    ), encoding="utf-8") as fh:
        contract = json.load(fh)
    assert contract["cost_components"]["slippage_pips"]["classification"] in ("UNAVAILABLE", "ASSUMED")


def test_no_order_placement_names_in_any_new_campaign_script():
    forbidden_names = {"order_send", "order_check", "mt5_gateway", "management_gateway"}
    for filename in SCRIPT_FILES_NO_ORDER_PLACEMENT:
        path = os.path.join(REPO_ROOT, "scripts", filename)
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        used_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        used_attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        imported_modules = {
            alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        } | {
            node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
        }
        assert not (forbidden_names & used_names), filename
        assert not (forbidden_names & used_attrs), filename
        assert not any(m and m.startswith("execution") for m in imported_modules), filename


def test_c10_and_strategy_semantics_unchanged_by_this_mission():
    diff = subprocess.check_output(
        ["git", "diff", WP3A_COMMIT_SHA, "--",
         "strategies/ST_LARGE_SMC_V1.yaml",
         "src/large_smc_research/",
         "src/validation_framework/adapters/large_smc_adapter.py"],
        cwd=REPO_ROOT, text=True,
    )
    assert diff == ""


def test_frozen_validation_core_unchanged_by_this_mission():
    """See tests/_lsmc_frozen_core.py: the shared multi-strategy
    config/governance/strategy_lifecycle.yaml is checked separately, narrowed to
    ST_LARGE_SMC_V1's own registry projection rather than the whole file."""
    diff = subprocess.check_output(
        ["git", "diff", WP3A_COMMIT_SHA, "--",
         "src/validation_framework/ag_validation_methodology.py",
         "src/validation_framework/validation_gate_state.py",
         "src/validation_framework/evidence_reconciliation.py",
         "src/validation_framework/g2_population_identity.py",
         "src/validation_framework/g3_gate.py",
         "src/validation_framework/svos_context_export.py",
         "src/validation_framework/lifecycle_registry.py",
         "src/validation_framework/evaluator.py",
         "src/validation_framework/models.py",
         "src/validation_framework/validation_admission.py"],
        cwd=REPO_ROOT, text=True,
    )
    assert diff == ""
    assert_large_smc_registry_projection_unchanged(REPO_ROOT, WP3A_COMMIT_SHA)


def test_execution_and_gateway_files_unchanged_by_this_mission():
    diff = subprocess.check_output(
        ["git", "diff", WP3A_COMMIT_SHA, "--",
         "src/execution/", "src/mt5/management_gateway.py", "src/mt5/mt5_gateway.py"],
        cwd=REPO_ROOT, text=True,
    )
    assert diff == ""


def test_execution_authority_still_unchanged():
    from onboard_large_smc_eurusd_admission_wp2 import build_large_smc_eurusd_profile_v2

    profile = build_large_smc_eurusd_profile_v2()
    assert profile.execution_authority_metadata == {
        "demo_authorized": False, "live_authorized": False, "proposal_generation_authorized": False,
    }
