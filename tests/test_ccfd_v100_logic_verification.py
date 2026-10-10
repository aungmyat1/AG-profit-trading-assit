"""Verify fail-closed evidence, policy boundaries and recorded/synthetic separation."""
import copy
import csv
import datetime as dt
import importlib.util
import json
from pathlib import Path

import pytest

from strategy_engine.session import Candle
from v1_tickets.ccfd_logic_gate import verify_case
from v1_tickets.crypto_cfd_policy import load_ticket_policy
from v1_tickets.manual_ticket import crypto_cfd_cost_gate

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ccfd_runner", ROOT / "scripts/ccfd_v100_logic_verification.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def inputs():
    case = json.loads(runner.DEFAULT.read_text())["cases"][0]
    candles = {}
    for tf, rel in case["paths"].items():
        with (runner.DEFAULT.parent / rel).open() as stream:
            candles[tf] = [Candle(dt.datetime.fromisoformat(r["timestamp_utc"]),
                                 *(float(r[k]) for k in ("open", "high", "low", "close")))
                           for r in csv.DictReader(stream)]
    return case, candles


def test_synthetic_all_gates_and_both_sides_windows():
    report = runner.run(runner.DEFAULT)
    assert report["verdict"] == "SYNTHETIC_ONLY"
    assert set(report["gates"].values()) == {"PASS"}
    assert report["uncovered_cases"] == []
    assert report["NO_BROKER_MUTATION"] and report["ORDER_API_CALLS"] == 0
    assert report["logic_identity"]["contract_hash"] and report["logic_identity"]["engine_identity"]


def test_relabelled_synthetic_never_verified(tmp_path):
    data = json.loads(runner.DEFAULT.read_text())
    data.update(source="MT5_VT_MARKETS_DEMO", mission="AGP-DATA-R2")
    for case in data["cases"]:
        case["paths"] = {tf: str(runner.DEFAULT.parent / rel) for tf, rel in case["paths"].items()}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data))
    # Manifest paths must be relative, matching the documented DATA-R2 rerun interface.
    for case in data["cases"]:
        for tf, rel in case["paths"].items():
            target = tmp_path / Path(rel).name
            target.write_bytes(Path(rel).read_bytes())
            case["paths"][tf] = target.name
    path.write_text(json.dumps(data))
    with pytest.raises(runner.ManifestRejected):  # no provenance sha256s at all
        runner.run(path)
    # Even with complete provenance hashes, synthetic bytes never become recorded evidence.
    _add_provenance(tmp_path, data)
    path.write_text(json.dumps(data))
    report = runner.run(path)
    assert report["verdict"] == "NOT_VERIFIED"
    assert not report["provenance_hashes_valid"]


def _add_provenance(base, data):
    import hashlib
    for case in data["cases"]:
        name = f"{case['id']}_provenance.json"
        (base / name).write_text(json.dumps({
            "source": "MT5_VT_MARKETS_DEMO", "mission": "AGP-DATA-R2", "symbol": case["symbol"],
            "recorded": True, "captured_at_utc": "2026-10-10T00:00:00+00:00",
            "sha256": {tf: hashlib.sha256((base / rel).read_bytes()).hexdigest()
                       for tf, rel in case["paths"].items()}}))
        case["provenance"] = name


def _copy_synthetic(tmp_path, **manifest_over):
    data = json.loads(runner.DEFAULT.read_text())
    data.update(manifest_over)
    for case in data["cases"]:
        for tf, rel in case["paths"].items():
            (tmp_path / Path(rel).name).write_bytes((runner.DEFAULT.parent / rel).read_bytes())
            case["paths"][tf] = Path(rel).name
    return data


@pytest.mark.parametrize("drop", ["file", "m5", "all", "short"])
def test_recorded_manifest_missing_provenance_sha256_is_rejected(tmp_path, drop, capsys, monkeypatch):
    data = _copy_synthetic(tmp_path, source="RECORDED", mission="AGP-DATA-R2")
    _add_provenance(tmp_path, data)
    prov = tmp_path / data["cases"][0]["provenance"]
    record = json.loads(prov.read_text())
    if drop == "file":
        prov.unlink()
    elif drop == "all":
        del record["sha256"]
    elif drop == "short":
        record["sha256"]["d1"] = "abc"
    else:
        del record["sha256"][drop]
    if drop != "file":
        prov.write_text(json.dumps(record))
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data))
    with pytest.raises(runner.ManifestRejected, match="provenance"):
        runner.run(path)
    monkeypatch.setattr("sys.argv", ["x", "--fixtures", str(path), "--out-dir", str(tmp_path / "out")])
    assert runner.main() == 2 and "REJECTED" in capsys.readouterr().out


