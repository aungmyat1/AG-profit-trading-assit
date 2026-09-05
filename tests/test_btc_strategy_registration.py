"""Registry/ledger consistency for ST_LIQUIDITY_SWEEP_RETEST_V1, reconciled in
AG_V1_0_3_BYBIT_QUALIFICATION_EXCEPTION_AND_BTC_DAILY_DECISION_V3 -- same style as
test_large_smc_registration.py. Proves registration presence/authority WITHOUT proving
generic Strategy Manager dispatch (none is claimed or required here)."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_st_liquidity_sweep_retest_v1_registered_research_only():
    registry = yaml.safe_load((ROOT / "strategies/registry.yaml").read_text(encoding="utf-8"))
    entry = registry["strategies"]["ST_LIQUIDITY_SWEEP_RETEST_V1"]

    assert entry["registered"] is True
    assert entry["research"] is True
    assert entry["demo_authorized"] is False
    assert entry["live_authorized"] is False
    assert entry["config_source"] == "strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml"
    # Registry preserves its existing schema exactly -- no unsupported fields added.
    allowed_fields = {"registered", "active", "research", "demo_authorized", "live_authorized",
                      "config_source", "engine", "note"}
    assert set(entry.keys()) <= allowed_fields


def test_registry_and_ledger_identity_agree():
    registry = yaml.safe_load((ROOT / "strategies/registry.yaml").read_text(encoding="utf-8"))
    strategy_yaml = yaml.safe_load((ROOT / "strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml").read_text(encoding="utf-8"))
    ledger_text = (ROOT / "strategies/STRATEGY_LEDGER.md").read_text(encoding="utf-8")

    entry = registry["strategies"]["ST_LIQUIDITY_SWEEP_RETEST_V1"]
    assert entry["config_source"] == "strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml"
    assert "ST_LIQUIDITY_SWEEP_RETEST_V1" in ledger_text
    assert "ACTIVE_INCUBATION (v2.0.0)" in ledger_text
    # Strategy YAML, ledger, and registry all agree on identity/version/status.
    assert strategy_yaml["version"] == "2.0.0"
    assert strategy_yaml["status"] == "ACTIVE_INCUBATION"
    profile_ids = {p["profile_id"] for p in strategy_yaml["profiles"]}
    assert {"FOREX", "CRYPTO_PERP"} <= profile_ids


def test_no_execution_authority_granted_by_registration():
    registry = yaml.safe_load((ROOT / "strategies/registry.yaml").read_text(encoding="utf-8"))
    entry = registry["strategies"]["ST_LIQUIDITY_SWEEP_RETEST_V1"]
    assert entry["demo_authorized"] is False
    assert entry["live_authorized"] is False
    assert "RESEARCH_ONLY" in entry["engine"]


def test_generic_strategy_manager_dispatch_not_claimed():
    """Registry presence alone does not imply a generic Strategy Manager runtime exists
    -- registry.yaml's own header comment already documents that nothing in this repo
    currently calls a strategy-manager runtime; this test only pins that this milestone
    did not silently start claiming otherwise."""
    registry_text = (ROOT / "strategies/registry.yaml").read_text(encoding="utf-8")
    assert "nothing in this repo currently" in registry_text or "no running orchestrator" in registry_text.lower() \
        or "distinct from EXECUTION PERMISSION" in registry_text
