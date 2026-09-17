"""AG_SSC_HYP_001_ROUTE_B_PHASE1_OCCURRENCE_RECONSTRUCTION.

Phase 1 ONLY of the preregistered Route B reconstruction (commit 0fdeafd). Reconstructs
GEN_001 (EURUSD) and GEN_002A (GBPUSD) occurrence *identity* -- not outcome -- from their
admitted, hash-verified H1/M15/M1 datasets, using the frozen historical engine
(session_sweep_continuation.{h1_bias,replay,sessions}, unchanged since the historical
generation commits per H1_BIAS_AUTHORITY.md).

This script calls the SAME session_sweep_continuation.replay.run_replay used by the
original GEN_001/GEN_002A generation scripts (scripts/run_first_canonical_session_sweep_
continuation_replay.py, scripts/run_gen_002a_gbpusd_session_sweep_continuation_replay.py)
so that occurrence admission (setup eligibility, direction, entry, stop) is reproduced
by the actual unmodified engine, not reimplemented. reference_high/reference_low are
obtained by calling session_sweep_continuation.sessions.build_reference_session directly
with the identical arguments run_replay itself uses internally (sessions.py:165) --
a pure, side-effect-free read, not a reimplementation of any decision logic.

Deliberately DISCARDED from every occurrence record: outcome, gross_R, net_R, friction
components, terminal_state, cost_status -- Phase 1 must not calculate or consult CONTROL
or TREATMENT economics. run_replay's own internal call to resolve_campaign_entry (which
DOES receive runner_target_r=3.0 from the frozen v1.0.1 config, because run_replay is a
single monolithic function) is consulted only for the outcome fields this script then
discards; per PAIRED_OCCURRENCE_PROOF (recovery audit 04c3cb4) and direct inspection of
replay.py:303-360, occurrence admission (setup_model/direction/entry_price/stop_price/
reference_high/reference_low) is fully resolved BEFORE that call and does not depend on
its runner_target_r argument.

RESEARCH ONLY. Places no orders. Calculates no CONTROL/TREATMENT R. Touches no strategy
file, no demo/live authority field.
"""
from __future__ import annotations

