"""Append-only assistant decision journal -- one JSON-lines file per run_id under
journal/assistant_runs.jsonl. Records EVERY evaluate() call (NO_SETUP, BLOCKED,
TRADE_READY, SHADOW_CHECKED, EXECUTED, etc.), not just executed trades (spec section 24).

This is a companion audit trail of "what the assistant decided" -- it is NOT a
replacement for Session Trade Codex's own execution ledger/journal, which stays
authoritative for the actual broker-facing history of that strategy.
"""
from __future__ import annotations

import json
import os

from assistant.models import AssistantDecision

DEFAULT_JOURNAL_PATH = os.path.join("journal", "assistant_runs.jsonl")


def record(decision: AssistantDecision, path: str = DEFAULT_JOURNAL_PATH) -> None:
    entry = {
        "run_id": decision.run_id,
        "timestamp_utc": decision.timestamp_utc.isoformat(),
        "strategy_id": decision.strategy_id,
        "strategy_version": decision.strategy_version,
        "symbol": decision.symbol,
        "cycle": decision.cycle,
        "session_date": None,
        "execution_mode": decision.execution_mode,
        "status": decision.status,
        "context_status": decision.context_status,
        "strategy_status": decision.strategy_status,
        "setup": decision.setup,
        "direction": decision.direction,
        "entry": decision.entry,
        "stop_loss": decision.stop_loss,
        "target": decision.target,
        "signal_id": decision.signal_id,
        "reason_codes": list(decision.reason_codes),
        "execution_report": decision.execution_report,
    }
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def read_all(path: str = DEFAULT_JOURNAL_PATH) -> list:
    if not os.path.exists(path):
        return []
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries
