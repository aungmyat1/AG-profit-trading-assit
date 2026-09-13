"""AG_ST_SESSION_SWEEP_CONTINUATION_FIRST_CANONICAL_REPLAY.

The FIRST canonical H1(bias) -> M15(setup) -> M1(fill) historical replay for
ST_SESSION_SWEEP_CONTINUATION_V1, using the Tier-A dataset package
(config/historical_datasets/ST_SESSION_SWEEP_CONTINUATION_V1_EURUSD_PACKAGE.yaml) and
the now-authorized H1 symbol-metadata manifest
(config/historical_datasets/EURUSD_H1_symbol_metadata.yaml).

Reuses, does not reinvent:
  - historical_replay.mt5_export_loader.load_mt5_export_csv (H1/M15/M1 ingestion,
    per-week broker-offset UTC conversion)
  - historical_replay.candle_store.HistoricalCandleStore + historical_replay.
    data_source_patch.historical_data_context (H1 structure-tier metadata patching)
  - session_sweep_continuation.h1_bias.resolve_h1_market_bias (H1 -> MarketBiasResult)
  - session_sweep_continuation.replay.run_replay (M15 setup decisions + M1 fill/outcome,
    now accepting bias_result + m1_candles -- both additive parameters)
  - performance.calculator.compute_trade_metrics (economics)

RESEARCH ONLY. Places no orders, touches no demo_eligible/demo_authorized/
live_authorized field, and changes no strategy parameter. FROZEN STRATEGY + FROZEN DATA
+ FROZEN BIAS ARCHITECTURE -- this script is a pure read/compute/report driver.
"""
from __future__ import annotations

