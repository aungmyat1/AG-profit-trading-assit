"""AG SSC HYP_002_SETUP_SELECTIVITY -- Stage 2 ATTEMPT 2 (warmup-corrected).

Identical to run_hyp002_gen002_population.py (Attempt 1) except:
  1. H1 is loaded from the combined warmup+decision evaluation-input series
     (artifacts/validation/.../HYP_002_EVALUATION_INPUT/EURUSD_H1_WARMUP_PLUS_GEN002.csv)
     instead of GEN_002's decision-window-only H1 file, so the frozen bias resolver has
     enough trailing H1 history to compute a real bias.
  2. The effective-date-range warmup check uses historical_replay.warmup_readiness.
     sufficient_h1_warmup (ACTUAL closed H1 bar count) instead of the elapsed-calendar-
     hours approximation Attempt 1 used (copied verbatim from the GEN_001 driver).
  3. M15/M1 are loaded from GEN_002 ONLY, unchanged -- the decision interval
     (2026-08-01T00:00:00Z -> 2026-09-14T23:59:59Z) is therefore structurally unchanged:
     no M15/M1 candle exists before 2026-08-03, so no decision cycle can occur before
     the frozen decision window regardless of how much H1 warmup history is loaded.

Warmup bars (< 2026-08-01T00:00:00Z) are used ONLY to populate the H1
HistoricalCandleStore for state initialization -- resolve_h1_market_bias's own no-
lookahead `historical_data_context` guarantees no bar at/after a decision's own
`ref_end` is used for that decision, exactly as for GEN_001/Attempt-1. This script adds
no new occurrence/trade source: run_replay is only ever invoked for dates the M15/M1
GEN_002 coverage admits (2026-08-01 .. 2026-09-14 inclusive), identical to Attempt 1.

RESEARCH ONLY. Places no orders. Touches no demo_eligible/demo_authorized/
live_authorized field. Changes no strategy parameter. Does not access holdout.
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
from historical_replay.symbol_metadata_manifest import (  # noqa: E402
    load_symbol_metadata_manifest,
    validate_manifest_for_dataset,
)
from historical_replay.utc_export_csv_loader import load_utc_export_csv  # noqa: E402
from historical_replay.warmup_readiness import sufficient_h1_warmup  # noqa: E402
from performance.calculator import compute_trade_metrics  # noqa: E402
from performance.models import ResolvedTradeSample  # noqa: E402
from research.session_lifecycle import (  # noqa: E402
    compare_lifecycle_records, lifecycle_record, population_hash,
)
from session_sweep_continuation.config import compute_config_hash, load_config  # noqa: E402
from session_sweep_continuation.h1_bias import resolve_h1_market_bias  # noqa: E402
from session_sweep_continuation.replay import run_replay  # noqa: E402
from session_sweep_continuation.sessions import session_windows_from_config  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SYMBOL = "EURUSD"
PIP_SIZE = 0.0001
PIP_VALUE_PER_LOT = 10.0
STRUCTURE_WARMUP_H1_BARS = 1000  # frozen, unchanged

GEN002_ROOT = REPO_ROOT / "data" / "research" / "ssc_fresh_dev" / "SSC_FRESH_DEV_GEN_002_MT5_20260801_20260914" / "raw"
M15_CSV = GEN002_ROOT / "EURUSD_M15.csv"
M1_CSV = GEN002_ROOT / "EURUSD_M1.csv"
COMBINED_H1_CSV = REPO_ROOT / "artifacts" / "validation" / "ST_SESSION_SWEEP_CONTINUATION_V1" / \
    "HYP_002_EVALUATION_INPUT" / "EURUSD_H1_WARMUP_PLUS_GEN002.csv"

H1_MANIFEST_PATH = REPO_ROOT / "config" / "historical_datasets" / "EURUSD_H1_WARMUP_PLUS_GEN002_symbol_metadata.yaml"

PREREGISTRATION_HASH = "4e2e4f21c8bf2fe5b461b29ceff670e769445be913d3f193a73e96cc84492fb7"
DATASET_FINGERPRINT = "f8108d37448cae8f9fe2f16a9905abdf8991ac916cf4a497b11eaca2debbf5aa"  # GEN_002 decision data, unchanged
PARENT_CONFIG_HASH = "e0cf113b2e1e6b82fedee02e744615aa8f30ff7962355c331cbbdfd581fdcfbf"
PARENT_RAW_SHA256 = "c92311c3c1789a2ea01495a82a1fbcba1d877a8fb4d9ac46732f39e0b81970a9"

EXPECTED_SHA256 = {
    COMBINED_H1_CSV: "0ce051944a2ff8e58c362aabf4ab25012b0936ddaf260108f5a4aca2eb46430f",
    M15_CSV: "3f0702eb50e67f8f9c534b30b69eafdb5620bc8d6e11defb6d8ccd47b76209e8",
    M1_CSV: "4cc01e2b185e714332cc5f1c4d253b579ee74085dd742903d0e9e3938906f332",
}

DECISION_WINDOW_START = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
DECISION_WINDOW_END = datetime(2026, 9, 14, 23, 59, 59, tzinfo=timezone.utc)

POPULATION_DIR = REPO_ROOT / "artifacts" / "validation" / "ST_SESSION_SWEEP_CONTINUATION_V1" / "HYP_002_POPULATION_ATTEMPT_2"
ECONOMIC_DIR = REPO_ROOT / "artifacts" / "validation" / "ST_SESSION_SWEEP_CONTINUATION_V1" / "HYP_002_ECONOMIC_RESULT_ATTEMPT_2"


def _git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except Exception:
        return "UNKNOWN"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify_fingerprint(path: Path) -> str:
    if not path.exists():
        raise SystemExit(f"DATASET_MISSING: {path}")
    actual = _sha256(path)
    expected = EXPECTED_SHA256[path]
    if actual != expected:
        raise SystemExit(f"FINGERPRINT_MISMATCH: {path}: actual={actual} expected={expected}")
    return actual


def _effective_date_range_bar_count(h1_candles, m15_report, m1_report, config: dict):
    """Same structural contract as the calendar-hour version, except the H1 warmup leg
    uses historical_replay.warmup_readiness.sufficient_h1_warmup (actual closed bar
    count) instead of `h1_report.start_utc + timedelta(hours=1000) <= ref_end`. The
    M15/M1 coverage checks are unchanged -- these already bound every admitted date to
    the frozen GEN_002 decision window (M15/M1 contain no bar before 2026-08-03)."""
    windows = session_windows_from_config(config)
    raw_start = max(m15_report.start_utc, m1_report.start_utc, DECISION_WINDOW_START)
    raw_end = min(m15_report.end_utc, m1_report.end_utc, DECISION_WINDOW_END)

    covered_dates = []
    d = raw_start.date()
    while datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc) <= raw_end:
        ok = True
        for pair_id, w in windows.items():
            ref_start, ref_end = w["reference"].bounds_for_date(d)
            trade_start, trade_end = w["trade"].bounds_for_date(d)
            if ref_start < DECISION_WINDOW_START or trade_end > DECISION_WINDOW_END:
                ok = False
                break
            if not (m15_report.start_utc <= ref_start and trade_end <= m15_report.end_utc):
                ok = False
                break
            if not (m1_report.start_utc <= trade_start and trade_end <= m1_report.end_utc):
                ok = False
                break
            if not sufficient_h1_warmup(h1_candles, ref_end, STRUCTURE_WARMUP_H1_BARS):
                ok = False
                break
        if ok:
            covered_dates.append(d)
        d = d + timedelta(days=1)

    return covered_dates


def _setup_key(model: str) -> str:
    return "S1" if model.startswith("S1") else "S2" if model.startswith("S2") else "S3"


def _bootstrap_delta_ci(paired, n_resamples=2000, seed=1337):
    """`paired`: list of (net_R, is_treatment) -- one entry per occurrence in the SAME
    frozen population. Each resample draws WITH replacement from this single list
    (preserving the nested CONTROL/TREATMENT relationship: TREATMENT is a subset of
    CONTROL, never an independent sample), then recomputes both arms' mean net_R from
    that resample."""
    import random
    rng = random.Random(seed)
    n = len(paired)
    if n == 0:
        return {"note": "population empty", "ci_90": None}
    deltas = []
    for _ in range(n_resamples):
        sample = [paired[rng.randrange(n)] for _ in range(n)]
        control_vals = [r for r, _ in sample if r is not None]
        treatment_vals = [r for r, is_t in sample if is_t and r is not None]
        if control_vals and treatment_vals:
            deltas.append((sum(treatment_vals) / len(treatment_vals)) - (sum(control_vals) / len(control_vals)))
    if not deltas:
        return {"note": "no resample produced both arms", "ci_90": None}
    deltas.sort()
    lo = deltas[int(0.05 * len(deltas))]
    hi = deltas[int(0.95 * len(deltas)) - 1]
    return {"n_resamples": len(deltas), "ci_90": [lo, hi], "median_delta": statistics.median(deltas)}


def main():
    config = load_config(repo_root=str(REPO_ROOT))
    config_hash = compute_config_hash(config)
    if config_hash != PARENT_CONFIG_HASH:
        raise SystemExit(f"PARENT_CONFIG_HASH_MISMATCH: {config_hash} != {PARENT_CONFIG_HASH}")
    git_commit = _git_commit()

    h1_sha = _verify_fingerprint(COMBINED_H1_CSV)
    m15_sha = _verify_fingerprint(M15_CSV)
    m1_sha = _verify_fingerprint(M1_CSV)

    h1_manifest = load_symbol_metadata_manifest(H1_MANIFEST_PATH)
    if h1_manifest.authority != "OWNER_APPROVED_DATASET_MANIFEST":
        raise SystemExit(f"H1_METADATA_NOT_AUTHORIZED: authority={h1_manifest.authority!r}")
    validate_manifest_for_dataset(h1_manifest, COMBINED_H1_CSV, SYMBOL)

    print("Loading combined H1 (warmup + decision window)...", file=sys.stderr)
    h1_candles, h1_report = load_utc_export_csv(str(COMBINED_H1_CSV), SYMBOL, "H1")
    print("Loading M15 (decision window only)...", file=sys.stderr)
    m15_candles, m15_report = load_utc_export_csv(str(M15_CSV), SYMBOL, "M15")
    print("Loading M1 (decision window only)...", file=sys.stderr)
    m1_candles, m1_report = load_utc_export_csv(str(M1_CSV), SYMBOL, "M1")

    for report, label in ((h1_report, "H1"), (m15_report, "M15"), (m1_report, "M1")):
        if report.normalized_timezone != "UTC":
            raise SystemExit(f"{label}_TIMEZONE_NOT_UTC: {report.normalized_timezone}")

    # No warmup bar reaches into or past the decision window.
    assert h1_report.start_utc < DECISION_WINDOW_START
    warmup_bars_in_h1 = sum(1 for c in h1_candles if c.time < DECISION_WINDOW_START)
    print(f"H1 series: {len(h1_candles)} total bars ({warmup_bars_in_h1} strictly before decision window)", file=sys.stderr)

    h1_store = HistoricalCandleStore()
    h1_store.load_series(SYMBOL, "H1", h1_candles)

    dates = _effective_date_range_bar_count(h1_candles, m15_report, m1_report, config)
    session_pairs = [p["pair_id"] for p in config.get("session_pairs", ())]
    windows = session_windows_from_config(config)

    if not dates:
        result = {
            "final_verdict_note": "EFFECTIVE_REPLAY_WINDOW_EMPTY even with warmup context -- unexpected, investigate.",
            "hyp002_result": "INCONCLUSIVE", "treatment_n": 0,
        }
        _finish(config, config_hash, git_commit, h1_sha, m15_sha, m1_sha, h1_manifest, result,
                run1=None, run2=None, control_metrics=None, treatment_metrics=None)
        return

    def run_all_cycles():
        lifecycle_records = []
        all_samples = []
        setup_samples = {"S1": [], "S2": [], "S3": []}
        regime_counts = {}
        bias_counts = {"BULLISH": 0, "BEARISH": 0, "NEUTRAL": 0, "UNAVAILABLE": 0}
        decision_cycles = 0

        for d in dates:
            for pair_id in session_pairs:
                decision_cycles += 1
                ref_end = windows[pair_id]["reference"].bounds_for_date(d)[1]
                assert ref_end >= DECISION_WINDOW_START, "decision cycle before frozen decision window -- must never happen"
                bias = resolve_h1_market_bias(h1_store, h1_manifest, SYMBOL, ref_end, pair_id)
                label = bias.bias if bias.confidence != "UNAVAILABLE" else "UNAVAILABLE"
                bias_counts[label] = bias_counts.get(label, 0) + 1

                result = run_replay(
                    m15_candles, config, SYMBOL, pair_id, d, PIP_SIZE, PIP_VALUE_PER_LOT,
                    bias_result=bias, m1_candles=m1_candles,
                )
                if result.regime is None or result.regime == "UNKNOWN":
                    regime_counts["UNKNOWN"] = regime_counts.get("UNKNOWN", 0) + 1
                    continue
                regime_counts[result.regime] = regime_counts.get(result.regime, 0) + 1

                if result.campaign is None:
                    continue
                for entry_dict in result.accepted_setups:
                    model = entry_dict["setup_model"]
                    key = _setup_key(model)
                    outcome = entry_dict["outcome"]
                    if outcome["terminal_state"] == "AMBIGUOUS_SEQUENCE" or outcome["gross_R"] is None:
                        continue
                    entry_time = entry_dict["entry_time"]
                    assert str(entry_time) >= "2026-08-01", "occurrence entry_time before decision window -- must never happen"
                    trade_id = f"{pair_id}_{d}_{entry_time}_{model}"
                    sample = ResolvedTradeSample(
                        source_record_id=trade_id, source_path="session_sweep_continuation.replay.run_replay",
                        strategy_id="ST_SESSION_SWEEP_CONTINUATION_V1", strategy_version=config.get("version", "1.0.0"),
                        symbol=SYMBOL, cycle=pair_id, resolved_at=entry_time,
                        gross_R=outcome["gross_R"], net_R=outcome["net_R"],
                        cost_status=outcome["cost_status"], outcome=outcome["terminal_state"],
                    )
                    all_samples.append(sample)
                    setup_samples[key].append(sample)
                    lifecycle_records.append(lifecycle_record(
                        entry_dict, trade_id=trade_id, strategy_id=sample.strategy_id,
                        strategy_version=sample.strategy_version, symbol=SYMBOL,
                    ))
                print(f"cycle {decision_cycles}/{len(dates) * len(session_pairs)} "
                      f"date={d} pair={pair_id} regime={result.regime} bias={label} occurrences_so_far={len(lifecycle_records)}",
                      file=sys.stderr, flush=True)

        return {"lifecycle_records": lifecycle_records, "all_samples": all_samples,
                "setup_samples": setup_samples, "regime_counts": regime_counts,
                "bias_counts": bias_counts, "decision_cycles": decision_cycles}

    print(f"Running replay across {len(dates)} dates x {len(session_pairs)} session_pairs "
          f"(warmup-corrected readiness check)...", file=sys.stderr)
    run1 = run_all_cycles()
    print("Running replay again for determinism check...", file=sys.stderr)
    run2 = run_all_cycles()

    hash1 = population_hash(run1["lifecycle_records"])
    hash2 = population_hash(run2["lifecycle_records"])
    field_comparison = compare_lifecycle_records(run1["lifecycle_records"], run2["lifecycle_records"])
    field_comparison["population_hash_equal"] = hash1 == hash2
    field_comparison["run_1_hash"] = hash1
    field_comparison["run_2_hash"] = hash2
    deterministic = (
        field_comparison.get("trade_count_equal", False)
        and field_comparison.get("occurrence_ids_equal", False)
        and field_comparison.get("field_level_equal", False)
        and field_comparison["population_hash_equal"]
    )
    if not deterministic:
        raise SystemExit(f"STOP_G2_FAIL: non-deterministic population across two identical runs: {field_comparison}")

    r = run1
    control_metrics = compute_trade_metrics(r["all_samples"])
    treatment_samples = r["setup_samples"]["S1"] + r["setup_samples"]["S2"]
    treatment_metrics = compute_trade_metrics(treatment_samples)
    by_setup_metrics = {k: compute_trade_metrics(v) for k, v in r["setup_samples"].items()}

    if len({rec["trade_id"] for rec in r["lifecycle_records"]}) != len(r["lifecycle_records"]):
        raise SystemExit("STOP_G2_FAIL: duplicate occurrence_id detected in canonical population")

    _finish(config, config_hash, git_commit, h1_sha, m15_sha, m1_sha, h1_manifest,
            {"decision_cycles": r["decision_cycles"], "regime_counts": r["regime_counts"],
             "bias_counts": r["bias_counts"], "dates_admitted": len(dates)},
            run1=r, run2=run2, control_metrics=control_metrics, treatment_metrics=treatment_metrics,
            field_comparison=field_comparison, treatment_samples=treatment_samples, by_setup_metrics=by_setup_metrics,
            setup_samples=r["setup_samples"])


def _finish(config, config_hash, git_commit, h1_sha, m15_sha, m1_sha, h1_manifest, meta,
            run1, run2, control_metrics, treatment_metrics, field_comparison=None,
            treatment_samples=None, by_setup_metrics=None, setup_samples=None):
    POPULATION_DIR.mkdir(parents=True, exist_ok=True)
    ECONOMIC_DIR.mkdir(parents=True, exist_ok=True)

    if run1 is None:
        (POPULATION_DIR / "canonical_population.json").write_text(json.dumps([], indent=2, sort_keys=True), encoding="utf-8")
        pop_manifest = {
            "population_id": "HYP_002_GEN_002_EURUSD_POPULATION_ATTEMPT_2", "trade_count": 0,
            "population_hash": population_hash([]), "attempt": 2, "note": meta["final_verdict_note"],
        }
        (POPULATION_DIR / "population_manifest.json").write_text(json.dumps(pop_manifest, indent=2, sort_keys=True), encoding="utf-8")
        economic = {"hyp002_result": "INCONCLUSIVE", "treatment_n": 0, "control_n": 0, "reason": meta["final_verdict_note"]}
        (ECONOMIC_DIR / "economic_evaluation.json").write_text(json.dumps(economic, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps({"population_manifest": pop_manifest, "economic_evaluation": economic}, indent=2, default=str))
        return

    records = run1["lifecycle_records"]
    (POPULATION_DIR / "canonical_population.json").write_text(json.dumps(records, indent=2, sort_keys=True), encoding="utf-8")
    pop_hash = population_hash(records)

    pop_manifest = {
        "population_id": "HYP_002_GEN_002_EURUSD_POPULATION_ATTEMPT_2",
        "strategy_id": "ST_SESSION_SWEEP_CONTINUATION_V1", "strategy_version": config.get("version", "1.0.0"),
        "attempt": 2,
        "trade_count": len(records), "population_hash": pop_hash,
        "dataset_fingerprint": DATASET_FINGERPRINT, "preregistration_hash": PREREGISTRATION_HASH,
        "parent_config_hash": PARENT_CONFIG_HASH, "parent_raw_sha256": PARENT_RAW_SHA256,
        "combined_h1_sha256": h1_sha, "m15_sha256": m15_sha, "m1_sha256": m1_sha,
        "h1_symbol_metadata_fingerprint": h1_manifest.dataset_fingerprint,
        "config_hash": config_hash, "git_commit_before": git_commit,
        "decision_cycles": meta["decision_cycles"], "regime_counts": meta["regime_counts"],
        "bias_counts": meta["bias_counts"], "dates_admitted": meta["dates_admitted"],
        "reproducibility": field_comparison,
    }
    (POPULATION_DIR / "population_manifest.json").write_text(json.dumps(pop_manifest, indent=2, sort_keys=True, default=str), encoding="utf-8")

    control_n = control_metrics.sample_size
    treatment_n = treatment_metrics.sample_size
    control_net = control_metrics.net_expectancy_R
    treatment_net = treatment_metrics.net_expectancy_R

    delta = None
    if isinstance(control_net, float) and isinstance(treatment_net, float):
        delta = treatment_net - control_net

    if treatment_n < 10:
        hyp002_result = "INCONCLUSIVE"
    elif delta is not None and delta > 0 and isinstance(treatment_net, float) and treatment_net > 0:
        hyp002_result = "PASS"
    else:
        hyp002_result = "FAIL"

    net_values_control = [s.net_R for s in run1["all_samples"] if s.net_R is not None]
    net_values_treatment = [s.net_R for s in treatment_samples if s.net_R is not None]
    secondary = {
        "median_net_R_control": statistics.median(net_values_control) if net_values_control else None,
        "std_net_R_control": statistics.pstdev(net_values_control) if len(net_values_control) > 1 else None,
        "median_net_R_treatment": statistics.median(net_values_treatment) if net_values_treatment else None,
        "std_net_R_treatment": statistics.pstdev(net_values_treatment) if len(net_values_treatment) > 1 else None,
        "bootstrap_delta_ci_90_NONDECISION": _bootstrap_delta_ci(
            [(s.net_R, key in ("S1", "S2")) for key, samples in (setup_samples or {}).items() for s in samples]
        ),
        "note": "SECONDARY / NON-DECISION diagnostics only -- do not alter hyp002_result.",
    }

    economic = {
        "hypothesis_id": "HYP_002_SETUP_SELECTIVITY", "attempt": 2,
        "population_hash": pop_hash, "dataset_fingerprint": DATASET_FINGERPRINT,
        "preregistration_hash": PREREGISTRATION_HASH,
        "control": {
            "definition": "S1+S2+S3", "n": control_n, "gross_expectancy_R": control_metrics.gross_expectancy_R,
            "net_expectancy_R": control_net, "net_total_R": control_metrics.net_total_R,
            "wins": control_metrics.wins, "losses": control_metrics.losses, "breakevens": control_metrics.breakevens,
            "win_rate": control_metrics.win_rate, "profit_factor": control_metrics.profit_factor,
            "max_drawdown_R": control_metrics.max_drawdown_R,
        },
        "treatment": {
            "definition": "S1+S2 only (S3 rejected)", "n": treatment_n,
            "gross_expectancy_R": treatment_metrics.gross_expectancy_R, "net_expectancy_R": treatment_net,
            "net_total_R": treatment_metrics.net_total_R,
            "wins": treatment_metrics.wins, "losses": treatment_metrics.losses, "breakevens": treatment_metrics.breakevens,
            "win_rate": treatment_metrics.win_rate, "profit_factor": treatment_metrics.profit_factor,
            "max_drawdown_R": treatment_metrics.max_drawdown_R,
        },
        "by_setup": {k: v.__dict__ for k, v in (by_setup_metrics or {}).items()},
        "delta_net_expectancy_R": delta,
        "decision_rule_applied": "PASS: N>=10 AND delta>0 AND TREATMENT_net>0 | FAIL: N>=10 AND (delta<=0 OR TREATMENT_net<=0) | INCONCLUSIVE: N<10",
        "hyp002_result": hyp002_result,
        "secondary_diagnostics": secondary,
    }
    (ECONOMIC_DIR / "economic_evaluation.json").write_text(json.dumps(economic, indent=2, sort_keys=True, default=str), encoding="utf-8")

    print(json.dumps({"population_manifest": pop_manifest, "economic_evaluation": economic}, indent=2, default=str))


if __name__ == "__main__":
    main()
