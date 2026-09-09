"""AG_MONEY_MAKING_EVIDENCE_PIPELINE_M1 P5-P14 -- read-only economic evidence report.

Produces a machine-readable economic verdict per strategy WITHOUT promotion authority
(P11: "a machine-readable economic verdict without promotion authority"). Reuses:

    performance.adapters.fx_adapter.load_fx_resolved_samples  (existing, unmodified)
    performance.cost_model.apply_contract_ceiling_scenario     (this milestone, additive)
    performance.calculator.compute_trade_metrics                (existing, unmodified)
    validation_framework.adapters.{fx,btc,large_smc}_adapter    (existing, unmodified --
        used only to read OOS_VALIDATION gate status, never to promote or mutate)

Never writes to any evidence file, never changes a lifecycle stage, never authorizes
Demo/Live execution, never places an order. Safe to run any number of times; this is a
report generator, not a scheduled job (P15: this milestone does not add scheduling).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from performance.adapters.fx_adapter import load_fx_resolved_samples  # noqa: E402
from performance.calculator import compute_trade_metrics  # noqa: E402
from performance.cost_model import apply_contract_ceiling_scenario, to_resolved_trade_samples  # noqa: E402
from validation_framework.adapters.btc_adapter import build_btc_record  # noqa: E402
from validation_framework.adapters.fx_adapter import build_fx_record  # noqa: E402
from validation_framework.adapters.large_smc_adapter import build_large_smc_record  # noqa: E402

MIN_SAMPLE_FOR_ANY_CLAIM = 30  # a repository-neutral statistical floor (not a governance
# threshold -- no repo/owner-signed minimum-sample-size figure was found; this number
# only gates whether descriptive metrics are reported as INSUFFICIENT_SAMPLE, never
# whether a strategy passes or fails an economic gate, which remains
# ECONOMIC_GATE_THRESHOLD_UNDEFINED regardless of sample size


def _economic_status(net_expectancy, sample_size, friction_evidence_complete: bool) -> str:
    if sample_size == 0:
        return "INSUFFICIENT_EVIDENCE"
    if not friction_evidence_complete:
        return "FRICTION_SENSITIVE"  # gross may look fine, but cost treatment is incomplete
    if isinstance(net_expectancy, str):  # NOT_EVALUATED
        return "INSUFFICIENT_EVIDENCE"
    if net_expectancy < 0:
        return "NEGATIVE_EXPECTANCY"
    if sample_size < MIN_SAMPLE_FOR_ANY_CLAIM:
        return "PROMISING_BUT_UNPROVEN"
    return "PROMISING_BUT_UNPROVEN"  # ECONOMIC_GATE_PASS never auto-assigned -- no signed threshold exists (P11)


def _kill_continue_advisory(economic_status: str, sample_size: int) -> str:
    if economic_status == "INSUFFICIENT_EVIDENCE":
        return "INSUFFICIENT_SAMPLE"
    if economic_status == "NEGATIVE_EXPECTANCY" and sample_size >= 10:
        return "PAUSE_FOR_RESEARCH"
    if economic_status in ("NEGATIVE_EXPECTANCY", "FRICTION_SENSITIVE"):
        return "CONTINUE_EVIDENCE_COLLECTION"
    return "CONTINUE_EVIDENCE_COLLECTION"


def session_trade_report() -> dict:
    base_samples = load_fx_resolved_samples(".")
    adjusted = apply_contract_ceiling_scenario(".")
    merged = to_resolved_trade_samples(adjusted, base_samples)

    gross_metrics = compute_trade_metrics(base_samples)
    net_metrics = compute_trade_metrics(merged)
    validation_record = build_fx_record(".")
    oos_gate = validation_record.gates.get("OOS_VALIDATION")

    friction_evidence_complete = len(adjusted) == len(base_samples) and len(base_samples) > 0
    economic_status = _economic_status(
        net_metrics.net_expectancy_R, gross_metrics.sample_size, friction_evidence_complete,
    )
    return {
        "strategy": "ST_ASIAN_SWEEP_5R_V1",
        "lifecycle_stage": validation_record.lifecycle_stage.value,
        "resolved_trade_count": gross_metrics.sample_size,
        "gross_metrics": gross_metrics.__dict__,
        "net_metrics_contract_ceiling_scenario": net_metrics.__dict__,
        "friction_evidence_complete": friction_evidence_complete,
        "friction_scenario_used": "CONTRACT_CEILING (only evidence-backed scenario; BASE/SEVERE unavailable -- no signed typical/tail assumption exists)",
        "economic_gate_threshold": "ECONOMIC_GATE_THRESHOLD_UNDEFINED",
        "economic_gate_pass": "ECONOMIC_GATE_THRESHOLD_UNDEFINED",
        "oos_status": oos_gate.status.value if oos_gate else "NOT_VERIFIED",
        "economic_status": economic_status,
        "kill_continue_advisory": _kill_continue_advisory(economic_status, gross_metrics.sample_size),
        "sample_sufficiency": "INSUFFICIENT_SAMPLE" if gross_metrics.sample_size < MIN_SAMPLE_FOR_ANY_CLAIM else "SAMPLE_ADEQUATE_FOR_DESCRIPTIVE_METRICS_ONLY",
    }


def large_smc_report() -> dict:
    validation_record = build_large_smc_record(".")
    oos_gate = validation_record.gates.get("OOS_VALIDATION")
    return {
        "strategy": "ST_LARGE_SMC_V1",
        "lifecycle_stage": validation_record.lifecycle_stage.value,
        "resolved_trade_count": 0,
        "gross_metrics": "N/A -- proposal_generation_authorized=false, no trade has ever been placed or resolvable",
        "net_metrics_contract_ceiling_scenario": "N/A",
        "friction_evidence_complete": False,
        "friction_scenario_used": "NOT_APPLICABLE -- no resolved trades exist",
        "economic_gate_threshold": "ECONOMIC_GATE_THRESHOLD_UNDEFINED",
        "economic_gate_pass": "ECONOMIC_GATE_THRESHOLD_UNDEFINED",
        "oos_status": oos_gate.status.value if oos_gate else "NOT_VERIFIED",
        "economic_status": "INSUFFICIENT_EVIDENCE",
        "kill_continue_advisory": "CONTINUE_EVIDENCE_COLLECTION" if False else "INSUFFICIENT_SAMPLE",
        "sample_sufficiency": "INSUFFICIENT_SAMPLE",
    }


def crypto_report() -> dict:
    validation_record = build_btc_record(".")
    oos_gate = validation_record.gates.get("OOS_VALIDATION")
    campaign = validation_record.gates["NATURAL_CAMPAIGN_ACCRUAL"].details
    return {
        "strategy": "ST_LIQUIDITY_SWEEP_RETEST_V1",
        "lifecycle_stage": validation_record.lifecycle_stage.value,
        "resolved_trade_count": 0,
        "gross_metrics": "N/A -- research-only, no execution, no resolvable trade exists",
        "net_metrics_contract_ceiling_scenario": "N/A",
        "friction_evidence_complete": False,
        "friction_scenario_used": "NOT_APPLICABLE -- no resolved trades exist (cost model exists at src/btc_sweep_research/costs.py but has never been applied to a resolved outcome, since none exists)",
        "economic_gate_threshold": "ECONOMIC_GATE_THRESHOLD_UNDEFINED",
        "economic_gate_pass": "ECONOMIC_GATE_THRESHOLD_UNDEFINED",
        "oos_status": oos_gate.status.value if oos_gate else "NOT_VERIFIED",
        "economic_status": "INSUFFICIENT_EVIDENCE",
        "kill_continue_advisory": "INSUFFICIENT_SAMPLE",
        "sample_sufficiency": "INSUFFICIENT_SAMPLE",
        "valid_campaign_days": campaign["valid_campaign_days"],
        "campaign_target": campaign["target_count"],
    }


def build_report() -> dict:
    return {
        "report_id": "AG_MONEY_MAKING_EVIDENCE_PIPELINE_M1_ECONOMIC_REPORT",
        "session_trade": session_trade_report(),
        "large_smc": large_smc_report(),
        "crypto": crypto_report(),
        "authority": "ADVISORY ONLY -- no lifecycle promotion, no authorization change, no order submitted",
    }


if __name__ == "__main__":
    print(json.dumps(build_report(), indent=2, default=str))