def test_null_expected_result_is_conformance_only(tmp_path):
    data = _copy_synthetic(tmp_path)
    for case in data["cases"]:
        case["expected_result"] = None
        case["expected_direction"] = None
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data))
    report = runner.run(path)
    assert report["conformance_only_cases"] == len(data["cases"])
    assert set(report["gates"].values()) == {"PASS"}  # L1-L6 still run, no expected-answer failure
    for row in report["cases"]:
        assert row["mode"] == "CONFORMANCE_ONLY"
        assert not {"expected_result", "direction"} & {c["rule"] for c in row["gates"]["L2"]["checks"]}
        assert {"contract_binding", "production_structure"} <= {c["rule"] for c in row["gates"]["L2"]["checks"]}
    # No asserted answer, so no coverage claim.
    assert len(report["uncovered_cases"]) == 8


def test_wrong_expected_result_still_fails_l2():
    case, candles = inputs()
    case = {**case, "expected_result": "WAITING_SWEEP"}
    raw = verify_case(case, candles, load_ticket_policy())
    row = {"result": raw["result"], "gates": raw["gates"]}
    runner._classify(case, row)
    assert row["mode"] == "EXPECTED_ANSWER" and row["gates"]["L2"]["status"] == "FAIL"


def test_reference_incomplete_is_data_coverage_gap_not_l2_failure():
    case, candles = inputs()
    cut = dt.datetime.fromisoformat(case["now"]).replace(hour=0, minute=0, second=0, microsecond=0)
    # Drop one previous-day M5 bar: the reference grid is incomplete.
    victim = next(c for c in candles["m5"] if cut - dt.timedelta(hours=12) <= c.time < cut)
    candles = {**candles, "m5": [c for c in candles["m5"] if c is not victim]}
    case = {**case, "expected_result": "ENTRY_VALID"}
    raw = verify_case(case, candles, load_ticket_policy())
    assert raw["result"]["result"] == "REFERENCE_INCOMPLETE"
    row = {"result": raw["result"], "gates": raw["gates"]}
    runner._classify(case, row)
    assert row["data_coverage_gap"] is True
    assert row["gates"]["L2"]["status"] == "PASS"
    assert row["gates"]["L3"]["status"] == "PASS"
    grid = next(c for c in row["gates"]["L3"]["checks"] if c["rule"] == "reference_grid")
    assert grid["verdict"] == runner.DATA_COVERAGE_GAP


@pytest.mark.parametrize("key", ["risk_pct", "cost_warn_R", "cost_block_R", "spread_ok_pct", "spread_block_pct"])
def test_cost_gate_missing_key_blocks(key):
    policy = load_ticket_policy()
    del policy[key]
    blocks, *_ = crypto_cfd_cost_gate(100, 1, 0, policy)
    assert blocks


@pytest.mark.parametrize("spread,commission,block,warn", [
    (10, 0, [], ["COST_WARN"]), (10.01, 0, [], ["SPREAD_WARN", "COST_WARN"]),
    (20, 0, [], ["SPREAD_WARN", "COST_WARN"]),
    (20.01, 0, ["SPREAD_TOO_WIDE"], ["COST_WARN"]),
    (1, 0.24, ["COST_TOO_HIGH"], []),
])
def test_friction_boundary(spread, commission, block, warn):
    got_block, got_warn, *_ = crypto_cfd_cost_gate(100, spread, commission, load_ticket_policy())
    assert (got_block, got_warn) == (block, warn)


@pytest.mark.parametrize("mutation,gate", [
    ("missing_reference", "L3"), ("future_bar", "L3"),
    ("stale_quote", "L5"), ("expired_signal", "L6"), ("wrong_expected_direction", "L2"),
])
def test_fixture_rejections(mutation, gate):
    case, candles = inputs()
    if mutation == "missing_reference":
        candles["m5"].pop(0)
    elif mutation == "future_bar":
        candles["m5"].append(Candle(dt.datetime.fromisoformat(case["now"]), 1, 2, 0.5, 1))
    elif mutation == "stale_quote":
        case["quote_time"] = (dt.datetime.fromisoformat(case["now"]) - dt.timedelta(minutes=16)).isoformat()
    elif mutation == "expired_signal":
        case["now"] = (dt.datetime.fromisoformat(case["now"]) + dt.timedelta(minutes=16)).isoformat()
    else:
        case["expected_direction"] = "SHORT"
    report = verify_case(case, candles, load_ticket_policy())
    assert report["gates"][gate]["status"] == "FAIL"


def test_geometry_corruption_is_detected(monkeypatch):
    from crypto_cfd_contract import rules
    original = rules.evaluate
    def corrupt(*args, **kwargs):
        result = copy.deepcopy(original(*args, **kwargs))
        if result["result"] == "ENTRY_VALID":
            p = result["evidence"]["target_plan"]
            p["stop_loss"] = p["entry"] + p["risk_distance"]
        return result
    monkeypatch.setattr(rules, "evaluate", corrupt)
    case, candles = inputs()
    result = verify_case(case, candles, load_ticket_policy())
    assert result["gates"]["L2"]["status"] == result["gates"]["L4"]["status"] == "FAIL"
