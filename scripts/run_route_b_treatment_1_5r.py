"""AG_SSC_HYP_001_ROUTE_B_CORRECTED_TREATMENT_1_5R (RB-T0/T1/T2).

Executes the preregistered 1.5R TREATMENT over the already-FROZEN Route B Phase 1
occurrence population. This is the treatment arm of the Route B reconstruction contract:
outcome resolution ONLY, using the frozen v1.0.1 resolver
(session_sweep_continuation.outcome_resolution.resolve_campaign_entry) with
runner_target_r=1.5 and OPPOSITE_SESSION_BOUNDARY partial-target semantics.

This script is a faithful mirror of scripts/run_route_b_corrected_control_3r.py with
EXACTLY ONE experimental delta: RUNNER_TARGET_R 3.0 -> 1.5. Every other input is
byte-identical to the frozen corrected CONTROL:

  * the same frozen Phase 1 occurrence population (hash re-verified before any outcome
    is resolved -- population drift aborts the run);
  * the same M1 datasets, friction model, partial semantics, partial/runner allocation,
    outcome-resolution methodology, metrics methodology, and per-segment economics.

STRICT FIREWALLS (enforced by construction, not by convention):
  * Occurrences are LOADED from the frozen Phase 1 population files and their
    population hashes are re-verified against the frozen authority BEFORE any outcome
    is resolved. This script NEVER regenerates occurrences (no run_replay, no setup
    detection, no H1-bias resolution, no session-box construction).
  * Only the TREATMENT (runner_target_r=1.5) is executed. No other runner target is
    computed. No parameter search. No post-result repair.
  * No holdout/fresh data is touched: only the hash-admitted historical M1 datasets
    (through 2026-07-31) referenced by each occurrence's frozen post_entry_m1_reference
    are read, for the sole purpose of slicing post-entry candles.
  * Places no orders. Modifies no strategy/config/demo/live authority file. The frozen
    strategy YAML (runner_target_r=3.0) is NOT modified: the treatment overrides the
    runner target in-memory at execution time only.

RESEARCH ONLY.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from historical_replay.mt5_export_loader import load_mt5_export_csv  # noqa: E402
from historical_replay.symbol_metadata_manifest import compute_dataset_fingerprint  # noqa: E402
from performance.calculator import compute_trade_metrics  # noqa: E402
from performance.models import ResolvedTradeSample  # noqa: E402
from session_sweep_continuation.config import load_config  # noqa: E402
from session_sweep_continuation.friction import estimate_friction  # noqa: E402
from session_sweep_continuation.outcome_resolution import resolve_campaign_entry  # noqa: E402
from session_sweep_continuation.replay import _m1_subsequent_candles  # noqa: E402
from session_sweep_continuation.sessions import session_windows_from_config  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
PIP_SIZE = 0.0001
PIP_VALUE_PER_LOT = 10.0

ROUTE_B_DIR = (
    REPO_ROOT / "artifacts" / "validation" / "ST_SESSION_SWEEP_CONTINUATION_V1"
    / "HYP_001" / "ROUTE_B_PHASE1_RECONSTRUCTION"
)
OUT_DIR = (
    REPO_ROOT / "artifacts" / "validation" / "ST_SESSION_SWEEP_CONTINUATION_V1"
    / "HYP_001" / "ROUTE_B_CORRECTED_TREATMENT_1_5R"
)

# The ONLY permitted experimental delta versus the frozen corrected CONTROL:
RUNNER_TARGET_R = 1.5
CONTROL_BASELINE_RUNNER_TARGET_R = 3.0
PARTIAL_PCT = 0.50
RUNNER_PCT = 0.50

# Frozen Route B population authority (re-verified independently, this mission).
FROZEN_POPULATION_HASHES = {
    "GEN_001": "1b6cda1733e8d0edb2dfb90ed092ab3445543ff01bce97d52ad5d04256609285",
    "GEN_002A": "b5a77c4951b0f8ecaf4308e8421087ff3bd4f240ddf31e3326b536989d5f63e7",
}

# Only the M1 leg is required for post-entry outcome resolution; its hash is the one
# frozen in each occurrence's post_entry_m1_reference (admitted in the Route B
# preregistration, commit 0fdeafd). H1/M15 are NOT read here (no re-detection).
DATASETS = {
    "GEN_001": dict(
        symbol="EURUSD",
        m1=Path(r"D:\EURUSD_M1_202605180946_202607312356.csv"),
        m1_sha="55422a1ccdf4ca76fd25451fbf849d559bed45d839891a3ada7a37f9f7dd6a23",
    ),
    "GEN_002A": dict(
        symbol="GBPUSD",
        m1=Path(r"D:\GBPUSD_M1_202606080533_202607302357.csv"),
        m1_sha="390798def4c598f3463be5f339d1cf2921537e96a48eca4d797aadb78c1d705c",
    ),
}


def population_hash(occurrences) -> str:
    ordered = sorted(occurrences, key=lambda r: r["trade_id"])
    payload = json.dumps(ordered, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_m1_fingerprint(path: Path, expected: str) -> str:
    if not path.exists():
        raise SystemExit(f"DATASET_MISSING: {path}")
    actual = compute_dataset_fingerprint(path).split("sha256:", 1)[1]
    if actual != expected:
        raise SystemExit(f"FINGERPRINT_MISMATCH: {path}: actual={actual} expected={expected}")
    return actual


def resolve_outcomes(gen_id: str, spec: dict, config: dict, windows: dict):
    pop_path = ROUTE_B_DIR / gen_id / "reconstructed_occurrence_population.json"
    occurrences = json.loads(pop_path.read_text(encoding="utf-8"))

    frozen_hash = FROZEN_POPULATION_HASHES[gen_id]
    actual_hash = population_hash(occurrences)
    if actual_hash != frozen_hash:
        raise SystemExit(
            f"POPULATION_HASH_MISMATCH ({gen_id}): loaded={actual_hash} frozen={frozen_hash} -- "
            f"occurrence population must NOT be regenerated"
        )

    m1_sha = verify_m1_fingerprint(spec["m1"], spec["m1_sha"])
    m1_candles, m1_report = load_mt5_export_csv(str(spec["m1"]), spec["symbol"], "M1")
    if m1_report.normalized_timezone != "UTC":
        raise SystemExit(f"{gen_id}_M1_TIMEZONE_NOT_UTC: {m1_report.normalized_timezone}")

    outcomes = []
    for occ in occurrences:
        entry_time = datetime.fromisoformat(occ["entry_time"])
        trading_date = datetime.strptime(occ["trading_date"], "%Y-%m-%d").date()
        trade_start, trade_end = windows[occ["session_pair"]]["trade"].bounds_for_date(trading_date)

        subsequent = _m1_subsequent_candles(m1_candles, entry_time, trade_end)

        risk = abs(occ["entry_price"] - occ["stop_price"])
        friction = estimate_friction(
            spec["symbol"], config, PIP_SIZE, PIP_VALUE_PER_LOT,
            stop_distance_price=risk,
        )

        outcome = resolve_campaign_entry(
            campaign_id=occ["trade_id"],
            setup_model=occ["setup_model"],
            direction=occ["direction"],
            entry_time=entry_time,
            entry_price=occ["entry_price"],
            stop_price=occ["stop_price"],
            reference_high=occ["reference_high"],
            reference_low=occ["reference_low"],
            runner_target_r=RUNNER_TARGET_R,
            partial_pct=PARTIAL_PCT,
            runner_pct=RUNNER_PCT,
            subsequent_candles=subsequent,
            session_exit_time=trade_end,
            friction=friction,
        )

        events = [e["event"] for e in outcome.event_sequence]
        outcomes.append({
            "trade_id": occ["trade_id"],
            "generation_id": gen_id,
            "symbol": occ["symbol"],
            "session_pair": occ["session_pair"],
            "trading_date": occ["trading_date"],
            "setup_model": occ["setup_model"],
            "direction": occ["direction"],
            "entry_time": occ["entry_time"],
            "entry_price": occ["entry_price"],
            "stop_price": occ["stop_price"],
            "reference_high": occ["reference_high"],
            "reference_low": occ["reference_low"],
            "partial_target_price": outcome.partial_target_price,
            "partial_target_interpretation": outcome.partial_target_interpretation,
            "runner_target_r": outcome.runner_target_r,
            "terminal_state": outcome.terminal_state,
            "gross_R": outcome.gross_R,
            "net_R": outcome.net_R,
            "spread_cost_R": outcome.spread_cost_R,
            "commission_cost_R": outcome.commission_cost_R,
            "slippage_cost_R": outcome.slippage_cost_R,
            "cost_status": outcome.cost_status,
            "note": outcome.note,
            "event_sequence": outcome.event_sequence,
            "partial_target_hit": "PARTIAL_TARGET" in events,
            "runner_target_hit": "RUNNER_TARGET_HIT" in events,
            "subsequent_m1_bar_count": len(subsequent),
        })

    outcomes.sort(key=lambda r: r["trade_id"])
    return outcomes, actual_hash, m1_sha


def metrics_for(outcomes, symbol, label):
    samples = []
    for o in outcomes:
        if o["gross_R"] is not None:
            samples.append(ResolvedTradeSample(
                source_record_id=o["trade_id"],
                source_path="session_sweep_continuation.outcome_resolution.resolve_campaign_entry",
                strategy_id="ST_SESSION_SWEEP_CONTINUATION_V1",
                strategy_version="1.0.1",
                symbol=symbol,
                cycle=o["session_pair"],
                resolved_at=o["entry_time"],
                gross_R=o["gross_R"],
                net_R=o["net_R"],
                cost_status=o["cost_status"],
                outcome=o["terminal_state"],
            ))

    m = compute_trade_metrics(samples)
    resolved = [o for o in outcomes if o["gross_R"] is not None]
    unresolved = [o for o in outcomes if o["gross_R"] is None]

    gross_total = m.gross_total_R
    net_total = m.net_total_R
    friction_total = (gross_total - net_total) if (net_total != "NOT_EVALUATED" and net_total is not None) else "NOT_EVALUATED"

    def state_count(s):
        return sum(1 for o in outcomes if o["terminal_state"] == s)

    setup_counts = {"S1_SWEEP_REVERSAL": 0, "S2_BREAKOUT_CONTINUATION": 0, "S3_PULLBACK_CONTINUATION": 0}
    for o in outcomes:
        key = o["setup_model"]
        if key in setup_counts:
            setup_counts[key] += 1
    long_count = sum(1 for o in outcomes if o["direction"] == "LONG")
    short_count = sum(1 for o in outcomes if o["direction"] == "SHORT")
    session_counts = {}
    for o in outcomes:
        session_counts[o["session_pair"]] = session_counts.get(o["session_pair"], 0) + 1

    return {
        "label": label,
        "symbol": symbol,
        "n_occurrences": len(outcomes),
        "n_resolved": len(resolved),
        "n_unresolved": len(unresolved),
        "wins": m.wins,
        "losses": m.losses,
        "breakevens": m.breakevens,
        "gross_total_R": gross_total,
        "friction_R": friction_total,
        "net_total_R": net_total,
        "gross_expectancy_R": m.gross_expectancy_R,
        "net_expectancy_R": m.net_expectancy_R,
        "profit_factor": m.profit_factor,
        "net_profit_factor": None,  # filled below if computable
        "win_rate": m.win_rate,
        "max_drawdown_R": m.max_drawdown_R,
        "max_consecutive_losses": m.max_consecutive_losses,
        "average_win_R": m.average_win_R,
        "average_loss_R": m.average_loss_R,
        "cost_status": m.cost_status,
        "partial_target_hits": sum(1 for o in outcomes if o["partial_target_hit"]),
        "partial_activation_rate": (sum(1 for o in outcomes if o["partial_target_hit"]) / len(resolved)) if resolved else None,
        "runner_target_hits": sum(1 for o in outcomes if o["runner_target_hit"]),
        "initial_stop_exits": state_count("RESOLVED_SL"),
        "session_exits": state_count("RESOLVED_SESSION_EXIT"),
        "runner_be_exits": state_count("RESOLVED_PARTIAL_BE"),
        "ambiguous_sequence": state_count("AMBIGUOUS_SEQUENCE"),
        "unresolved_no_data": state_count("UNRESOLVED_NO_DATA"),
        "setup_counts": setup_counts,
        "long_count": long_count,
        "short_count": short_count,
        "session_counts": session_counts,
    }


def main():
    config = load_config(repo_root=str(REPO_ROOT))
    if str(config.get("version")) != "1.0.1":
        raise SystemExit(f"STRATEGY_VERSION_NOT_1_0_1: {config.get('version')!r}")
    tm = config.get("trade_management", {})
    # Firewall: the frozen strategy YAML must still carry the CONTROL baseline of 3.0R.
    # The treatment overrides it in-memory (RUNNER_TARGET_R=1.5) WITHOUT modifying the
    # frozen YAML. Any drift in the frozen baseline aborts the run.
    if float(tm.get("runner_target_r")) != CONTROL_BASELINE_RUNNER_TARGET_R:
        raise SystemExit(f"CONTROL_BASELINE_MISMATCH: {tm.get('runner_target_r')!r}")

    windows = session_windows_from_config(config)

    all_outcomes = []
    gen_results = {}
    for gen_id, spec in DATASETS.items():
        outcomes, pop_hash, m1_sha = resolve_outcomes(gen_id, spec, config, windows)
        all_outcomes.extend(outcomes)
        gen_results[gen_id] = {
            "population_hash": pop_hash,
            "population_hash_matches_frozen": pop_hash == FROZEN_POPULATION_HASHES[gen_id],
            "m1_sha256": m1_sha,
            "metrics": metrics_for(outcomes, spec["symbol"], gen_id),
        }

    all_outcomes.sort(key=lambda r: r["trade_id"])
    combined_metrics = metrics_for(all_outcomes, "EURUSD+GBPUSD", "COMBINED")

    # per-setup economics (combined population) -- RB-T2 S1/S2/S3
    setup_metrics = {}
    for setup in ("S1_SWEEP_REVERSAL", "S2_BREAKOUT_CONTINUATION", "S3_PULLBACK_CONTINUATION"):
        subset = [o for o in all_outcomes if o["setup_model"] == setup]
        if subset:
            setup_metrics[setup] = metrics_for(subset, "EURUSD+GBPUSD", setup)

    # net profit factor over combined resolved trades (canonical: positive_net/abs(negative_net))
    net_vals = [o["net_R"] for o in all_outcomes if o["net_R"] is not None]
    if net_vals:
        pos = sum(v for v in net_vals if v > 0)
        neg = sum(v for v in net_vals if v < 0)
        if neg == 0:
            combined_metrics["net_profit_factor"] = "UNDEFINED_NO_LOSSES" if pos else "NOT_EVALUATED"
        else:
            combined_metrics["net_profit_factor"] = (pos / abs(neg)) if pos else "UNDEFINED_NO_WINS"
    else:
        combined_metrics["net_profit_factor"] = "NOT_EVALUATED"

    # combined population hash (same deterministic algorithm as the Phase 1 freeze)
    combined_pop_hash_parts = sorted(f"{g}:{gen_results[g]['population_hash']}" for g in DATASETS)
    combined_pop_hash = hashlib.sha256(json.dumps(combined_pop_hash_parts, sort_keys=True).encode()).hexdigest()

    # TREATMENT hashes
    outcomes_payload = json.dumps(all_outcomes, sort_keys=True, separators=(",", ":"))
    treatment_outcome_hash = hashlib.sha256(outcomes_payload.encode("utf-8")).hexdigest()

    evidence = {
        "treatment_id": "SSC_V1_0_1_TREATMENT_1_5R",
        "strategy": "ST_SESSION_SWEEP_CONTINUATION_V1",
        "version": "1.0.1",
        "runner_target_r": RUNNER_TARGET_R,
        "control_baseline_runner_target_r": CONTROL_BASELINE_RUNNER_TARGET_R,
        "partial_target_pct": PARTIAL_PCT,
        "runner_pct": RUNNER_PCT,
        "partial_semantics": "OPPOSITE_SESSION_BOUNDARY",
        "LONG": "reference_high",
        "SHORT": "reference_low",
        "generations": gen_results,
        "combined": combined_metrics,
        "setup_metrics": setup_metrics,
        "population_hashes": {
            "GEN_001": gen_results["GEN_001"]["population_hash"],
            "GEN_002A": gen_results["GEN_002A"]["population_hash"],
            "COMBINED": combined_pop_hash,
        },
        "frozen_phase1_hashes": dict(FROZEN_POPULATION_HASHES),
        "treatment_outcome_hash": treatment_outcome_hash,
    }
    treatment_evidence_hash = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "TREATMENT_OUTCOMES.json").write_text(
        json.dumps(all_outcomes, indent=2, sort_keys=True, default=str), encoding="utf-8",
    )
    (OUT_DIR / "TREATMENT_SUMMARY.json").write_text(
        json.dumps({**evidence, "treatment_evidence_hash": treatment_evidence_hash},
                   indent=2, sort_keys=True, default=str), encoding="utf-8",
    )

    print(json.dumps({
        "treatment_outcome_hash": treatment_outcome_hash,
        "treatment_evidence_hash": treatment_evidence_hash,
        "treatment_population_hash": {
            "GEN_001": gen_results["GEN_001"]["population_hash"],
            "GEN_002A": gen_results["GEN_002A"]["population_hash"],
            "COMBINED": combined_pop_hash,
        },
        "population_hash_matches_phase1": all(
            gen_results[g]["population_hash_matches_frozen"] for g in DATASETS
        ),
        "combined": combined_metrics,
    }, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
