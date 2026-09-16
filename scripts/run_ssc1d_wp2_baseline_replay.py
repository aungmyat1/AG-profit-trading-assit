"""AG SSC1D-WP2 -- DEVELOPMENT baseline replay for ST_SESSION_SWEEP_CONTINUATION_V1.

Pilot-local driver for the SSC_ONE_DAY_OPTIMIZATION_PILOT_V1 pilot
(docs/validation/SSC_ONE_DAY_DEMO_PILOT_V2.md). Produces ONE authoritative,
canonical-parity SSC v1.0.0 replay over the DEVELOPMENT dataset only
(GEN_001 EURUSD H1/M15/M1 triplet), writing output exclusively to a new
pilot-local path -- never into artifacts/research/EXP_EXPOSURE_EFFICIENCY_V1/GEN_001/.

This is a deliberate near-duplicate of
scripts/run_first_canonical_session_sweep_continuation_replay.py, reusing
the EXACT same underlying library calls (historical_replay.*,
session_sweep_continuation.h1_bias/replay, performance.calculator) and the
EXACT same frozen strategy config/data -- zero semantic changes -- so its
output can be directly parity-checked against that script's already-existing,
already-reproducibility-verified canonical population
(artifacts/research/EXP_EXPOSURE_EFFICIENCY_V1/GEN_001/canonical_lifecycle_population.json,
population_hash 8e32a7498e5a1c7df6658e6700ff3386fb38821ed189619a20224ce032d9166d)
WITHOUT writing into, or modifying, that existing canonical evidence.

RESEARCH ONLY. Places no orders, touches no demo_eligible/demo_authorized/
live_authorized field, and changes no strategy parameter. FROZEN STRATEGY +
FROZEN DATA + FROZEN BIAS ARCHITECTURE -- this script is a pure
read/compute/report driver, identical in kind to the script it mirrors.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from historical_replay.candle_store import HistoricalCandleStore  # noqa: E402
from historical_replay.mt5_export_loader import load_mt5_export_csv  # noqa: E402
from historical_replay.symbol_metadata_manifest import (  # noqa: E402
    compute_dataset_fingerprint,
    load_symbol_metadata_manifest,
    validate_manifest_for_dataset,
)
from performance.calculator import compute_trade_metrics  # noqa: E402
from performance.models import ResolvedTradeSample  # noqa: E402
from research.session_lifecycle import (  # noqa: E402
    compare_lifecycle_records, control_reconcile, lifecycle_record, population_hash,
)
from session_sweep_continuation.config import compute_config_hash, load_config  # noqa: E402
from session_sweep_continuation.h1_bias import resolve_h1_market_bias  # noqa: E402
from session_sweep_continuation.replay import run_replay  # noqa: E402
from session_sweep_continuation.sessions import session_windows_from_config  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SYMBOL = "EURUSD"
PIP_SIZE = 0.0001
PIP_VALUE_PER_LOT = 10.0
STRUCTURE_WARMUP_H1_BARS = 1000  # market_structure.tiers.EXTERNAL_SWING_LENGTH(50)*20

H1_CSV = Path(r"D:\EURUSD_H1_202501020000_202607310000.csv")
M15_CSV = Path(r"D:\EURUSD_M15_202501020000_202606192345.csv")
M1_CSV = Path(r"D:\EURUSD_M1_202605180946_202607312356.csv")

H1_MANIFEST_PATH = REPO_ROOT / "config" / "historical_datasets" / "EURUSD_H1_symbol_metadata.yaml"

# Pilot-local output only -- never artifacts/research/EXP_EXPOSURE_EFFICIENCY_V1/GEN_001/.
OUT_DIR = REPO_ROOT / "artifacts" / "validation" / "ST_SESSION_SWEEP_CONTINUATION_V1" / "SSC1D_PILOT" / "SSC1D_WP2_BASELINE"

# Existing canonical evidence, READ-ONLY, for cross-population-hash parity checking only.
GEN_001_LIFECYCLE_PATH = REPO_ROOT / "artifacts" / "research" / "EXP_EXPOSURE_EFFICIENCY_V1" / "GEN_001" / "canonical_lifecycle_population.json"

EXPECTED_SHA256 = {
    H1_CSV: "f1b456e4b50215ad23370949f15faaa8548f9c03053a20d8974d6e9fd480a060",
    M15_CSV: "7f7502938862f4a3779f018caab468fe4445a4d8c676c8393dc29ca57fc43a65",
    M1_CSV: "55422a1ccdf4ca76fd25451fbf849d559bed45d839891a3ada7a37f9f7dd6a23",
}


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except Exception:
        return "UNKNOWN"


def _verify_fingerprint(path: Path) -> str:
    if not path.exists():
        raise SystemExit(f"DATASET_MISSING: {path}")
    actual = compute_dataset_fingerprint(path).split("sha256:", 1)[1]
    expected = EXPECTED_SHA256[path]
    if actual != expected:
        raise SystemExit(f"FINGERPRINT_MISMATCH: {path}: actual={actual} expected={expected}")
    return actual


def _effective_date_range(h1_report, m15_report, m1_report, config: dict):
    """Identical logic to the canonical GEN_001 driver: a calendar date is INCLUDED only
    if, for EVERY configured session_pair, M15/M1/H1 coverage is sufficient for that
    date's decision cycle (computed from actual file coverage, never assumed)."""
    windows = session_windows_from_config(config)
    raw_start = max(m15_report.start_utc, m1_report.start_utc, h1_report.start_utc)
    raw_end = min(m15_report.end_utc, m1_report.end_utc, h1_report.end_utc)

    covered_dates = []
    d = raw_start.date()
    while datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc) <= raw_end:
        ok = True
        for pair_id, w in windows.items():
            ref_start, ref_end = w["reference"].bounds_for_date(d)
            trade_start, trade_end = w["trade"].bounds_for_date(d)
            if not (m15_report.start_utc <= ref_start and trade_end <= m15_report.end_utc):
                ok = False
                break
            if not (m1_report.start_utc <= trade_start and trade_end <= m1_report.end_utc):
                ok = False
                break
            if not (h1_report.start_utc + timedelta(hours=STRUCTURE_WARMUP_H1_BARS) <= ref_end):
                ok = False
                break
        if ok:
            covered_dates.append(d)
        d = d + timedelta(days=1)

    return covered_dates


