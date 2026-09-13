"""Validate the existing frozen EURUSD lifecycle population.

Research-only report driver. It validates the immutable lifecycle artifact and
dataset package without changing strategy logic or execution authority. A replay
determinism PASS requires a persisted second-run report; this script deliberately
fails closed when that evidence is absent.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from research.session_lifecycle import population_hash

REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "research" / "EXP_EXPOSURE_EFFICIENCY_V1" / "GEN_001"
POPULATION_PATH = ARTIFACT_DIR / "canonical_lifecycle_population.json"
INPUT_MANIFEST_PATH = ARTIFACT_DIR / "input_manifest.json"
PACKAGE_PATH = REPO_ROOT / "config" / "historical_datasets" / "ST_SESSION_SWEEP_CONTINUATION_V1_EURUSD_PACKAGE.yaml"
REPORT_PATH = ARTIFACT_DIR / "g0_g1_validation.json"
EXPECTED_STRATEGY = "ST_SESSION_SWEEP_CONTINUATION_V1"
EXPECTED_VERSION = "1.0.0"
EXPECTED_SYMBOL = "EURUSD"
EXPECTED_DATASET_SHA = "55422a1ccdf4ca76fd25451fbf849d559bed45d839891a3ada7a37f9f7dd6a23"
EXPECTED_POPULATION_HASH = "8e32a7498e5a1c7df6658e6700ff3386fb38821ed189619a20224ce032d9166d"


def _git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _aware_utc(value: str) -> bool:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.tzinfo is not None and parsed.utcoffset() is not None and parsed.utcoffset().total_seconds() == 0


def _validate_records(records: list[dict]) -> dict:
    reasons: dict[str, int] = {}
    ids = [record.get("trade_id") for record in records]
    if len(ids) != len(set(ids)):
        reasons["DUPLICATE_OCCURRENCE_ID"] = len(ids) - len(set(ids))

    valid = 0
    evaluable = 0
    for record in records:
        problems = []
        required = ("trade_id", "strategy_id", "strategy_version", "symbol", "direction",
                    "entry_time", "entry_price", "initial_stop", "initial_risk", "events",
                    "gross_R", "friction_R", "net_R", "final_state", "resolution_time")
        problems.extend(f"MISSING_{field}" for field in required if field not in record)
        if record.get("strategy_id") != EXPECTED_STRATEGY:
            problems.append("STRATEGY_PROVENANCE")
        if record.get("strategy_version") != EXPECTED_VERSION:
            problems.append("VERSION_PROVENANCE")
        if record.get("symbol") != EXPECTED_SYMBOL:
            problems.append("SYMBOL_PROVENANCE")
        if record.get("direction") not in {"LONG", "SHORT"}:
            problems.append("INVALID_DIRECTION")
        try:
            entry = datetime.fromisoformat(record["entry_time"])
            resolution = datetime.fromisoformat(record["resolution_time"])
            event_times = [datetime.fromisoformat(event["time"]) for event in record["events"]]
            if not (_aware_utc(record["entry_time"]) and _aware_utc(record["resolution_time"])
                    and all(_aware_utc(event["time"]) for event in record["events"])):
                problems.append("TIMESTAMP_NOT_CANONICAL_UTC")
            if not event_times or event_times != sorted(event_times) or event_times[0] < entry or resolution != event_times[-1]:
                problems.append("INVALID_EVENT_CHRONOLOGY")
            if record["initial_risk"] <= 0 or record["entry_price"] == record["initial_stop"]:
                problems.append("INVALID_STOP_GEOMETRY")
            if abs(record["initial_risk"] - abs(record["entry_price"] - record["initial_stop"])) > 1e-12:
                problems.append("RISK_RECONCILIATION")
            if abs(sum(event["gross_R_delta"] for event in record["events"]) - record["gross_R"]) > 1e-12:
                problems.append("GROSS_RECONCILIATION")
            if abs(record["gross_R"] - record["friction_R"] - record["net_R"]) > 1e-12:
                problems.append("NET_RECONCILIATION")
            if entry >= resolution:
                problems.append("NO_POST_ENTRY_PATH")
            if record["final_state"] not in {"RESOLVED_SL", "RESOLVED_TP1", "RESOLVED_SESSION_EXIT", "RESOLVED_TIME_STOP"}:
                problems.append("OUTCOME_NOT_EVALUABLE")
        except (KeyError, TypeError, ValueError):
            problems.append("MALFORMED_OCCURRENCE")

        if problems:
            for problem in problems:
                reasons[problem] = reasons.get(problem, 0) + 1
        else:
            valid += 1
            evaluable += 1

    return {
        "generated_occurrences": len(records),
        "valid_occurrences": valid,
        "evaluable_occurrences": evaluable,
        "excluded_occurrences": len(records) - evaluable,
        "exclusion_reasons": reasons,
        "setup_counts": {
            setup: sum(f"_{setup}_" in record.get("trade_id", "") for record in records)
            for setup in ("S1", "S2", "S3")
        },
    }


def validate(*, replay_evidence_path: Path | None = None) -> dict:
    package = yaml.safe_load(PACKAGE_PATH.read_text(encoding="utf-8"))
    input_manifest = json.loads(INPUT_MANIFEST_PATH.read_text(encoding="utf-8"))
    records = json.loads(POPULATION_PATH.read_text(encoding="utf-8"))
    reloaded_records = json.loads(POPULATION_PATH.read_text(encoding="utf-8"))

    source = next(item for item in package["sources"] if item["role"] == "FILL_RESOLUTION_INPUT")
    source_path = Path(r"D:\EURUSD_M1_202605180946_202607312356.csv")
    dataset_exists = source_path.exists()
    dataset_sha = _sha256(source_path) if dataset_exists else None
    hash_run_1 = population_hash(records)
    hash_reload = population_hash(reloaded_records)
    replay_evidence = None
    if replay_evidence_path is not None:
        replay_evidence = json.loads(replay_evidence_path.read_text(encoding="utf-8"))

    record_checks = _validate_records(records)
    g0_checks = {
        "package_strategy_exact": package.get("strategy_id") == EXPECTED_STRATEGY,
        "package_version_exact": package.get("strategy_version") == EXPECTED_VERSION,
        "package_symbol_exact": package.get("symbol") == EXPECTED_SYMBOL,
        "dataset_exists": dataset_exists,
        "dataset_sha256_exact": dataset_sha == EXPECTED_DATASET_SHA,
        "manifest_dataset_sha256_exact": input_manifest.get("dataset_sha256") == EXPECTED_DATASET_SHA,
        "artifact_count_exact": len(records) == 31,
        "artifact_hash_exact": hash_run_1 == EXPECTED_POPULATION_HASH,
        "reload_hash_exact": hash_reload == EXPECTED_POPULATION_HASH,
        "replay_run_2_persisted": replay_evidence is not None,
    }
    if replay_evidence is not None:
        g0_checks["replay_counts_match"] = (
            replay_evidence.get("trade_count_run_1") == 31
            and replay_evidence.get("trade_count_run_2") == 31
            and replay_evidence.get("population_hash_run_1") == EXPECTED_POPULATION_HASH
            and replay_evidence.get("population_hash_run_2") == EXPECTED_POPULATION_HASH
            and replay_evidence.get("occurrence_ids_run_1") == replay_evidence.get("occurrence_ids_run_2")
        )

    g0 = "G0_PASS" if all(g0_checks.values()) else "EVIDENCE_INCOMPLETE"
    g1_checks = {
        "all_records_valid": record_checks["valid_occurrences"] == len(records),
        "all_records_evaluable": record_checks["evaluable_occurrences"] == len(records),
        "unique_occurrence_ids": "DUPLICATE_OCCURRENCE_ID" not in record_checks["exclusion_reasons"],
        "decision_time_causality_persisted": False,
        "raw_post_entry_path_persisted": False,
    }
    g1 = "G1_PASS" if all(g1_checks.values()) else "EVIDENCE_INCOMPLETE"

    report = {
        "strategy_id": EXPECTED_STRATEGY,
        "version": EXPECTED_VERSION,
        "symbol": EXPECTED_SYMBOL,
        "dataset_hash": EXPECTED_DATASET_SHA,
        "population_hash": hash_run_1,
        **{key: record_checks[key] for key in ("generated_occurrences", "valid_occurrences", "evaluable_occurrences", "excluded_occurrences", "exclusion_reasons")},
        "g0_checks": g0_checks,
        "g1_checks": g1_checks,
        "g0_verdict": g0,
        "g1_verdict": g1,
        "overall_verdict": "G0_PASS_G1_PASS" if g0 == "G0_PASS" and g1 == "G1_PASS" else "EVIDENCE_INCOMPLETE",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "code_head": _git_head(),
        "validation_implementation": "scripts/validate_first_canonical_population.py@1",
        "replay_determinism": replay_evidence or {"status": "NOT_PERSISTED", "reason": "SECOND_REPLAY_EVIDENCE_REQUIRED"},
        "baseline_discovery_metrics": "NOT_EVALUATED_UNTIL_G0_G1_PASS_AND_SPLIT_FREEZE",
        "split_freeze": "NOT_CREATED_G0_G1_INCOMPLETE",
        "limitations": [
            "The lifecycle artifact does not persist raw decision-time candle inputs.",
            "The lifecycle artifact does not persist the full post-entry candle path.",
            "Target/MAE/MFE fields are not present in this artifact; no target result is inferred.",
        ],
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay-evidence", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(replay_evidence_path=args.replay_evidence), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()