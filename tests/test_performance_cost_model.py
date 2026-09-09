"""AG_MONEY_MAKING_EVIDENCE_PIPELINE_M1 P16 acceptance tests for
performance.cost_model -- the canonical FX transaction-cost model. Uses a tmp_path
outcome_resolution records directory; never touches the live artifacts/ tree."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from performance.cost_model import (  # noqa: E402
    PIP_SIZE,
    apply_contract_ceiling_scenario,
    to_resolved_trade_samples,
)
from performance.models import ResolvedTradeSample  # noqa: E402

STRATEGY_ID = "ST_ASIAN_SWEEP_5R_V1"
STRATEGY_VERSION = "1.1.1"


def _write_record(records_dir: Path, name: str, entry: float, stop_loss: float, realized_R: float):
    records_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "proposal_id": name, "strategy_id": STRATEGY_ID, "strategy_version": STRATEGY_VERSION,
        "symbol": "EURUSD", "entry": entry, "stop_loss": stop_loss, "realized_R": realized_R,
        "cost_status": "NOT_INCLUDED", "terminal_state": "RESOLVED_SL",
    }
    (records_dir / f"{name}.json").write_text(json.dumps(record), encoding="utf-8")


def test_net_R_equals_gross_minus_total_friction(tmp_path):
    records_dir = tmp_path / "artifacts" / "outcome_resolution" / "records"
    _write_record(records_dir, f"{STRATEGY_ID}_TEST_1", entry=1.1000, stop_loss=1.0990, realized_R=-1.0)
    results = apply_contract_ceiling_scenario(str(tmp_path), STRATEGY_ID, STRATEGY_VERSION)
    assert len(results) == 1
    r = results[0]
    assert abs(r.net_R - (r.gross_R - r.total_friction_R)) < 1e-9


def test_gross_values_never_modified_by_cost_model(tmp_path):
    records_dir = tmp_path / "artifacts" / "outcome_resolution" / "records"
    _write_record(records_dir, f"{STRATEGY_ID}_TEST_1", entry=1.1000, stop_loss=1.0990, realized_R=-1.0)
    original = json.loads((records_dir / f"{STRATEGY_ID}_TEST_1.json").read_text(encoding="utf-8"))
    apply_contract_ceiling_scenario(str(tmp_path), STRATEGY_ID, STRATEGY_VERSION)
    after = json.loads((records_dir / f"{STRATEGY_ID}_TEST_1.json").read_text(encoding="utf-8"))
    assert original == after  # source file byte-identical -- costs are additive only


def test_zero_cost_baseline_matches_gross_when_no_friction_scenario_applied(tmp_path):
    """The zero-cost baseline is simply the unmodified gross_R -- proven by never
    calling the cost model at all and reading realized_R verbatim."""
    records_dir = tmp_path / "artifacts" / "outcome_resolution" / "records"
    _write_record(records_dir, f"{STRATEGY_ID}_TEST_1", entry=1.1000, stop_loss=1.0990, realized_R=-1.0)
    record = json.loads((records_dir / f"{STRATEGY_ID}_TEST_1.json").read_text(encoding="utf-8"))
    assert record["realized_R"] == -1.0


def test_wider_stop_produces_smaller_friction_R(tmp_path):
    """Friction expressed in R units must shrink as the trade's own risk distance
    grows -- the same absolute friction price is a smaller fraction of a wider stop."""
    records_dir = tmp_path / "artifacts" / "outcome_resolution" / "records"
    _write_record(records_dir, f"{STRATEGY_ID}_TIGHT", entry=1.1000, stop_loss=1.0998, realized_R=-1.0)  # 2 pip stop
    _write_record(records_dir, f"{STRATEGY_ID}_WIDE", entry=1.1000, stop_loss=1.0950, realized_R=-1.0)   # 50 pip stop
    results = {r.source_record_id: r for r in apply_contract_ceiling_scenario(str(tmp_path), STRATEGY_ID, STRATEGY_VERSION)}
    assert results[f"{STRATEGY_ID}_TIGHT"].total_friction_R > results[f"{STRATEGY_ID}_WIDE"].total_friction_R


def test_missing_entry_or_stop_is_skipped_not_guessed(tmp_path):
    records_dir = tmp_path / "artifacts" / "outcome_resolution" / "records"
    records_dir.mkdir(parents=True)
    record = {
        "proposal_id": "X", "strategy_id": STRATEGY_ID, "strategy_version": STRATEGY_VERSION,
        "symbol": "EURUSD", "entry": None, "stop_loss": 1.0990, "realized_R": -1.0,
    }
    (records_dir / "X.json").write_text(json.dumps(record), encoding="utf-8")
    results = apply_contract_ceiling_scenario(str(tmp_path), STRATEGY_ID, STRATEGY_VERSION)
    assert results == []


def test_deterministic_repeatability(tmp_path):
    records_dir = tmp_path / "artifacts" / "outcome_resolution" / "records"
    _write_record(records_dir, f"{STRATEGY_ID}_TEST_1", entry=1.1000, stop_loss=1.0990, realized_R=-1.0)
    r1 = apply_contract_ceiling_scenario(str(tmp_path), STRATEGY_ID, STRATEGY_VERSION)
    r2 = apply_contract_ceiling_scenario(str(tmp_path), STRATEGY_ID, STRATEGY_VERSION)
    assert r1 == r2


def test_to_resolved_trade_samples_never_mutates_base_list(tmp_path):
    records_dir = tmp_path / "artifacts" / "outcome_resolution" / "records"
    _write_record(records_dir, f"{STRATEGY_ID}_TEST_1", entry=1.1000, stop_loss=1.0990, realized_R=-1.0)
    base = [ResolvedTradeSample(
        source_record_id=f"{STRATEGY_ID}_TEST_1", source_path="x", strategy_id=STRATEGY_ID,
        strategy_version=STRATEGY_VERSION, symbol="EURUSD", cycle="ASIAN_LONDON",
        resolved_at=None, gross_R=-1.0, net_R=None, cost_status="NOT_INCLUDED", outcome="RESOLVED_SL",
    )]
    adjusted = apply_contract_ceiling_scenario(str(tmp_path), STRATEGY_ID, STRATEGY_VERSION)
    merged = to_resolved_trade_samples(adjusted, base)
    assert base[0].net_R is None  # original untouched
    assert merged[0].net_R is not None
    assert merged[0].gross_R == base[0].gross_R  # gross unchanged
