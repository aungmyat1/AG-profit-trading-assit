#!/usr/bin/env python
"""AG_THREE_STRATEGY_VALIDATION_CONTINUATION_V1 -- Session Trade economic validation,
P2-P5. Applies the governed BASE/STRESSED/SEVERE friction cost model
(src/fx_friction_research/cost_model.py) to every real, already-resolved
ST_ASIAN_SWEEP_5R_V1 v1.1.1 outcome record and writes a single, fully provenance-bound
evidence artifact.

Read-only over the resolved outcome records: never modifies realized_R/terminal_state/
entry/stop_loss/tp1/tp2 on any source record (see
tests/test_fx_friction_stress_evidence.py::test_source_records_untouched_by_generation).
Writes only artifacts/outcome_resolution/fx_friction_stress_evidence.json.

This produces FRICTION_EVIDENCE_COMPLETE (an evidence-quality/reproducibility fact), not
an economic verdict -- see the module docstring distinction reproduced in the artifact
itself under `evidence_completeness` vs `economic_status`. Gross performance is already
known to be negative (-13.0R over 13 trades); no assumption here is chosen to improve
that result.

Usage:
    python scripts/generate_fx_friction_stress_evidence.py
"""
from __future__ import annotations

import json
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from fx_friction_research.cost_model import SCENARIOS, calculate_trade_friction  # noqa: E402
from fx_friction_research.provenance import resolved_record_hash  # noqa: E402
from validation_framework.adapters.fx_adapter import (  # noqa: E402
    SEMANTIC_VERSION,
    STRATEGY_ID,
    _read_outcome_records,
)

COST_MODEL_VERSION = "FX_FRICTION_COST_MODEL_V1"
APPLICATION_RELEASE = "AG_TRADE_ASSISTANT_V1_0_3"
OUTPUT_PATH = REPO_ROOT / "artifacts" / "outcome_resolution" / "fx_friction_stress_evidence.json"


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), text=True
        ).strip()
    except Exception:
        return "UNKNOWN"


def _max_drawdown_R(ordered_R: list) -> float:
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in ordered_R:
        cum += r
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
    return round(max_dd, 4)


def _scenario_report(records, scenario) -> dict:
    frictions = [
        calculate_trade_friction(
            proposal_id=r["proposal_id"],
            symbol=r["symbol"],
            entry=r["entry"],
            stop_loss=r["stop_loss"],
            gross_R=r["realized_R"],
            scenario=scenario,
        )
        for r in records
    ]
    gross = [f.gross_R for f in frictions]
    net = [f.net_R for f in frictions]

    gross_profit = sum(r for r in gross if r > 0)
    gross_loss = sum(r for r in gross if r < 0)
    net_profit = sum(r for r in net if r > 0)
    net_loss = sum(r for r in net if r < 0)

    profit_factor_net = (net_profit / abs(net_loss)) if net_loss < 0 else (
        None if net_profit == 0 else float("inf")
    )

    return {
        "scenario": scenario.name,
        "cost_assumptions": {
            "spread_pips": scenario.spread_pips,
            "commission_pips": scenario.commission_pips,
            "slippage_pips": scenario.slippage_pips,
            "total_friction_pips": scenario.total_friction_pips,
            "source": scenario.source,
        },
        "trade_count": len(frictions),
        "gross_R_total": round(sum(gross), 4),
        "net_R_total": round(sum(net), 4),
        "gross_expectancy_R": round(statistics.mean(gross), 4) if gross else None,
        "net_expectancy_R": round(statistics.mean(net), 4) if net else None,
        "profit_factor_net": profit_factor_net,
        "max_drawdown_R": _max_drawdown_R(net),
        "cost_drag_R": round(sum(gross) - sum(net), 4),
        "per_trade": [
            {
                "proposal_id": f.proposal_id,
                "gross_R": round(f.gross_R, 4),
                "spread_cost_R": round(f.spread_cost_R, 4),
                "commission_cost_R": round(f.commission_cost_R, 4),
                "slippage_cost_R": round(f.slippage_cost_R, 4),
                "total_friction_R": round(f.total_friction_R, 4),
                "net_R": round(f.net_R, 4),
            }
            for f in frictions
        ],
    }