import hashlib
import json
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
from session_sweep_continuation.config import compute_config_hash, load_config  # noqa: E402
from session_sweep_continuation.h1_bias import resolve_h1_market_bias  # noqa: E402
from session_sweep_continuation.replay import run_replay  # noqa: E402
from session_sweep_continuation.sessions import (  # noqa: E402
    build_reference_session, session_windows_from_config,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
STRUCTURE_WARMUP_H1_BARS = 1000
PIP_SIZE = 0.0001
PIP_VALUE_PER_LOT = 10.0

GENERATIONS = {
    "GEN_001": dict(
        symbol="EURUSD",
        h1=Path(r"D:\EURUSD_H1_202501020000_202607310000.csv"),
        m15=Path(r"D:\EURUSD_M15_202501020000_202606192345.csv"),
        m1=Path(r"D:\EURUSD_M1_202605180946_202607312356.csv"),
        h1_manifest=REPO_ROOT / "config" / "historical_datasets" / "EURUSD_H1_symbol_metadata.yaml",
        expected_h1="f1b456e4b50215ad23370949f15faaa8548f9c03053a20d8974d6e9fd480a060",
        expected_m15="7f7502938862f4a3779f018caab468fe4445a4d8c676c8393dc29ca57fc43a65",
        expected_m1="55422a1ccdf4ca76fd25451fbf849d559bed45d839891a3ada7a37f9f7dd6a23",
        historical_population_hash="8e32a7498e5a1c7df6658e6700ff3386fb38821ed189619a20224ce032d9166d",
        historical_count=31,
    ),
    "GEN_002A": dict(
        symbol="GBPUSD",
        h1=Path(r"D:\GBPUSD_H1_202501020000_202607310000.csv"),
        m15=Path(r"D:\GBPUSD_M15_202501020000_202607310000.csv"),
        m1=Path(r"D:\GBPUSD_M1_202606080533_202607302357.csv"),
        h1_manifest=REPO_ROOT / "config" / "historical_datasets" / "GBPUSD_H1_symbol_metadata.yaml",
        expected_h1="a82275bcf8db245440c6f4cd15bb69ab54b7f8677025410910c913a82bcefe9e",
        expected_m15="1192991287d7e1293c78b8037893ed50f2e0a274c6ed7ac0b1b187988344bac1",
        expected_m1="390798def4c598f3463be5f339d1cf2921537e96a48eca4d797aadb78c1d705c",
        historical_population_hash="2a2fb946f995805ccc56342a712376ccf5ee9fb1e324fa383e7d08c5d3e54fd8",
        historical_count=57,
    ),
}


def _verify_fingerprint(path: Path, expected: str) -> str:
    if not path.exists():
        raise SystemExit(f"DATASET_MISSING: {path}")
    actual = compute_dataset_fingerprint(path).split("sha256:", 1)[1]
    if actual != expected:
        raise SystemExit(f"FINGERPRINT_MISMATCH: {path}: actual={actual} expected={expected}")
    return actual


def _effective_date_range(h1_report, m15_report, m1_report, config, windows):
    raw_start = max(m15_report.start_utc, m1_report.start_utc, h1_report.start_utc)
    raw_end = min(m15_report.end_utc, m1_report.end_utc, h1_report.end_utc)
    covered = []
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
            covered.append(d)
        d = d + timedelta(days=1)
    return covered


def reconstruct_generation(gen_id: str, spec: dict, run_label: str) -> dict:
    symbol = spec["symbol"]
    config = load_config(repo_root=str(REPO_ROOT))

    h1_sha = _verify_fingerprint(spec["h1"], spec["expected_h1"])
    m15_sha = _verify_fingerprint(spec["m15"], spec["expected_m15"])
    m1_sha = _verify_fingerprint(spec["m1"], spec["expected_m1"])

    h1_manifest = load_symbol_metadata_manifest(spec["h1_manifest"])
    if h1_manifest.authority != "OWNER_APPROVED_DATASET_MANIFEST":
        raise SystemExit(f"H1_METADATA_NOT_AUTHORIZED: {gen_id}: authority={h1_manifest.authority!r}")
    validate_manifest_for_dataset(h1_manifest, spec["h1"], symbol)

    print(f"[{gen_id}/{run_label}] loading H1/M15/M1...", file=sys.stderr)
    h1_candles, h1_report = load_mt5_export_csv(str(spec["h1"]), symbol, "H1")
    m15_candles, m15_report = load_mt5_export_csv(str(spec["m15"]), symbol, "M15")
    m1_candles, m1_report = load_mt5_export_csv(str(spec["m1"]), symbol, "M1")

    for report, label in ((h1_report, "H1"), (m15_report, "M15"), (m1_report, "M1")):
        if report.normalized_timezone != "UTC":
            raise SystemExit(f"{gen_id}_{label}_TIMEZONE_NOT_UTC: {report.normalized_timezone}")

    h1_store = HistoricalCandleStore()
    h1_store.load_series(symbol, "H1", h1_candles)

    windows = session_windows_from_config(config)
    session_pairs = [p["pair_id"] for p in config.get("session_pairs", ())]

    dates = _effective_date_range(h1_report, m15_report, m1_report, config, windows)
    if not dates:
        raise SystemExit(f"{gen_id}_EFFECTIVE_REPLAY_WINDOW_EMPTY")

    occurrences = []
    lookahead_violations = []
    runner_target_consulted_by_outcome_math = False

    for d in dates:
        for pair_id in session_pairs:
            w = windows[pair_id]
            ref_start, ref_end = w["reference"].bounds_for_date(d)

            bias = resolve_h1_market_bias(h1_store, h1_manifest, symbol, ref_end, pair_id)

            result = run_replay(
                m15_candles, config, symbol, pair_id, d, PIP_SIZE, PIP_VALUE_PER_LOT,
                bias_result=bias, m1_candles=m1_candles,
            )
            if result.regime is None or result.regime == "UNKNOWN" or not result.accepted_setups:
                continue

            # Independent, pure read of the SAME reference session run_replay computed
            # internally (sessions.py:165) -- not a reimplementation, just re-derivation
            # from data available strictly before ref_end (no lookahead: build_reference_
            # session itself only consumes candles inside [ref_start, ref_end)).
            reference = build_reference_session(m15_candles, w["reference"], d, ref_end, PIP_SIZE)

            for entry_dict in result.accepted_setups:
                entry_time_str = entry_dict["entry_time"]
                entry_time = datetime.fromisoformat(entry_time_str)
                if entry_time < ref_end:
                    lookahead_violations.append({"gen": gen_id, "entry_time": entry_time_str, "ref_end": str(ref_end)})
                # resolve_campaign_entry (called internally by run_replay, replay.py:354)
                # always receives runner_target_r=3.0 from the frozen v1.0.1 config to
                # compute entry_dict["outcome"] -- deliberately never read below.
                runner_target_consulted_by_outcome_math = True

                trade_id = f"{pair_id}_{d}_{entry_time_str}_{entry_dict['setup_model']}"
                occurrences.append({
                    "trade_id": trade_id,
                    "generation_id": gen_id,
                    "symbol": symbol,
                    "session_pair": pair_id,
                    "trading_date": str(d),
                    "setup_model": entry_dict["setup_model"],
                    "direction": entry_dict["direction"],
                    "h1_bias": bias.bias,
                    "h1_bias_confidence": bias.confidence,
                    "decision_timestamp": str(ref_end),
                    "entry_time": entry_time_str,
                    "entry_price": entry_dict["entry_price"],
                    "stop_price": entry_dict["stop_price"],
                    "reference_high": reference.high,
                    "reference_low": reference.low,
                    "fill_precision": entry_dict.get("fill_precision"),
                    "post_entry_m1_reference": {
                        "dataset_sha256": m1_sha,
                        "from_exclusive": entry_time_str,
                    },
                })

    occurrences.sort(key=lambda r: r["trade_id"])
    payload = json.dumps(occurrences, sort_keys=True, separators=(",", ":"))
    population_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    return {
        "generation_id": gen_id,
        "symbol": symbol,
        "occurrences": occurrences,
        "count": len(occurrences),
        "population_hash": population_hash,
        "dataset_hashes": {"H1": h1_sha, "M15": m15_sha, "M1": m1_sha, "symbol_metadata": h1_manifest.dataset_fingerprint},
        "lookahead_violations": lookahead_violations,
        "runner_target_consulted_by_internal_outcome_math": runner_target_consulted_by_outcome_math,
    }


CHECKPOINT_DIR = (
    REPO_ROOT / "artifacts" / "validation" / "ST_SESSION_SWEEP_CONTINUATION_V1"
    / "HYP_001" / "ROUTE_B_PHASE1_RECONSTRUCTION" / "_CHECKPOINTS"
)


def _checkpoint_path(gen_id: str, run_label: str) -> Path:
    return CHECKPOINT_DIR / f"{gen_id}_{run_label}.json"


def _load_checkpoint(gen_id: str, run_label: str):
    p = _checkpoint_path(gen_id, run_label)
    if p.exists():
        print(f"[{gen_id}/{run_label}] checkpoint found, reusing (no recomputation)", file=sys.stderr)
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def _save_checkpoint(gen_id: str, run_label: str, result: dict) -> None:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    _checkpoint_path(gen_id, run_label).write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8",
    )
    print(f"[{gen_id}/{run_label}] checkpoint persisted: count={result['count']} hash={result['population_hash'][:16]}...", file=sys.stderr, flush=True)