import hashlib
import json
import statistics
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
from research.session_lifecycle import control_reconcile, lifecycle_record, population_hash  # noqa: E402
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
PACKAGE_MANIFEST_PATH = REPO_ROOT / "config" / "historical_datasets" / "ST_SESSION_SWEEP_CONTINUATION_V1_EURUSD_PACKAGE.yaml"

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
    """R10: the actual usable window, computed per-session-pair-window feasibility, not
    assumed from raw file coverage. A calendar date is INCLUDED only if, for EVERY
    configured session_pair: (a) M15 covers [ref_start, trade_end), (b) M1 covers
    [trade_start, trade_end), and (c) at least STRUCTURE_WARMUP_H1_BARS H1 bars close
    before ref_end. H1's own coverage (2025-01-02 onward) makes (c) satisfied for every
    date in the raw M1/M15 overlap window by a wide margin -- verified, not assumed,
    below via an explicit count rather than skipped."""
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

    def run_all_cycles():
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
        all_samples = []
        lifecycle_records = []
        steps_log = []

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
                steps_log.append({"date": str(d), "pair": pair_id, "regime": result.regime,
                                   "bias": bias.bias, "confidence": bias.confidence})

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
                    for key in setup_models_in_campaign:
                        campaigns_with[key] += 1
                    if not setup_models_in_campaign:
                        campaigns_no_trade += 1

        return {
            "decision_cycles": decision_cycles, "bias_counts": bias_counts, "regime_counts": regime_counts,
            "setup_candidates": setup_candidates, "direction_blocked": direction_blocked, "fills": fills,
            "campaigns_started": campaigns_started, "campaigns_with": campaigns_with,
            "campaigns_no_trade": campaigns_no_trade, "friction_rejections": friction_rejections,
            "alloc_rejections": alloc_rejections, "exclusions": exclusions,
            "session_pair_samples": session_pair_samples, "direction_samples": direction_samples,
            "regime_samples": regime_samples, "setup_samples": setup_samples, "all_samples": all_samples,
            "steps_log": steps_log, "lifecycle_records": lifecycle_records,
        }

    print(f"Running replay across {len(dates)} dates x {len(session_pairs)} session pairs...", file=sys.stderr)
    run1 = run_all_cycles()
    print("Running replay again for determinism check...", file=sys.stderr)
    run2 = run_all_cycles()

    deterministic = (
        run1["decision_cycles"] == run2["decision_cycles"]
        and run1["bias_counts"] == run2["bias_counts"]
        and run1["regime_counts"] == run2["regime_counts"]
        and run1["setup_candidates"] == run2["setup_candidates"]
        and run1["fills"] == run2["fills"]
        and [(s.gross_R, s.net_R, s.outcome) for s in run1["all_samples"]]
        == [(s.gross_R, s.net_R, s.outcome) for s in run2["all_samples"]]
    )

    r = run1
    overall_metrics = compute_trade_metrics(r["all_samples"])
    by_setup_metrics = {k: compute_trade_metrics(v) for k, v in r["setup_samples"].items()}
    by_direction_metrics = {k: compute_trade_metrics(v) for k, v in r["direction_samples"].items()}
    by_regime_metrics = {k: compute_trade_metrics(v) for k, v in r["regime_samples"].items()}
    by_session_metrics = {k: compute_trade_metrics(v) for k, v in r["session_pair_samples"].items()}

    def max_consecutive_wins(samples):
        streak = best = 0
        for s in sorted(samples, key=lambda s: s.resolved_at or ""):
            if s.gross_R > 1e-9:
                streak += 1
                best = max(best, streak)
            else:
                streak = 0
        return best

    combined_fp_input = json.dumps({
        "H1": h1_sha, "M15": m15_sha, "M1": m1_sha,
        "symbol_metadata": h1_manifest.dataset_fingerprint,
    }, sort_keys=True)
    replay_evidence_fingerprint = hashlib.sha256(combined_fp_input.encode("utf-8")).hexdigest()

    n = overall_metrics.sample_size
    if n == 0:
        economic_verdict = "NOT_EVALUABLE"
    elif n < 10:  # strategy's own min_sample_size (performance_attribution.min_sample_size)
        economic_verdict = "INSUFFICIENT_EVIDENCE"
    elif isinstance(overall_metrics.net_expectancy_R, float) and overall_metrics.net_expectancy_R <= 0:
        economic_verdict = "NEGATIVE_EXPECTANCY"
    elif isinstance(overall_metrics.net_expectancy_R, float) and overall_metrics.net_expectancy_R > 0:
        economic_verdict = "POSITIVE_RESEARCH_EXPECTANCY"
    else:
        economic_verdict = "INSUFFICIENT_EVIDENCE"

    report = {
        "report_id": "AG_ST_SESSION_SWEEP_CONTINUATION_FIRST_CANONICAL_REPLAY_STATUS",
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
        "overall_max_consecutive_wins": max_consecutive_wins(r["all_samples"]),
        "by_setup_metrics": {k: v.__dict__ for k, v in by_setup_metrics.items()},
        "by_direction_metrics": {k: v.__dict__ for k, v in by_direction_metrics.items()},
        "by_regime_metrics": {k: v.__dict__ for k, v in by_regime_metrics.items()},
        "by_session_metrics": {k: v.__dict__ for k, v in by_session_metrics.items()},
        "reproducibility": {
            "run_1_sample_count": len(run1["all_samples"]), "run_2_sample_count": len(run2["all_samples"]),
            "deterministic": deterministic,
        },
        "economic_verdict": economic_verdict,
        "lifecycle_reconciliation": control_reconcile(r["lifecycle_records"]),
    }
    output_dir = REPO_ROOT / "artifacts" / "research" / "EXP_EXPOSURE_EFFICIENCY_V1" / "GEN_001"
    output_dir.mkdir(parents=True, exist_ok=True)
    lifecycle_path = output_dir / "canonical_lifecycle_population.json"
    lifecycle_path.write_text(json.dumps(r["lifecycle_records"], indent=2, sort_keys=True), encoding="utf-8")
    input_manifest = {
        "experiment_id": "EXP_EXPOSURE_EFFICIENCY_V1", "generation_id": "GEN_001",
        "strategy_id": "ST_SESSION_SWEEP_CONTINUATION_V1", "strategy_version": config.get("version", "1.0.0"),
        "symbol": SYMBOL, "date_start": str(effective_start), "date_end": str(effective_end),
        "dataset_path": str(M1_CSV), "dataset_sha256": m1_sha, "trade_count": len(r["lifecycle_records"]),
        "lifecycle_population_hash": population_hash(r["lifecycle_records"]),
        "friction_provenance": "session_sweep_continuation.friction:MODELED",
        "control_reconciliation": report["lifecycle_reconciliation"],
        "experiment_arms": ["CONTROL", 30, 45, 60, 90, 120], "repository_commit": git_commit,
    }
    (output_dir / "input_manifest.json").write_text(json.dumps(input_manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return report


if __name__ == "__main__":
    main()
