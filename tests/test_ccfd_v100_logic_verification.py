"""Verify fail-closed evidence, policy boundaries and recorded/synthetic separation."""
import copy
import csv
import datetime as dt
import importlib.util
import json
from pathlib import Path

import pytest

from v1_tickets.ccfd_logic_gate import verify_case
from v1_tickets.crypto_cfd_policy import load_ticket_policy
from v1_tickets.manual_ticket import crypto_cfd_cost_gate
from strategy_engine.session import Candle

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
    with pytest.raises(ValueError, match="missing provenance sha256s"):
        runner.run(path)


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
    assert report["gates"][gate]["status"] == ("NOT_EVIDENCED" if mutation == "missing_reference" else "FAIL")


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


def test_null_expected_answer_is_conformance_only():
    case, candles = inputs()
    case.update(expected_result=None, expected_direction=None)
    row = verify_case(case, candles, load_ticket_policy())
    assert set(row['gates']) == {'L1', 'L2', 'L3', 'L4', 'L5', 'L6'}
    assert set(g['status'] for g in row['gates'].values()) == {'PASS'}
    assert row['gates']['L2']['mode'] == 'CONFORMANCE_ONLY'
    assert not {'L2.expected_result', 'L2.direction'} & {c['id'] for c in row['gates']['L2']['checks']}


@pytest.mark.parametrize('source', ['RECORDED', 'MT5_VT_MARKETS_DEMO'])
def test_recorded_missing_provenance_hashes_rejected(tmp_path, source):
    data = json.loads(runner.DEFAULT.read_text())
    data.update(source=source, mission='AGP-DATA-R2')
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='missing provenance sha256s'):
        runner.run(path)


def test_reference_incomplete_is_data_coverage_gap():
    case, candles = inputs()
    case['expected_result'] = None
    candles['m5'] = candles['m5'][1:]
    row = verify_case(case, candles, load_ticket_policy())
    assert row['result']['result'] == 'REFERENCE_INCOMPLETE'
    assert row['gates']['L2']['status'] == 'PASS'
    assert row['gates']['L3']['status'] == 'NOT_EVIDENCED'
    assert row['data_coverage_gaps'] == ['REFERENCE_INCOMPLETE']


def test_recorded_partial_provenance_hash_map_rejected(tmp_path):
    data = json.loads(runner.DEFAULT.read_text())
    data.update(source='RECORDED', mission='AGP-DATA-R2')
    data['cases'] = data['cases'][:1]
    data['cases'][0]['provenance'] = 'provenance.json'
    (tmp_path / 'provenance.json').write_text(json.dumps({'sha256': {'m5': 'a' * 64}}))
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='missing provenance sha256s'):
        runner.run(path)


def test_reference_gap_does_not_mask_invalid_ohlc():
    case, candles = inputs()
    case['expected_result'] = None
    candles['m5'] = candles['m5'][1:]
    bar = candles['m5'][0]
    candles['m5'][0] = Candle(bar.time, bar.open, bar.low - 1, bar.low, bar.close)
    row = verify_case(case, candles, load_ticket_policy())
    assert row['gates']['L3']['status'] == 'FAIL'
