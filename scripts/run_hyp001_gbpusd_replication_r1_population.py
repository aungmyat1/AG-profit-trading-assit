"""AG SSC HYP_001_GBPUSD_REPLICATION_R1 -- Gate 2: canonical population generation only.

Mirrors scripts/run_hyp002_gen002_population_attempt2.py's population-generation
method exactly (same frozen v1.0.0 detector/config, same H1-warmup-plus-decision
bias-resolution pattern, same determinism double-run, same population hashing via
research.session_lifecycle.population_hash), substituting GBPUSD for EURUSD and this
lane's own frozen window/hashes. Deliberately does NOT compute or write any economic
metric (net_expectancy_R, gross_R, profit_factor, etc.) -- this is Gate 2 only, per
HYP_001_GBPUSD_REPLICATION_R1_PREREGISTRATION.md's cumulative-evidence / adequacy-gate
separation (mirrored from the EURUSD HYP_001 confirmation protocol's own Gate-2/Gate-3
split). A separate, explicit script performs Gate 3 (economic evaluation) and refuses
to run below the frozen minimum_N=20.

RESEARCH ONLY. Places no orders. Touches no demo_eligible/demo_authorized/
live_authorized field. Changes no strategy parameter. Does not access holdout. Does
not touch EURUSD HYP_001/CONFIRM_001 in any way.
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
from historical_replay.symbol_metadata_manifest import (  # noqa: E402
    load_symbol_metadata_manifest,
    validate_manifest_for_dataset,
)
from historical_replay.utc_export_csv_loader import load_utc_export_csv  # noqa: E402
from historical_replay.warmup_readiness import sufficient_h1_warmup  # noqa: E402
from research.session_lifecycle import (  # noqa: E402
    compare_lifecycle_records, lifecycle_record, population_hash,
)
from session_sweep_continuation.config import compute_config_hash, load_config  # noqa: E402
from session_sweep_continuation.h1_bias import resolve_h1_market_bias  # noqa: E402
from session_sweep_continuation.replay import run_replay  # noqa: E402
from session_sweep_continuation.sessions import session_windows_from_config  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SYMBOL = "GBPUSD"
PIP_SIZE = 0.0001
PIP_VALUE_PER_LOT = 10.0
STRUCTURE_WARMUP_H1_BARS = 1000  # frozen, unchanged

GEN002_ROOT = REPO_ROOT / "data" / "research" / "ssc_fresh_dev" / "SSC_FRESH_DEV_GEN_002_MT5_20260801_20260914" / "raw"
M15_CSV = GEN002_ROOT / "GBPUSD_M15.csv"
M1_CSV = GEN002_ROOT / "GBPUSD_M1.csv"
COMBINED_H1_CSV = REPO_ROOT / "artifacts" / "validation" / "ST_SESSION_SWEEP_CONTINUATION_V1" / \
    "HYP_001_GBPUSD_REPLICATION_R1" / "GBPUSD_H1_WARMUP_PLUS_R1.csv"

H1_MANIFEST_PATH = REPO_ROOT / "config" / "historical_datasets" / "GBPUSD_H1_WARMUP_PLUS_R1_symbol_metadata.yaml"

PREREGISTRATION_HASH = "b401e9745e1be90b5a510e41c60923a79262fa9907a6dc49d7d92ee4c7a2853e"  # DRAFT hash; frozen hash recorded separately once frozen
DATASET_FINGERPRINT = "f8108d37448cae8f9fe2f16a9905abdf8991ac916cf4a497b11eaca2debbf5aa"  # GEN_002 admission event, unchanged (shared EURUSD+GBPUSD admission)
PARENT_CONFIG_HASH = "e0cf113b2e1e6b82fedee02e744615aa8f30ff7962355c331cbbdfd581fdcfbf"
PARENT_RAW_SHA256 = "c92311c3c1789a2ea01495a82a1fbcba1d877a8fb4d9ac46732f39e0b81970a9"

EXPECTED_SHA256 = {
    M15_CSV: "71a67d9d6dd984395e98473d9e265508b6bde32eeeb60c6331d4a6dad8ab3636",
    M1_CSV: "41a403a738060131f2be40d16cd048dd5161c934bb1bdc2f2d06f2a46862ef30",
    COMBINED_H1_CSV: "06e904873e02b4f122cdad139c534b4ea7c39202a7930cefc3a0ce0add126862",
}

DECISION_WINDOW_START = datetime(2026, 8, 3, 0, 0, 0, tzinfo=timezone.utc)
DECISION_WINDOW_END = datetime(2026, 9, 14, 23, 59, 59, tzinfo=timezone.utc)

POPULATION_DIR = REPO_ROOT / "artifacts" / "validation" / "ST_SESSION_SWEEP_CONTINUATION_V1" / \
    "HYP_001_GBPUSD_REPLICATION_R1" / "POPULATION"
MINIMUM_TREATMENT_N = 20


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


def _effective_date_range(h1_candles, m15_report, m1_report, config: dict):
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


def run_all_cycles(dates, session_pairs, windows, h1_store, h1_manifest, m15_candles, m1_candles, config):
    lifecycle_records = []
    setup_counts = {"S1": 0, "S2": 0, "S3": 0}
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
                assert str(entry_time) >= "2026-08-03", "occurrence entry_time before decision window -- must never happen"
                trade_id = f"{pair_id}_{d}_{entry_time}_{model}"
                setup_counts[key] += 1
                lifecycle_records.append(lifecycle_record(
                    entry_dict, trade_id=trade_id, strategy_id="ST_SESSION_SWEEP_CONTINUATION_V1",
                    strategy_version=config.get("version", "1.0.0"), symbol=SYMBOL,
                ))
            print(f"cycle {decision_cycles}/{len(dates) * len(session_pairs)} "
                  f"date={d} pair={pair_id} regime={result.regime} bias={label} occurrences_so_far={len(lifecycle_records)}",
                  file=sys.stderr, flush=True)

    return {"lifecycle_records": lifecycle_records, "setup_counts": setup_counts,
            "regime_counts": regime_counts, "bias_counts": bias_counts, "decision_cycles": decision_cycles}


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

    assert h1_report.start_utc < DECISION_WINDOW_START
    warmup_bars_in_h1 = sum(1 for c in h1_candles if c.time < DECISION_WINDOW_START)
    print(f"H1 series: {len(h1_candles)} total bars ({warmup_bars_in_h1} strictly before decision window)", file=sys.stderr)

    h1_store = HistoricalCandleStore()
    h1_store.load_series(SYMBOL, "H1", h1_candles)

    dates = _effective_date_range(h1_candles, m15_report, m1_report, config)
    session_pairs = [p["pair_id"] for p in config.get("session_pairs", ())]
    windows = session_windows_from_config(config)

    if not dates:
        raise SystemExit("EFFECTIVE_REPLAY_WINDOW_EMPTY -- unexpected, investigate before continuing")

    print(f"Running replay across {len(dates)} dates x {len(session_pairs)} session_pairs...", file=sys.stderr)
    run1 = run_all_cycles(dates, session_pairs, windows, h1_store, h1_manifest, m15_candles, m1_candles, config)
    print("Running replay again for determinism check...", file=sys.stderr)
    run2 = run_all_cycles(dates, session_pairs, windows, h1_store, h1_manifest, m15_candles, m1_candles, config)

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
        raise SystemExit(f"POPULATION_NONDETERMINISTIC: {field_comparison}")

    records = run1["lifecycle_records"]
    if len({rec["trade_id"] for rec in records}) != len(records):
        raise SystemExit("DUPLICATE_OCCURRENCE_ID: duplicate occurrence_id detected in canonical population")

    POPULATION_DIR.mkdir(parents=True, exist_ok=True)
    (POPULATION_DIR / "canonical_population.json").write_text(
        json.dumps(records, indent=2, sort_keys=True, default=str), encoding="utf-8")
    pop_hash = population_hash(records)

    total_n = len(records)
    s1_n = run1["setup_counts"]["S1"]
    s2_n = run1["setup_counts"]["S2"]
    s3_n = run1["setup_counts"]["S3"]
    treatment_n = s1_n + s2_n + s3_n  # CONTROL and TREATMENT differ only by exit policy (Section 4/6 of the
    # preregistration) -- unlike HYP_002's setup-admission filter, HYP_001's TREATMENT admits the SAME
    # occurrences as CONTROL (S1+S2+S3), so TREATMENT_N == CONTROL_N == TOTAL_N by construction here.
    assert treatment_n == total_n, "TREATMENT_N must equal TOTAL_N for an exit-only mechanism"

    adequacy = "ADEQUATE" if treatment_n >= MINIMUM_TREATMENT_N else "INCONCLUSIVE_INSUFFICIENT_SAMPLE"

    pop_manifest = {
        "population_id": "HYP_001_GBPUSD_REPLICATION_R1_POPULATION",
        "strategy_id": "ST_SESSION_SWEEP_CONTINUATION_V1", "strategy_version": config.get("version", "1.0.0"),
        "symbol": SYMBOL,
        "total_n": total_n, "s1_n": s1_n, "s2_n": s2_n, "s3_n": s3_n, "treatment_n": treatment_n,
        "minimum_treatment_n": MINIMUM_TREATMENT_N, "adequacy": adequacy,
        "population_hash": pop_hash,
        "dataset_fingerprint": DATASET_FINGERPRINT, "preregistration_hash": PREREGISTRATION_HASH,
        "parent_config_hash": PARENT_CONFIG_HASH, "parent_raw_sha256": PARENT_RAW_SHA256,
        "combined_h1_sha256": h1_sha, "m15_sha256": m15_sha, "m1_sha256": m1_sha,
        "h1_symbol_metadata_fingerprint": h1_manifest.dataset_fingerprint,
        "config_hash": config_hash, "git_commit_before": git_commit,
        "decision_cycles": run1["decision_cycles"], "regime_counts": run1["regime_counts"],
        "bias_counts": run1["bias_counts"], "dates_admitted": len(dates),
        "reproducibility": field_comparison,
        "economics_computed": False,
        "note": "Gate 2 (population + adequacy) only. No net_R/gross_R/expectancy/profit_factor/drawdown "
                "computed or stored in this artifact -- economic evaluation is a separate, explicit Gate-3 "
                "script that refuses to run below minimum_treatment_n.",
    }
    (POPULATION_DIR / "population_manifest.json").write_text(
        json.dumps(pop_manifest, indent=2, sort_keys=True, default=str), encoding="utf-8")

    print(json.dumps(pop_manifest, indent=2, default=str))


if __name__ == "__main__":
    main()
