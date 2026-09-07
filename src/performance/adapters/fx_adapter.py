"""Read-only FX performance adapter: normalizes
artifacts/outcome_resolution/records/ST_ASIAN_SWEEP_5R_V1_*.json (written by
scripts/resolve_forward_shadow_outcomes.py) into ResolvedTradeSample. Never writes to
that directory -- source records remain the sole, immutable historical truth.
"""
from __future__ import annotations

import json
import os
from typing import List

from performance.models import ResolvedTradeSample

STRATEGY_ID = "ST_ASIAN_SWEEP_5R_V1"
STRATEGY_VERSION = "1.1.1"
RECORDS_DIR = os.path.join("artifacts", "outcome_resolution", "records")


def load_fx_resolved_samples(
    repo_root: str = ".", strategy_version: str = STRATEGY_VERSION,
) -> List[ResolvedTradeSample]:
    """Reads every ST_ASIAN_SWEEP_5R_V1 record whose strategy_version matches and
    whose realized_R was actually computed (skips AMBIGUOUS_SEQUENCE/UNRESOLVED
    records rather than fabricating a sample for them)."""
    directory = os.path.join(repo_root, RECORDS_DIR)
    samples: List[ResolvedTradeSample] = []
    if not os.path.isdir(directory):
        return samples

    for name in sorted(os.listdir(directory)):
        if not name.startswith(STRATEGY_ID) or not name.endswith(".json"):
            continue
        path = os.path.join(directory, name)
        with open(path, "r", encoding="utf-8") as fh:
            record = json.load(fh)
        if record.get("strategy_version") != strategy_version:
            continue
        realized_R = record.get("realized_R")
        if realized_R is None:
            continue  # e.g. AMBIGUOUS_SEQUENCE/UNRESOLVED -- not a resolved trade

        cost_status = record.get("cost_status", "NOT_INCLUDED")
        samples.append(ResolvedTradeSample(
            source_record_id=record["proposal_id"],
            source_path=os.path.join(RECORDS_DIR, name).replace("\\", "/"),
            strategy_id=record["strategy_id"],
            strategy_version=record["strategy_version"],
            symbol=record["symbol"],
            cycle=record.get("cycle"),
            resolved_at=record.get("proposal_timestamp"),  # no separate resolution
            # timestamp exists in this schema; proposal_timestamp is the best available
            # strictly-ordered field for deterministic drawdown sequencing.
            gross_R=float(realized_R),
            net_R=None if cost_status != "INCLUDED" else record.get("net_R"),
            cost_status=cost_status,
            outcome=record.get("terminal_state", "UNKNOWN"),
        ))
    return samples
