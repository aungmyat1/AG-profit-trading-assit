"""Read-only EURUSD spread evidence capture (AG_LARGE_SMC_EURUSD_FRICTION_EVIDENCE_V1,
WP3A P2). Connects via mt5.connection.connect() (idempotent), captures `--count`
live bid/ask observations spaced `--interval-seconds` apart via
fx_friction_research.spread_evidence, and appends raw observations plus a freshly
computed summary to artifacts/validation/ST_LARGE_SMC_V1/EURUSD_ADMISSION_CONTRACTS/
spread_evidence/. Never calls order_send/order_check or anything execution-facing.
Fails closed (non-zero exit, no file written) if MT5 is not connected.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from mt5.connection import MT5ConnectionError, connect  # noqa: E402
from fx_friction_research.spread_evidence import (  # noqa: E402
    capture_observation,
    raw_observations_hash,
    summarize,
)

PIP_SIZE_EURUSD = 0.0001
OUT_DIR = REPO_ROOT / "artifacts" / "validation" / "ST_LARGE_SMC_V1" / "EURUSD_ADMISSION_CONTRACTS" / "spread_evidence"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--interval-seconds", type=float, default=5.0)
    parser.add_argument("--label", default="session_snapshot")
    args = parser.parse_args()

    try:
        connect()
    except MT5ConnectionError as exc:
        print(f"MT5_CONNECTION_FAILED: {exc}", file=sys.stderr)
        return 1

    observations = []
    for i in range(args.count):
        observations.append(capture_observation("EURUSD", PIP_SIZE_EURUSD))
        if i < args.count - 1:
            time.sleep(args.interval_seconds)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = OUT_DIR / f"{args.label}_raw.jsonl"
    with raw_path.open("a", encoding="utf-8") as fh:
        for observation in observations:
            fh.write(json.dumps(asdict(observation), sort_keys=True) + "\n")

    summary = summarize(observations)
    summary["raw_observations_hash"] = raw_observations_hash(observations)
    summary["label"] = args.label
    summary_path = OUT_DIR / f"{args.label}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
