"""Scheduled strategy bindings must resolve to registered, hash-pinned contracts."""

import hashlib
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_every_scheduled_task_strategy_is_registered_with_matching_contract_hash():
    registry = yaml.safe_load((ROOT / "strategies/registry.yaml").read_text(encoding="utf-8"))["strategies"]
    install = (ROOT / "scripts/host/install_tasks.ps1").read_text(encoding="utf-8")
    tasks = re.findall(r"\{ Name = '(AG-V1-[^']+)';\s+Mode = '([^']+)'", install)
    assert tasks

    # Resolve identity from the source each scheduled mode actually loads.
    bindings = {
        "fx": ("src/v1_tickets/fx.py", "strategies/ST_ASIAN_SWEEP_5R_V1.yaml"),
        "crypto": ("src/btc_sweep_research/daily_report.py", "strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml"),
        "lsmc": ("src/large_smc_watch/contract.py", "strategies/ST_LARGE_SMC_V1_1_1_0.yaml"),
    }
    for _task_name, mode in tasks:
        source, contract_path = bindings[mode]
        runtime_source = (ROOT / source).read_text(encoding="utf-8")
        if mode == "fx":
            strategy_path = re.search(r"STRATEGY_PATH\s*=\s*[\"']([^\"']+)", runtime_source).group(1)
            contract_path = strategy_path
            contract_data = yaml.safe_load((ROOT / contract_path).read_text(encoding="utf-8"))
            strategy_id, version = contract_data["strategy_id"], str(contract_data["version"])
        else:
            id_match = re.search(r"STRATEGY_ID\s*=\s*[\"']([^\"']+)", runtime_source)
            version_match = re.search(r"STRATEGY_VERSION\s*=\s*[\"']([^\"']+)", runtime_source)
            assert id_match and version_match, f"{source} must declare runtime identity"
            strategy_id, version = id_match.group(1), version_match.group(1)
            contract_data = yaml.safe_load((ROOT / contract_path).read_text(encoding="utf-8"))
            assert contract_data["strategy_id"] == strategy_id and str(contract_data["version"]) == version
        entry = registry[strategy_id]
        version_entry = entry if entry.get("version") == version else entry.get("historical_versions", {}).get(version)
        assert version_entry is not None, f"{strategy_id}@{version} is absent from registry"
        contract = ROOT / contract_path
        assert version_entry["config_source"] == contract_path
        assert hashlib.sha256(contract.read_bytes()).hexdigest() == version_entry["contract_sha256"]


def test_fx_live_s1_path_loads_scoped_candidate_bound_to_registry_identity():
    """fx mode has two bindings: the legacy/replay STRATEGY_PATH (1.1.1, checked above) and the live S1 path
    (daily_evaluator LIVE, GBPUSD x ASIAN_LONDON), which must load the 1.1.2 candidate whose identity matches
    registry candidate_versions["1.1.2"]."""
    import inspect
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from strategy_engine import load_strategy
    from v1_tickets import daily_evaluator
    from v1_tickets import fx as v1_fx
    from v1_tickets.authority import logic_identity

    source = inspect.getsource(daily_evaluator.evaluate_fx_pair)
    assert 'runtime_scope = ticket_source == "LIVE"' in source
    assert '("GBPUSD", "ASIAN_LONDON")' in source
    assert "SCOPED_CANDIDATE_PATH if runtime_scope else STRATEGY_PATH" in source
    assert v1_fx.SCOPED_CANDIDATE_PATH == "strategies/ST_ASIAN_SWEEP_5R_V1_1_1_2.yaml"

    strategy = load_strategy(v1_fx.SCOPED_CANDIDATE_PATH)
    assert (strategy.strategy_id, strategy.version) == ("ST_ASIAN_SWEEP_5R_V1", "1.1.2")

    candidate = yaml.safe_load((ROOT / "strategies/registry.yaml").read_text(encoding="utf-8"))[
        "strategies"]["ST_ASIAN_SWEEP_5R_V1"]["candidate_versions"]["1.1.2"]
    assert candidate["config_source"] == v1_fx.SCOPED_CANDIDATE_PATH
    identity = logic_identity("ST_ASIAN_SWEEP_5R_V1", "1.1.2")
    assert identity["digest"] == candidate["logic_verified_identity"]
    (s1,) = [s for s in candidate["logic_verified_scopes"] if s["scope_id"] == "S1"]
    assert (s1["symbol"], s1["session"], s1["engine_setup"]) == ("GBPUSD", "ASIAN_LONDON", "SWEEP")
    assert s1["config_source"] == v1_fx.SCOPED_CANDIDATE_PATH
    assert s1["contract_hash"] == identity["contract_hash"] and s1["identity_hash"] == identity["digest"]
    assert v1_fx.symbol_scope_verified(strategy.strategy_id, strategy.version, "GBPUSD", "ASIAN_LONDON",
                                       setup="SWEEP", branch="RANGE_SWEEP", contract_path=strategy.source_path)
