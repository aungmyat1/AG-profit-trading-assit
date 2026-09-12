"""AG_LOCAL_RESEARCH_BOOTSTRAP_V1 -- one-shot, read-only-with-respect-to-trading proof
run. Produces two run directories under research_external/runs/:

    ARTIFACT_PROOF_001/   -- deterministic 5-row CSV/Parquet write->reopen->hash-twice
                             persistence proof (no market data, no MT5 connection)
    REAL_DATA_PROOF_001/  -- small real, closed-bar EURUSD M5 capture from the
                             project's existing read-only MT5 connection, persisted,
                             reopened, and re-verified byte-for-byte

No strategy research, optimization, or candidate creation happens here (this file
performs neither). No MetaTrader5 order/execution function is imported or reachable
from this file or from research_external/tooling/mt5_capture.py -- see
tests/test_research_external_containment.py for the static proof.

Run with: python research_external/bootstrap_run.py
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))
sys.path.insert(0, _HERE)

from tooling.artifact_io import (  # noqa: E402
    read_csv,
    read_parquet,
    sha256_of_file,
    write_csv,
    write_json_manifest,
    write_parquet,
)
from tooling.mt5_capture import broker_server_name, capture_closed_bars  # noqa: E402

RUNS_DIR = os.path.join(_HERE, "runs")

_SAMPLE_ROWS = [
    {"row_id": 1, "value": 10},
    {"row_id": 2, "value": 20},
    {"row_id": 3, "value": 30},
    {"row_id": 4, "value": 40},
    {"row_id": 5, "value": 50},
]
_EXPECTED_SUM = 150


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=_REPO_ROOT, capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except Exception:
        return "NOT_AVAILABLE"


def run_artifact_persistence_proof() -> dict:
    run_dir = os.path.join(RUNS_DIR, "ARTIFACT_PROOF_001")
    csv_path = os.path.join(run_dir, "sample.csv")
    parquet_path = os.path.join(run_dir, "sample.parquet")
    proof_path = os.path.join(run_dir, "proof.json")
    manifest_path = os.path.join(run_dir, "manifest.json")

    csv_artifact = write_csv(csv_path, _SAMPLE_ROWS, fieldnames=["row_id", "value"])
    parquet_artifact = write_parquet(parquet_path, _SAMPLE_ROWS)

    # Reopen (fresh process-level read, not the writer's own in-memory rows) and
    # verify row count + sum before trusting either file.
    reopened_csv_rows = read_csv(csv_path)
    csv_sum = sum(int(r["value"]) for r in reopened_csv_rows)
    reopened_parquet_df = read_parquet(parquet_path)
    parquet_sum = int(reopened_parquet_df["value"].sum())

    result = {
        "csv": {
            "path": csv_path, "size_bytes": csv_artifact.size_bytes,
            "sha256_pass1": csv_artifact.sha256_pass1, "sha256_pass2": csv_artifact.sha256_pass2,
            "hash_reproducible": csv_artifact.reproducible,
            "row_count": len(reopened_csv_rows), "sum_value": csv_sum, "sum_matches_expected": csv_sum == _EXPECTED_SUM,
        },
        "parquet": {
            "path": parquet_path, "size_bytes": parquet_artifact.size_bytes,
            "sha256_pass1": parquet_artifact.sha256_pass1, "sha256_pass2": parquet_artifact.sha256_pass2,
            "hash_reproducible": parquet_artifact.reproducible,
            "row_count": len(reopened_parquet_df), "sum_value": parquet_sum, "sum_matches_expected": parquet_sum == _EXPECTED_SUM,
        },
    }

    write_json_manifest(proof_path, {
        "run_id": "ARTIFACT_PROOF_001",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "LOCAL_ARTIFACT_PERSISTENCE_PROOF",
        "sample_rows": _SAMPLE_ROWS,
        "expected_sum": _EXPECTED_SUM,
        "result": result,
    })
    proof_sha = sha256_of_file(proof_path)

    manifest_entries = [
        {"filename": "sample.csv", "size_bytes": result["csv"]["size_bytes"], "sha256": result["csv"]["sha256_pass2"]},
        {"filename": "sample.parquet", "size_bytes": result["parquet"]["size_bytes"], "sha256": result["parquet"]["sha256_pass2"]},
        {"filename": "proof.json", "size_bytes": os.path.getsize(proof_path), "sha256": proof_sha},
    ]
    write_json_manifest(manifest_path, {"run_id": "ARTIFACT_PROOF_001", "entries": manifest_entries})

    result["proof_json_sha256"] = proof_sha
    result["overall_pass"] = (
        result["csv"]["hash_reproducible"] and result["csv"]["sum_matches_expected"]
        and result["parquet"]["hash_reproducible"] and result["parquet"]["sum_matches_expected"]
    )
    return result


def run_real_mt5_data_proof(symbol: str = "EURUSD", timeframe: str = "M5", count: int = 20) -> dict:
    run_dir = os.path.join(RUNS_DIR, "REAL_DATA_PROOF_001")
    dataset_dir = os.path.join(run_dir, "datasets")
    dataset_path = os.path.join(dataset_dir, "EURUSD_M5_REAL_PROOF.parquet")
    manifest_path = os.path.join(run_dir, "dataset_manifest.json")

    bars = capture_closed_bars(symbol, timeframe, count)
    broker = broker_server_name()
    rows = [b.__dict__ for b in bars]

    write_start = datetime.now(timezone.utc)
    artifact = write_parquet(dataset_path, rows)

    reopened = read_parquet(dataset_path)
    # Round-trip identity checks (section 8/10).
    row_count = len(reopened)
    timestamps = list(reopened["timestamp_utc"])
    epochs = list(reopened["raw_epoch"])
    monotonic = all(epochs[i] <= epochs[i + 1] for i in range(len(epochs) - 1))
    duplicate_count = len(epochs) - len(set(epochs))
    now_utc = datetime.now(timezone.utc)
    future_rows = sum(1 for e in epochs if datetime.fromtimestamp(int(e), tz=timezone.utc) > now_utc)

    # Timestamp authority: first, last, and up to 3 interior samples, recomputed
    # independently from raw_epoch and compared against the stored timestamp_utc.
    sample_indices = sorted(set([0, row_count - 1] + [row_count // 4, row_count // 2, (3 * row_count) // 4]))
    sample_indices = [i for i in sample_indices if 0 <= i < row_count]
    mismatches = 0
    samples_checked = []
    for i in sample_indices:
        expected = datetime.fromtimestamp(int(epochs[i]), tz=timezone.utc).isoformat()
        stored = timestamps[i]
        match = expected == stored
        if not match:
            mismatches += 1
        samples_checked.append({"index": i, "raw_epoch": int(epochs[i]), "expected_utc": expected, "stored_utc": stored, "match": match})

    reopen_sha256 = sha256_of_file(dataset_path)
    hash_match = reopen_sha256 == artifact.sha256_pass2

    dataset_manifest = {
        "dataset_id": "EURUSD_M5_REAL_PROOF",
        "source_type": "REAL_OBSERVED_MARKET",
        "broker": broker,
        "symbol": symbol,
        "timeframe": timeframe,
        "requested_count": count,
        "actual_first_timestamp": timestamps[0] if row_count else None,
        "actual_last_timestamp": timestamps[-1] if row_count else None,
        "acquired_at_utc": write_start.isoformat(),
        "row_count": row_count,
        "file_path": os.path.relpath(dataset_path, _REPO_ROOT).replace("\\", "/"),
        "size_bytes": artifact.size_bytes,
        "sha256": artifact.sha256_pass2,
        "sha256_reopen": reopen_sha256,
        "hash_match": hash_match,
        "monotonic": monotonic,
        "duplicate_timestamp_count": duplicate_count,
        "future_row_count": future_rows,
        "timestamp_samples_checked": len(samples_checked),
        "timestamp_mismatch_count": mismatches,
        "timestamp_samples": samples_checked,
        "timestamp_authority": "PASS" if mismatches == 0 else "FAIL",
    }
    write_json_manifest(manifest_path, dataset_manifest)

    dataset_manifest["overall_pass"] = (
        row_count > 0 and hash_match and monotonic and duplicate_count == 0 and future_rows == 0 and mismatches == 0
    )
    return dataset_manifest


def write_run_manifest(dataset_manifest: dict) -> dict:
    run_manifest_path = os.path.join(RUNS_DIR, "REAL_DATA_PROOF_001", "run_manifest.json")
    payload = {
        "run_id": "REAL_DATA_PROOF_001",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(),
        "python_version": sys.version,
        "data_source": dataset_manifest["source_type"],
        "broker": dataset_manifest["broker"],
        "dataset_id": dataset_manifest["dataset_id"],
        "dataset_sha256": dataset_manifest["sha256"],
        "purpose": "LOCAL_RESEARCH_PIPELINE_BOOTSTRAP",
        "strategy_research_performed": False,
        "candidate_created": False,
        "optimization_performed": False,
        "platform": platform.system() + " " + platform.release(),
    }
    write_json_manifest(run_manifest_path, payload)
    return payload


def main() -> None:
    print("=== ARTIFACT_PROOF_001 ===")
    proof_result = run_artifact_persistence_proof()
    print(json.dumps(proof_result, indent=2, default=str))

    print()
    print("=== REAL_DATA_PROOF_001 ===")
    try:
        dataset_manifest = run_real_mt5_data_proof()
    except Exception as exc:  # noqa: BLE001 -- surfaced verbatim to the operator, no trading fallback
        print("REAL_MT5_DATA_PROOF_FAILED:", repr(exc))
        return
    print(json.dumps(dataset_manifest, indent=2, default=str))

    print()
    print("=== run_manifest.json ===")
    run_manifest = write_run_manifest(dataset_manifest)
    print(json.dumps(run_manifest, indent=2, default=str))


if __name__ == "__main__":
    main()