def build_evidence(repo_root: str = str(REPO_ROOT)) -> dict:
    records, record_refs = _read_outcome_records(repo_root)
    records = sorted(records, key=lambda r: r["proposal_timestamp"])

    scenario_reports = {name: _scenario_report(records, scenario) for name, scenario in SCENARIOS.items()}

    base = scenario_reports["BASE"]
    all_records_resolved = all(r.get("terminal_state") in
                                {"RESOLVED_SL", "RESOLVED_TP1_BE", "RESOLVED_TP1_TP2", "RESOLVED_SESSION_EXIT"}
                                for r in records)
    evidence_complete = bool(records) and all_records_resolved

    net_status = "NEGATIVE" if base["net_expectancy_R"] is not None and base["net_expectancy_R"] < 0 else "NON_NEGATIVE"
    gross_status = "NEGATIVE" if base["gross_expectancy_R"] is not None and base["gross_expectancy_R"] < 0 else "NON_NEGATIVE"
    # Economic gate never passes on a negative BASE net expectancy -- this is a
    # deliberately conservative, non-optimizable rule, not a judgment call made here.
    economic_gate_pass = evidence_complete and net_status == "NON_NEGATIVE"

    # Classification taxonomy (AG_THREE_STRATEGY_VALIDATION_CONTINUATION_V1 P6). Applied
    # mechanically from the already-computed BASE numbers above -- never chosen to soften
    # a negative result, and never re-derived from a different, more favorable scenario.
    MIN_SAMPLE_FOR_FORMAL_CLASSIFICATION = 20  # matches SHADOW_SERIES_COMPLETION's own target_valid_days
    if not evidence_complete:
        economic_classification = "INSUFFICIENT_EVIDENCE"
    elif gross_status == "NON_NEGATIVE" and net_status == "NEGATIVE":
        # An otherwise non-negative edge that costs alone erode into a loss.
        economic_classification = "FRICTION_SENSITIVE"
    elif net_status == "NEGATIVE":
        # Already negative before costs, and costs make it worse -- unambiguous, not a
        # borderline/friction-driven case. Reported directly, not softened by sample size.
        economic_classification = "NEGATIVE_EXPECTANCY"
    elif len(records) < MIN_SAMPLE_FOR_FORMAL_CLASSIFICATION:
        economic_classification = "PROMISING_BUT_UNPROVEN"
    else:
        economic_classification = "ECONOMIC_GATE_PASS"

    return {
        "schema": "AG_FX_FRICTION_STRESS_EVIDENCE_V1",
        "strategy_id": STRATEGY_ID,
        "strategy_version": SEMANTIC_VERSION,
        "application_release": APPLICATION_RELEASE,
        "git_commit": _git_commit(),
        "cost_model_version": COST_MODEL_VERSION,
        "resolved_record_count": len(records),
        "resolved_record_refs": list(record_refs),
        "resolved_record_hash": resolved_record_hash(records),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evidence_completeness": {
            "friction_evidence_complete": evidence_complete,
            "note": (
                "PASS means every resolved trade received valid cost treatment under all "
                "three scenarios, identity/provenance are bound, and results are "
                "reproducible from resolved_record_hash. It does NOT mean profitable -- "
                "see economic_status below."
            ),
        },
        "economic_status": {
            "gross_status": gross_status,
            "net_status": net_status,
            "economic_gate_pass": economic_gate_pass,
            "economic_classification": economic_classification,
        },
        "scenarios": scenario_reports,
    }


def main() -> int:
    evidence = build_evidence()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(evidence, fh, indent=2, sort_keys=True)
        fh.write("\n")

    base = evidence["scenarios"]["BASE"]
    print(f"Wrote {OUTPUT_PATH}")
    print(f"resolved_record_hash = {evidence['resolved_record_hash']}")
    print(f"friction_evidence_complete = {evidence['evidence_completeness']['friction_evidence_complete']}")
    print(f"BASE net_expectancy_R = {base['net_expectancy_R']}  net_R_total = {base['net_R_total']}")
    print(f"economic_gate_pass = {evidence['economic_status']['economic_gate_pass']}")
    print(f"economic_classification = {evidence['economic_status']['economic_classification']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
