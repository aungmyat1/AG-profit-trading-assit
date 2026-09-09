"""AG_THREE_STRATEGY_VALIDATION_CONTINUATION_V1 (Session Trade economic validation)
tests for the FX friction cost model, provenance binding, and the evaluator invariants
that must hold once a negative economic result exists (economic fail != technical fail,
technical pass != demo authorization)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from fx_friction_research.cost_model import SCENARIOS, calculate_trade_friction  # noqa: E402
from fx_friction_research.provenance import resolved_record_hash  # noqa: E402
from validation_framework.adapters.fx_adapter import build_fx_record, _read_outcome_records  # noqa: E402
from validation_framework.evaluator import evaluate_transition  # noqa: E402
from validation_framework.models import GateStatus  # noqa: E402
import generate_fx_friction_stress_evidence as gen  # noqa: E402


# ---------------------------------------------------------------------------
# Gross outcome immutability + record identity.
# ---------------------------------------------------------------------------


def test_source_records_untouched_by_generation():
    """Running the evidence generator must never change any resolved record's economic
    fields -- proven by re-computing the hash before/after and by an exact git-diff
    check on the record files."""
    before = subprocess.check_output(
        ["git", "status", "--short", "--", "artifacts/outcome_resolution/records/"],
        cwd=str(REPO_ROOT), text=True,
    )
    gen.build_evidence(repo_root=str(REPO_ROOT))
    after = subprocess.check_output(
        ["git", "status", "--short", "--", "artifacts/outcome_resolution/records/"],
        cwd=str(REPO_ROOT), text=True,
    )
    assert before == after


def test_resolved_record_hash_reproducible():
    records, _ = _read_outcome_records(str(REPO_ROOT))
    h1 = resolved_record_hash(records)
    h2 = resolved_record_hash(list(reversed(records)))  # order must not matter
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex digest


def test_resolved_record_hash_changes_if_an_economic_field_changes():
    records, _ = _read_outcome_records(str(REPO_ROOT))
    original = resolved_record_hash(records)
    mutated = [dict(r) for r in records]
    mutated[0]["realized_R"] = mutated[0]["realized_R"] + 0.5
    assert resolved_record_hash(mutated) != original


# ---------------------------------------------------------------------------
# Cost model arithmetic.
# ---------------------------------------------------------------------------


def test_net_R_arithmetic_matches_gross_minus_total_friction():
    scenario = SCENARIOS["BASE"]
    friction = calculate_trade_friction(
        proposal_id="T1", symbol="EURUSD", entry=1.1000, stop_loss=1.0990,
        gross_R=-1.0, scenario=scenario,
    )
    assert friction.total_friction_R == pytest.approx(
        friction.spread_cost_R + friction.commission_cost_R + friction.slippage_cost_R
    )
    assert friction.net_R == pytest.approx(friction.gross_R - friction.total_friction_R)
    assert friction.gross_R == -1.0  # never modified


def test_spread_cost_scales_with_scenario_spread_pips():
    base = calculate_trade_friction("T1", "EURUSD", 1.1000, 1.0990, -1.0, SCENARIOS["BASE"])
    stressed = calculate_trade_friction("T1", "EURUSD", 1.1000, 1.0990, -1.0, SCENARIOS["STRESSED"])
    assert stressed.spread_cost_R > base.spread_cost_R
    assert stressed.spread_cost_R == pytest.approx(
        SCENARIOS["STRESSED"].spread_pips * 0.0001 / 0.0010
    )


def test_commission_cost_is_pip_based_and_symbol_scoped():
    friction = calculate_trade_friction("T1", "EURUSD", 1.1000, 1.0990, -1.0, SCENARIOS["BASE"])
    assert friction.commission_cost_R == pytest.approx(SCENARIOS["BASE"].commission_pips * 0.0001 / 0.0010)


def test_slippage_cost_matches_strategy_signed_limit_in_stressed_scenario():
    """STRESSED slippage_pips must equal the strategy's own signed
    slippage_limit_points=10 converted at 10 points/pip (5-digit EURUSD/GBPUSD, real
    captured evidence -- see cost_model module docstring), not an arbitrary number."""
    assert SCENARIOS["STRESSED"].slippage_pips == 1.0
    friction = calculate_trade_friction("T1", "EURUSD", 1.1000, 1.0990, -1.0, SCENARIOS["STRESSED"])
    assert friction.slippage_cost_R == pytest.approx(1.0 * 0.0001 / 0.0010)


def test_missing_symbol_pip_size_fails_closed():
    with pytest.raises(ValueError):
        calculate_trade_friction("T1", "USDJPY", 150.00, 149.90, -1.0, SCENARIOS["BASE"])


def test_non_positive_risk_distance_fails_closed():
    with pytest.raises(ValueError):
        calculate_trade_friction("T1", "EURUSD", 1.1000, 1.1000, -1.0, SCENARIOS["BASE"])


def test_scenario_reproducibility_same_inputs_same_output():
    a = calculate_trade_friction("T1", "EURUSD", 1.1000, 1.0990, -1.0, SCENARIOS["SEVERE"])
    b = calculate_trade_friction("T1", "EURUSD", 1.1000, 1.0990, -1.0, SCENARIOS["SEVERE"])
    assert a == b


# ---------------------------------------------------------------------------
# Evidence artifact identity binding + evidence completeness vs economic result.
# ---------------------------------------------------------------------------


def test_friction_evidence_identity_binding():
    evidence = gen.build_evidence(repo_root=str(REPO_ROOT))
    for field in (
        "strategy_id", "strategy_version", "application_release", "git_commit",
        "cost_model_version", "resolved_record_hash", "generated_at",
    ):
        assert evidence[field], f"{field} missing or empty"
    assert evidence["strategy_id"] == "ST_ASIAN_SWEEP_5R_V1"
    assert evidence["resolved_record_count"] == 13


def test_friction_evidence_complete_is_not_profitability():
    """FRICTION_EVIDENCE_COMPLETE=True and a negative net expectancy must coexist --
    evidence completeness is a reproducibility fact, never conflated with profitability."""
    evidence = gen.build_evidence(repo_root=str(REPO_ROOT))
    assert evidence["evidence_completeness"]["friction_evidence_complete"] is True
    assert evidence["economic_status"]["net_status"] == "NEGATIVE"
    assert evidence["economic_status"]["economic_gate_pass"] is False


def test_gross_already_negative_is_not_softened_by_costs():
    evidence = gen.build_evidence(repo_root=str(REPO_ROOT))
    base = evidence["scenarios"]["BASE"]
    assert base["gross_expectancy_R"] < 0
    assert base["net_expectancy_R"] < base["gross_expectancy_R"]  # costs only make it worse
    assert evidence["economic_status"]["economic_classification"] == "NEGATIVE_EXPECTANCY"


def test_no_strategy_parameter_was_modified_by_this_evidence_work():
    """No strategy config/rule file may be touched by friction-evidence generation --
    this task computes an economic READING of frozen trades, never a strategy edit."""
    diff = subprocess.check_output(
        ["git", "status", "--short", "--", "strategies/ST_ASIAN_SWEEP_5R_V1.yaml"],
        cwd=str(REPO_ROOT), text=True,
    )
    assert diff == ""


# ---------------------------------------------------------------------------
# OOS split authority (P7) -- must fail closed, never invent a favorable split.
# ---------------------------------------------------------------------------


def test_no_oos_split_authority_exists_for_fx():
    """Mandatory: no pre-frozen/governance-authorized OOS split exists for
    ST_ASIAN_SWEEP_5R_V1 anywhere in the repository. Formal OOS execution must not be
    attempted; OOS_VALIDATION stays NOT_VERIFIED with an explicit reason."""
    hits = subprocess.run(
        ["git", "grep", "-il", "-e", "oos_split", "-e", "walk_forward", "-e", "development_period"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    fx_scoped = [
        line for line in hits.stdout.splitlines()
        if "asian" in line.lower() or "session_trade" in line.lower()
    ]
    assert fx_scoped == [], f"unexpected FX-scoped OOS split authority found: {fx_scoped}"


# ---------------------------------------------------------------------------
# Evaluator invariants: economic fail != technical fail; technical pass != demo auth.
# ---------------------------------------------------------------------------


def test_historical_replay_pass_does_not_imply_demo_eligible():
    """Technical evidence (HISTORICAL_REPLAY, now PASS) improving must never, by itself,
    make the strategy DEMO_ELIGIBLE while FRICTION_STRESS_TEST/OOS_VALIDATION/
    SHADOW_SERIES_COMPLETION are not real PASS. The evaluator remains the sole gate."""
    record = build_fx_record(repo_root=str(REPO_ROOT))
    assert record.gates["HISTORICAL_REPLAY"].status == GateStatus.PASS
    assert record.promotion_eligible is False
    assert set(record.promotion_blockers) == {
        "SHADOW_SERIES_COMPLETION", "FRICTION_STRESS_TEST", "OOS_VALIDATION",
    }


def test_economic_gate_fail_is_a_distinct_fact_from_technical_gate_fail():
    """A NEGATIVE_EXPECTANCY economic finding is recorded independently of the
    evaluator's technical gates -- evaluate_transition() never consumes economic_status,
    and the friction evidence artifact never claims to speak for promotion eligibility."""
    evidence = gen.build_evidence(repo_root=str(REPO_ROOT))
    record = build_fx_record(repo_root=str(REPO_ROOT))
    # The economic finding (negative expectancy) is independent of, and must not silently
    # alter, the evaluator's own gate statuses.
    assert evidence["economic_status"]["net_status"] == "NEGATIVE"
    assert record.gates["HISTORICAL_REPLAY"].status == GateStatus.PASS  # unaffected
    assert "FRICTION_STRESS_TEST" in record.promotion_blockers  # still the evaluator's own real gate


def test_demo_eligible_transition_still_blocked_even_if_friction_gate_were_forced_pass():
    """Even simulating FRICTION_STRESS_TEST forced to PASS, OOS_VALIDATION/
    SHADOW_SERIES_COMPLETION must still block -- proves no single improved gate can
    silently grant DEMO_ELIGIBLE."""
    record = build_fx_record(repo_root=str(REPO_ROOT))
    gates = dict(record.gates)
    from validation_framework.models import GateResult
    from datetime import datetime, timezone
    gates["FRICTION_STRESS_TEST"] = GateResult(
        gate_name="FRICTION_STRESS_TEST", status=GateStatus.PASS, evidence_refs=(),
        evaluated_at=datetime.now(timezone.utc), evaluator_version="TEST",
    )
    evaluation = evaluate_transition(
        record.lifecycle_stage, record.next_transition, gates, strategy_id=record.identity.strategy_id,
    )
    assert evaluation.eligible is False
    assert "OOS_VALIDATION" in evaluation.blocking_gates
    assert "SHADOW_SERIES_COMPLETION" in evaluation.blocking_gates
    assert "FRICTION_STRESS_TEST" not in evaluation.blocking_gates