def main():
    config = load_config(repo_root=str(REPO_ROOT))
    config_hash = compute_config_hash(config)
    git_commit = _git_commit()

    h1_sha = _verify_fingerprint(H1_CSV)
    m15_sha = _verify_fingerprint(M15_CSV)
    m1_sha = _verify_fingerprint(M1_CSV)

    h1_manifest = load_symbol_metadata_manifest(H1_MANIFEST_PATH)
    if h1_manifest.authority != "OWNER_APPROVED_DATASET_MANIFEST":
        raise SystemExit(f"H1_METADATA_NOT_AUTHORIZED: authority={h1_manifest.authority!r}")
    validate_manifest_for_dataset(h1_manifest, H1_CSV, SYMBOL)

    print("Loading H1...", file=sys.stderr)
    h1_candles, h1_report = load_mt5_export_csv(str(H1_CSV), SYMBOL, "H1")
    print("Loading M15...", file=sys.stderr)
    m15_candles, m15_report = load_mt5_export_csv(str(M15_CSV), SYMBOL, "M15")
    print("Loading M1...", file=sys.stderr)
    m1_candles, m1_report = load_mt5_export_csv(str(M1_CSV), SYMBOL, "M1")

    for report, label in ((h1_report, "H1"), (m15_report, "M15"), (m1_report, "M1")):
        if report.normalized_timezone != "UTC":
            raise SystemExit(f"{label}_TIMEZONE_NOT_UTC: {report.normalized_timezone}")

    h1_store = HistoricalCandleStore()
    h1_store.load_series(SYMBOL, "H1", h1_candles)

    dates = _effective_date_range(h1_report, m15_report, m1_report, config)
    if not dates:
        raise SystemExit("EFFECTIVE_REPLAY_WINDOW_EMPTY")
    effective_start, effective_end = dates[0], dates[-1]

    session_pairs = [p["pair_id"] for p in config.get("session_pairs", ())]
    windows = session_windows_from_config(config)

    def run_all_cycles(run_label: str):
        decision_cycles = 0
        bias_counts = {"BULLISH": 0, "BEARISH": 0, "NEUTRAL": 0, "UNAVAILABLE": 0, "ERROR": 0}
        regime_counts = {}
        setup_candidates = {"S1": 0, "S2": 0, "S3": 0}
        direction_blocked = 0
        fills = {"S1": 0, "S2": 0, "S3": 0}
        campaigns_started = 0
        campaigns_with = {"S1": 0, "S2": 0, "S3": 0}
        campaigns_no_trade = 0
        friction_rejections = 0
        alloc_rejections = 0
        exclusions = {
            "insufficient_h1_history": 0, "neutral_bias": 0, "unavailable_bias": 0,
            "direction_blocked": 0, "regime_unknown": 0, "friction_rejected": 0,
            "alloc_rejected": 0, "ambiguous": 0,
        }
        session_pair_samples = {p: [] for p in session_pairs}
        direction_samples = {"LONG": [], "SHORT": []}
        regime_samples = {}
        setup_samples = {"S1": [], "S2": [], "S3": []}
        exit_reason_samples: dict[str, list] = {}
        all_samples = []
        lifecycle_records = []

        for d in dates:
            for pair_id in session_pairs:
                decision_cycles += 1
                ref_end = windows[pair_id]["reference"].bounds_for_date(d)[1]

                bias = resolve_h1_market_bias(h1_store, h1_manifest, SYMBOL, ref_end, pair_id)
                if bias.confidence == "UNAVAILABLE":
                    if bias.bias == "NEUTRAL" and "INSUFFICIENT" in "".join(bias.reason_codes):
                        bias_counts["UNAVAILABLE"] += 1
                        exclusions["insufficient_h1_history"] += 1
                    else:
                        bias_counts["UNAVAILABLE"] += 1
                        exclusions["unavailable_bias"] += 1
                elif bias.bias == "NEUTRAL":
                    bias_counts["NEUTRAL"] += 1
                    exclusions["neutral_bias"] += 1
                else:
                    bias_counts[bias.bias] += 1

                result = run_replay(
                    m15_candles, config, SYMBOL, pair_id, d, PIP_SIZE, PIP_VALUE_PER_LOT,
                    bias_result=bias, m1_candles=m1_candles,
                )

                if result.regime is None or result.regime == "UNKNOWN":
                    regime_counts["UNKNOWN"] = regime_counts.get("UNKNOWN", 0) + 1
                    exclusions["regime_unknown"] += 1
                    continue
                regime_counts[result.regime] = regime_counts.get(result.regime, 0) + 1

                for rej in result.rejected_setups:
                    reason = rej.get("reason", "")
                    if reason in ("BIAS_MISSING", "BIAS_SYMBOL_MISMATCH", "BIAS_DIRECTION_MISMATCH"):
                        direction_blocked += 1
                        exclusions["direction_blocked"] += 1
                    elif reason == "STOP_BELOW_FRICTION_FLOOR":
                        friction_rejections += 1
                        exclusions["friction_rejected"] += 1
                    elif reason in ("MAX_TOTAL_ENTRIES_PER_CAMPAIGN_REACHED", "SETUP_MAX_OCCURRENCES_REACHED",
                                     "RISK_CAP_EXHAUSTED", "MIN_MEANINGFUL_RISK_UNAVAILABLE",
                                     "CAMPAIGN_NOT_ACCEPTING_ENTRIES"):
                        alloc_rejections += 1
                        exclusions["alloc_rejected"] += 1

                if result.campaign is not None:
                    campaigns_started += 1
                    setup_models_in_campaign = set()
                    for entry_dict in result.accepted_setups:
                        model = entry_dict["setup_model"]
                        key = "S1" if model.startswith("S1") else "S2" if model.startswith("S2") else "S3"
                        setup_candidates[key] += 1
                        setup_models_in_campaign.add(key)
                        outcome = entry_dict["outcome"]
                        if outcome["terminal_state"] == "AMBIGUOUS_SEQUENCE":
                            exclusions["ambiguous"] += 1
                            continue
                        if outcome["gross_R"] is None:
                            continue
                        fills[key] += 1
                        sample = ResolvedTradeSample(
                            source_record_id=f"{pair_id}_{d}_{entry_dict['entry_time']}_{model}",
                            source_path="session_sweep_continuation.replay.run_replay",
                            strategy_id="ST_SESSION_SWEEP_CONTINUATION_V1",
                            strategy_version=config.get("version", "1.0.0"),
                            symbol=SYMBOL, cycle=pair_id, resolved_at=entry_dict["entry_time"],
                            gross_R=outcome["gross_R"], net_R=outcome["net_R"],
                            cost_status=outcome["cost_status"], outcome=outcome["terminal_state"],
                        )
                        all_samples.append(sample)
                        lifecycle_records.append(lifecycle_record(
                            entry_dict,
                            trade_id=sample.source_record_id,
                            strategy_id=sample.strategy_id,
                            strategy_version=sample.strategy_version,
                            symbol=SYMBOL,
                        ))
                        session_pair_samples[pair_id].append(sample)
                        direction_samples[entry_dict["direction"]].append(sample)
                        regime_samples.setdefault(result.regime, []).append(sample)
                        setup_samples[key].append(sample)
                        exit_reason_samples.setdefault(outcome["terminal_state"], []).append(sample)
                    for key in setup_models_in_campaign:
                        campaigns_with[key] += 1
                    if not setup_models_in_campaign:
                        campaigns_no_trade += 1

                print(
                    f"{run_label} cycle {decision_cycles}/{len(dates) * len(session_pairs)} "
                    f"session={pair_id} date={d} occurrence_count_so_far={len(lifecycle_records)}",
                    file=sys.stderr, flush=True,
                )

        return {
            "decision_cycles": decision_cycles, "bias_counts": bias_counts, "regime_counts": regime_counts,
            "setup_candidates": setup_candidates, "direction_blocked": direction_blocked, "fills": fills,
            "campaigns_started": campaigns_started, "campaigns_with": campaigns_with,
            "campaigns_no_trade": campaigns_no_trade, "friction_rejections": friction_rejections,
            "alloc_rejections": alloc_rejections, "exclusions": exclusions,
            "session_pair_samples": session_pair_samples, "direction_samples": direction_samples,
            "regime_samples": regime_samples, "setup_samples": setup_samples,
            "exit_reason_samples": exit_reason_samples, "all_samples": all_samples,
            "lifecycle_records": lifecycle_records,
        }

    total_cycles = len(dates) * len(session_pairs)
    print(f"Running replay across {total_cycles} cycles...", file=sys.stderr, flush=True)
    run1 = run_all_cycles("RUN_1")
    print("Running replay again for determinism check...", file=sys.stderr)
    run2 = run_all_cycles("RUN_2")

    run1_records = run1["lifecycle_records"]
    run2_records = run2["lifecycle_records"]
    run1_hash = population_hash(run1_records)
    run2_hash = population_hash(run2_records)
    field_comparison = compare_lifecycle_records(run1_records, run2_records)
    field_comparison["population_hash_equal"] = run1_hash == run2_hash
    field_comparison["run_1_hash"] = run1_hash
    field_comparison["run_2_hash"] = run2_hash
    field_comparison["final_verdict"] = (
        "G0_REPRODUCIBILITY_PASS"
        if field_comparison["trade_count_equal"]
        and field_comparison["occurrence_ids_equal"]
        and field_comparison["occurrence_order_equal"]
        and field_comparison["field_level_equal"]
        and field_comparison["population_hash_equal"]
        else "G0_REPRODUCIBILITY_FAIL"
    )

    # Cross-population parity check against the pre-existing GEN_001 canonical
    # population -- READ-ONLY, no write into that directory.
    gen001_parity = {"gen001_artifact_found": False}
    if GEN_001_LIFECYCLE_PATH.exists():
        gen001_records = json.loads(GEN_001_LIFECYCLE_PATH.read_text(encoding="utf-8"))
        gen001_hash = population_hash(gen001_records)
        gen001_parity = {
            "gen001_artifact_found": True,
            "gen001_population_hash": gen001_hash,
            "wp2_run1_population_hash": run1_hash,
            "matches_gen001": gen001_hash == run1_hash,
        }

    r = run1
    overall_metrics = compute_trade_metrics(r["all_samples"])
    by_setup_metrics = {k: compute_trade_metrics(v) for k, v in r["setup_samples"].items()}
    by_direction_metrics = {k: compute_trade_metrics(v) for k, v in r["direction_samples"].items()}
    by_regime_metrics = {k: compute_trade_metrics(v) for k, v in r["regime_samples"].items()}
    by_session_metrics = {k: compute_trade_metrics(v) for k, v in r["session_pair_samples"].items()}
    by_exit_reason_metrics = {k: compute_trade_metrics(v) for k, v in r["exit_reason_samples"].items()}

    combined_fp_input = json.dumps({
        "H1": h1_sha, "M15": m15_sha, "M1": m1_sha,
        "symbol_metadata": h1_manifest.dataset_fingerprint,
    }, sort_keys=True)
    replay_evidence_fingerprint = hashlib.sha256(combined_fp_input.encode("utf-8")).hexdigest()

    report = {
        "report_id": "SSC1D_WP2_DEVELOPMENT_BASELINE",
        "pilot_id": "SSC_ONE_DAY_OPTIMIZATION_PILOT_V1",
        "work_package": "SSC1D-WP2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "identity": {
            "strategy_id": "ST_SESSION_SWEEP_CONTINUATION_V1",
            "strategy_version": config.get("version", "1.0.0"),
            "git_commit": git_commit, "config_fingerprint": config_hash,
            "H1_fingerprint": h1_sha, "M15_fingerprint": m15_sha, "M1_fingerprint": m1_sha,
            "symbol_metadata_fingerprint": h1_manifest.dataset_fingerprint,
            "replay_evidence_fingerprint": f"sha256:{replay_evidence_fingerprint}",
            "replay_engine_version": "session_sweep_continuation.replay v1 (M1-fill-wired)",
        },
        "development_dataset_id": "SSC1D_WP2_DEVELOPMENT_GEN001_TRIPLET",
        "coverage": {
            "h1_raw": {"start": str(h1_report.start_utc), "end": str(h1_report.end_utc)},
            "m15_raw": {"start": str(m15_report.start_utc), "end": str(m15_report.end_utc)},
            "m1_raw": {"start": str(m1_report.start_utc), "end": str(m1_report.end_utc)},
            "effective_start": str(effective_start), "effective_end": str(effective_end),
            "effective_days": len(dates),
        },
        "decision_cycles": r["decision_cycles"],
        "bias_counts": r["bias_counts"],
        "regime_counts": r["regime_counts"],
        "setup_candidates": r["setup_candidates"],
        "direction_blocked": r["direction_blocked"],
        "fills": r["fills"],
        "campaigns_started": r["campaigns_started"],
        "campaigns_with": r["campaigns_with"],
        "campaigns_no_trade": r["campaigns_no_trade"],
        "friction_rejections": r["friction_rejections"],
        "alloc_rejections": r["alloc_rejections"],
        "exclusions": r["exclusions"],
        "overall_metrics": overall_metrics.__dict__,
        "by_setup_metrics": {k: v.__dict__ for k, v in by_setup_metrics.items()},
        "by_direction_metrics": {k: v.__dict__ for k, v in by_direction_metrics.items()},
        "by_regime_metrics": {k: v.__dict__ for k, v in by_regime_metrics.items()},
        "by_session_metrics": {k: v.__dict__ for k, v in by_session_metrics.items()},
        "by_exit_reason_metrics": {k: v.__dict__ for k, v in by_exit_reason_metrics.items()},
        "reproducibility": {
            "run_1_sample_count": len(run1["all_samples"]), "run_2_sample_count": len(run2["all_samples"]),
            "field_comparison": field_comparison,
        },
        "gen001_cross_population_parity_check": gen001_parity,
        "lifecycle_reconciliation": control_reconcile(r["lifecycle_records"]),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "wp2_baseline_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8",
    )
    (OUT_DIR / "wp2_run1_lifecycle_population.json").write_text(
        json.dumps(run1_records, indent=2, sort_keys=True), encoding="utf-8",
    )
    (OUT_DIR / "wp2_run2_lifecycle_population.json").write_text(
        json.dumps(run2_records, indent=2, sort_keys=True), encoding="utf-8",
    )
    print(json.dumps(report, indent=2, default=str))
    return report


if __name__ == "__main__":
    main()