def reconstruct_generation_checkpointed(gen_id: str, spec: dict, run_label: str) -> dict:
    cached = _load_checkpoint(gen_id, run_label)
    if cached is not None:
        return cached
    result = reconstruct_generation(gen_id, spec, run_label)
    _save_checkpoint(gen_id, run_label, result)
    return result


def main():
    all_results = {}
    for gen_id, spec in GENERATIONS.items():
        run1 = reconstruct_generation_checkpointed(gen_id, spec, "RUN_1")
        run2 = reconstruct_generation_checkpointed(gen_id, spec, "RUN_2")
        deterministic = (
            run1["population_hash"] == run2["population_hash"]
            and run1["count"] == run2["count"]
            and [o["trade_id"] for o in run1["occurrences"]] == [o["trade_id"] for o in run2["occurrences"]]
        )
        all_results[gen_id] = {
            "run1": run1, "run2_population_hash": run2["population_hash"],
            "run2_count": run2["count"], "deterministic": deterministic,
        }

    combined_ids_hashes = sorted(
        f"{gen_id}:{all_results[gen_id]['run1']['population_hash']}" for gen_id in GENERATIONS
    )
    combined_hash = hashlib.sha256(json.dumps(combined_ids_hashes, sort_keys=True).encode()).hexdigest()

    combined_ids_hashes_r2 = sorted(
        f"{gen_id}:{all_results[gen_id]['run2_population_hash']}" for gen_id in GENERATIONS
    )
    combined_hash_r2 = hashlib.sha256(json.dumps(combined_ids_hashes_r2, sort_keys=True).encode()).hexdigest()

    out = {
        "report_id": "SSC_HYP_001_ROUTE_B_PHASE1_RECONSTRUCTION",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generations": {
            gen_id: {
                "historical_population_hash": GENERATIONS[gen_id]["historical_population_hash"],
                "historical_count": GENERATIONS[gen_id]["historical_count"],
                "reconstructed_count": all_results[gen_id]["run1"]["count"],
                "reconstructed_population_hash": all_results[gen_id]["run1"]["population_hash"],
                "determinism_run2_hash": all_results[gen_id]["run2_population_hash"],
                "deterministic": all_results[gen_id]["deterministic"],
                "dataset_hashes": all_results[gen_id]["run1"]["dataset_hashes"],
                "lookahead_violations": all_results[gen_id]["run1"]["lookahead_violations"],
                "runner_target_consulted_by_internal_outcome_math": all_results[gen_id]["run1"][
                    "runner_target_consulted_by_internal_outcome_math"
                ],
            }
            for gen_id in GENERATIONS
        },
        "combined": {
            "occurrences": sum(all_results[g]["run1"]["count"] for g in GENERATIONS),
            "population_hash": combined_hash,
            "run2_hash": combined_hash_r2,
            "deterministic": combined_hash == combined_hash_r2,
        },
    }

    for gen_id in GENERATIONS:
        out_dir = REPO_ROOT / "artifacts" / "validation" / "ST_SESSION_SWEEP_CONTINUATION_V1" / "HYP_001" / "ROUTE_B_PHASE1_RECONSTRUCTION" / gen_id
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "reconstructed_occurrence_population.json").write_text(
            json.dumps(all_results[gen_id]["run1"]["occurrences"], indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )

    summary_dir = REPO_ROOT / "artifacts" / "validation" / "ST_SESSION_SWEEP_CONTINUATION_V1" / "HYP_001" / "ROUTE_B_PHASE1_RECONSTRUCTION"
    summary_dir.mkdir(parents=True, exist_ok=True)
    (summary_dir / "PHASE1_RECONSTRUCTION_SUMMARY.json").write_text(
        json.dumps(out, indent=2, sort_keys=True, default=str), encoding="utf-8",
    )

    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
