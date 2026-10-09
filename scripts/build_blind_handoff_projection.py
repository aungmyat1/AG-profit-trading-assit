#!/usr/bin/env python3
"""Build the deterministic input-only R4A projection; never evaluates strategy rules."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts/logic_verification/ST_ASIAN_SWEEP_5R_V1_2_0/r3_dataset/cases.json"
PUBLIC = ROOT / "artifacts/blind_handoff/ST_ASIAN_SWEEP_5R_V1_2_0/dataset.json"
PRIVATE = ROOT / "artifacts/blind_handoff_private/ST_ASIAN_SWEEP_5R_V1_2_0/case_id_map.json"
SOURCE_DATASET_ID = "AG_ASIAN_SWEEP_V1_2_R3_LOGIC_PARITY_001"
SOURCE_DATASET_SHA256 = "a3c1ee5b04792dcea4defbd868cb0ed1a048927deddb68b9b67ecf842856fd80"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def main() -> int:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    projected, id_map = [], {}
    for index, case in enumerate(source["cases"], 1):
        neutral = f"C{index:03d}"
        id_map[neutral] = case["case_id"]
        projected.append({
            "case_id": neutral,
            "symbol": case["symbol"],
            "session_id": case["session_id"],
            "session_date": case["session_date"],
            "reference_start_utc": case["reference_start_utc"],
            "reference_end_utc": case["reference_end_utc"],
            "reference_candles": case["reference_candles"],
            "trade_candles": case["trade_candles"],
            "spread_observation": None if case["spread_value"] is None else {
                "value": case["spread_value"], "unit": case["spread_unit"],
                "timestamp_utc": case["spread_timestamp_utc"], "source": case["spread_source"],
                "provenance_sha256": case["spread_provenance_hash"],
            },
            "precision_metadata": None,
            "raw_source_sha256": case["raw_source_hash"],
        })
    output = {
        "schema_id": "AG_ASIAN_SWEEP_V1_2_BLIND_INPUT_V1",
        "source_dataset_id": SOURCE_DATASET_ID,
        "source_dataset_sha256": SOURCE_DATASET_SHA256,
        "cases": projected,
    }
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    private = {"handoff_to_source_case_ids": id_map,
               "public_dataset_sha256": hashlib.sha256(PUBLIC.read_bytes()).hexdigest()}
    PRIVATE.write_text(json.dumps(private, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
