"""Identity/provenance binding for FX friction-stress evidence
(AG_THREE_STRATEGY_VALIDATION_CONTINUATION_V1 P4). Deterministic, dependency-free hash of
the exact resolved-outcome economic fields this evidence is derived from -- used both as
the P1 "friction work is additive only" immutability proof and as the evidence artifact's
own `resolved_record_hash` binding."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List

# The economic/identity fields a resolved outcome record carries. Anything outside this
# set (e.g. evidence_quality, note, market_data_source) is descriptive metadata, not an
# economic fact this hash needs to pin.
ECONOMIC_FIELDS: tuple = (
    "proposal_id", "strategy_id", "strategy_version", "symbol", "cycle", "trading_date",
    "entry", "stop_loss", "tp1", "tp2", "terminal_state", "realized_R", "tp1_R",
    "event_sequence", "proposal_timestamp", "market_data_start", "market_data_end",
)


def economic_fingerprint(record: Dict[str, Any]) -> Dict[str, Any]:
    return {k: record.get(k) for k in ECONOMIC_FIELDS}


def resolved_record_hash(records: List[Dict[str, Any]]) -> str:
    """SHA-256 over the sorted, canonical JSON of every record's economic fingerprint.
    Deterministic and order-independent (records sorted by proposal_id first) -- re-
    running this over an unchanged record population always reproduces the same digest;
    any change to realized_R/terminal_state/entry/stop/target/timestamps changes it."""
    fingerprints = sorted(
        (economic_fingerprint(r) for r in records),
        key=lambda r: r["proposal_id"] or "",
    )
    blob = json.dumps(fingerprints, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()
