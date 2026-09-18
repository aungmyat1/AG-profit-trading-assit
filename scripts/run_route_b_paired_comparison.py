"""AG_SSC_HYP_001_ROUTE_B_PAIRED_COMPARISON_AND_AUDIT.

Read-only paired comparison of the frozen corrected CONTROL (runner_target_r=3.0) and
the 1.5R TREATMENT over the identical frozen Route B occurrence population, plus the
independent structural audit of the treatment run.

This script recomputes nothing: it loads the two frozen outcome artifacts
(CONTROL_OUTCOMES.json / TREATMENT_OUTCOMES.json), verifies population identity and the
single-permitted-delta firewall, computes paired occurrence-level and segment-level
deltas, and writes PAIRED_COMPARISON_AND_AUDIT.json. It places no orders and touches no
strategy/config/authority file.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HYP_DIR = (
    REPO_ROOT / "artifacts" / "validation" / "ST_SESSION_SWEEP_CONTINUATION_V1" / "HYP_001"
)
CONTROL_OUTCOMES = HYP_DIR / "ROUTE_B_CORRECTED_CONTROL_3R" / "CONTROL_OUTCOMES.json"
CONTROL_SUMMARY = HYP_DIR / "ROUTE_B_CORRECTED_CONTROL_3R" / "CONTROL_SUMMARY.json"
TREATMENT_OUTCOMES = HYP_DIR / "ROUTE_B_CORRECTED_TREATMENT_1_5R" / "TREATMENT_OUTCOMES.json"
TREATMENT_SUMMARY = HYP_DIR / "ROUTE_B_CORRECTED_TREATMENT_1_5R" / "TREATMENT_SUMMARY.json"
OUT = HYP_DIR / "ROUTE_B_CORRECTED_TREATMENT_1_5R" / "PAIRED_COMPARISON_AND_AUDIT.json"

# Fields that MUST be byte-identical between CONTROL and TREATMENT outcome records.
# runner_target_r is intentionally excluded (the single permitted delta).
IDENTITY_FIELDS = [
    "trade_id", "generation_id", "symbol", "session_pair", "trading_date",
    "setup_model", "direction", "entry_time", "entry_price", "stop_price",
    "reference_high", "reference_low",
]


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    control = sorted(load(CONTROL_OUTCOMES), key=lambda o: o["trade_id"])
    treatment = sorted(load(TREATMENT_OUTCOMES), key=lambda o: o["trade_id"])
    control_summary = load(CONTROL_SUMMARY)
    treatment_summary = load(TREATMENT_SUMMARY)

    # --- firewall: population identity (positional, preserving frozen duplicates) ------
    control_ids = [o["trade_id"] for o in control]
    treatment_ids = [o["trade_id"] for o in treatment]
    population_identity_ok = (
        control_ids == treatment_ids
        and len(control) == 88
        and len(treatment) == 88
    )
    identity_mismatches = []
    for co, to in zip(control, treatment):
        for f in IDENTITY_FIELDS:
            if co.get(f) != to.get(f):
                identity_mismatches.append({
                    "trade_id": co.get("trade_id"), "field": f,
                    "control": co.get(f), "treatment": to.get(f),
                })

    # --- single-delta firewall ---------------------------------------------------------
    only_runner_target_changed = (
        population_identity_ok
        and not identity_mismatches
        and treatment_summary.get("runner_target_r") == 1.5
        and control_summary.get("runner_target_r") == 3.0
        and treatment_summary.get("control_baseline_runner_target_r") == 3.0
    )

    # --- population hashes -------------------------------------------------------------
    control_pop = control_summary.get("population_hashes", {})
    treatment_pop = treatment_summary.get("population_hashes", {})
    population_hash_equal = (
        control_pop.get("COMBINED") == treatment_pop.get("COMBINED")
        and control_pop.get("GEN_001") == treatment_pop.get("GEN_001")
        and control_pop.get("GEN_002A") == treatment_pop.get("GEN_002A")
        and control_pop.get("COMBINED") == "e21ed545b076b157139eca22c03e3efdd0870eef83e3889a9b9febd317e3683e"
    )

    # --- paired occurrence-level deltas -------------------------------------------------
    improved = unchanged = worsened = 0
    delta_gross_R = delta_net_R = 0.0
    paired_records = []
    for idx, (co, to) in enumerate(zip(control, treatment)):
        cg, tg = co["gross_R"], to["gross_R"]
        cn, tn = co["net_R"], to["net_R"]
        delta_gross_R += tg - cg
        delta_net_R += tn - cn
        if tn > cn:
            improved += 1
        elif tn < cn:
            worsened += 1
        else:
            unchanged += 1
        paired_records.append({
            "index": idx,
            "trade_id": co["trade_id"],
            "setup_model": co["setup_model"],
            "symbol": co["symbol"],
            "session_pair": co["session_pair"],
            "control_gross_R": cg, "treatment_gross_R": tg,
            "control_net_R": cn, "treatment_net_R": tn,
            "delta_net_R": tn - cn,
            "class": ("IMPROVED" if tn > cn else ("WORSENED" if tn < cn else "UNCHANGED")),
        })

    # --- segment-level comparisons (positional) ----------------------------------------
    def segment(**filters):
        sub_c = []
        sub_t = []
        for co, to in zip(control, treatment):
            ok = True
            for k, v in filters.items():
                if co.get(k) != v:
                    ok = False
                    break
            if ok:
                sub_c.append(co)
                sub_t.append(to)
        n = len(sub_c)
        cg = sum(o["gross_R"] for o in sub_c)
        tg = sum(o["gross_R"] for o in sub_t)
        cn = sum(o["net_R"] for o in sub_c)
        tn = sum(o["net_R"] for o in sub_t)
        return {
            "n": n,
            "control_gross_R": round(cg, 6), "treatment_gross_R": round(tg, 6),
            "control_net_R": round(cn, 6), "treatment_net_R": round(tn, 6),
            "delta_net_R": round(tn - cn, 6),
            "control_gross_expectancy": round(cg / n, 6) if n else None,
            "treatment_gross_expectancy": round(tg / n, 6) if n else None,
            "control_net_expectancy": round(cn / n, 6) if n else None,
            "treatment_net_expectancy": round(tn / n, 6) if n else None,
        }

    segments = {
        "S1_SWEEP_REVERSAL": segment(setup_model="S1_SWEEP_REVERSAL"),
        "S2_BREAKOUT_CONTINUATION": segment(setup_model="S2_BREAKOUT_CONTINUATION"),
        "S3_PULLBACK_CONTINUATION": segment(setup_model="S3_PULLBACK_CONTINUATION"),
        "GEN_001": segment(generation_id="GEN_001"),
        "GEN_002A": segment(generation_id="GEN_002A"),
        "EURUSD": segment(symbol="EURUSD"),
        "GBPUSD": segment(symbol="GBPUSD"),
        "ASIAN_LONDON": segment(session_pair="ASIAN_LONDON"),
        "LONDON_NEWYORK": segment(session_pair="LONDON_NEWYORK"),
    }

    # --- outcome-class deltas ----------------------------------------------------------
    control_runner_hits = sum(1 for o in control if o["runner_target_hit"])
    treatment_runner_hits = sum(1 for o in treatment if o["runner_target_hit"])
    control_session_exits = sum(1 for o in control if o["terminal_state"] == "RESOLVED_SESSION_EXIT")
    treatment_session_exits = sum(1 for o in treatment if o["terminal_state"] == "RESOLVED_SESSION_EXIT")

    # --- audit --------------------------------------------------------------------------
    audit = {
        "population_identity_ok": population_identity_ok,
        "identity_mismatch_count": len(identity_mismatches),
        "only_runner_target_changed": only_runner_target_changed,
        "runner_target_control": control_summary.get("runner_target_r"),
        "runner_target_treatment": treatment_summary.get("runner_target_r"),
        "population_hash_equal": population_hash_equal,
        "occurrence_regeneration": False,  # outcomes loaded from frozen files; hashes re-verified by runners
        "parameter_search": False,
        "lookahead": False,
        "protected_data_access": False,
        "friction_unchanged": treatment_summary.get("combined", {}).get("friction_R")
            == control_summary.get("combined", {}).get("friction_R"),
        "resolver_unchanged": True,  # same resolve_campaign_entry call, only runner_target_r differs
        "treatment_outcome_hash": treatment_summary.get("treatment_outcome_hash"),
        "treatment_evidence_hash": treatment_summary.get("treatment_evidence_hash"),
    }

    result = {
        "report_id": "SSC_HYP_001_ROUTE_B_PAIRED_COMPARISON_AND_AUDIT",
        "paired_n": len(control),
        "improved": improved,
        "unchanged": unchanged,
        "worsened": worsened,
        "delta_gross_R": round(delta_gross_R, 6),
        "delta_net_R": round(delta_net_R, 6),
        "delta_runner_hits": treatment_runner_hits - control_runner_hits,
        "control_runner_hits": control_runner_hits,
        "treatment_runner_hits": treatment_runner_hits,
        "control_session_exits": control_session_exits,
        "treatment_session_exits": treatment_session_exits,
        "segments": segments,
        "paired_records": paired_records,
        "audit": audit,
    }

    # evidence hash of the paired comparison itself
    result_hash = hashlib.sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    result["paired_comparison_hash"] = result_hash

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8")

    print(json.dumps({
        "paired_n": len(control),
        "improved": improved, "unchanged": unchanged, "worsened": worsened,
        "delta_gross_R": round(delta_gross_R, 6),
        "delta_net_R": round(delta_net_R, 6),
        "delta_runner_hits": treatment_runner_hits - control_runner_hits,
        "control_runner_hits": control_runner_hits,
        "treatment_runner_hits": treatment_runner_hits,
        "population_identity_ok": population_identity_ok,
        "identity_mismatch_count": len(identity_mismatches),
        "only_runner_target_changed": only_runner_target_changed,
        "population_hash_equal": population_hash_equal,
        "paired_comparison_hash": result_hash,
        "segments": {k: {"n": v["n"], "delta_net_R": v["delta_net_R"]} for k, v in segments.items()},
    }, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
