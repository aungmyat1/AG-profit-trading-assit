"""Append-only trade-idea journal (AG_TRADING_ASSISTANT_WORKFLOW_V1 spec sections 26-28)
-- one JSON-lines file, journal/trade_ideas.jsonl. Records EVERY
technique_router.analyze_by_technique() call (WAIT/NO_TRADE/rejected setups included,
not only TRADE_PROPOSAL_READY -- spec section 27), and keeps a decision snapshot taken
at evaluation time T physically separate from any realized outcome recorded later (spec
section 28): a realized_outcome line is a new appended record keyed by the same
`idea_id`, never a rewrite of the original decision_snapshot line.

Distinct from assistant/journal.py (the strategy_manager/runtime.evaluate path's own
journal) and execution/journal.py + trade_management/journal.py (order/position event
logs) -- this journal covers the technique_router SMC/DAYTRADING analysis path only and
does not replace any of those."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

DEFAULT_JOURNAL_PATH = os.path.join("journal", "trade_ideas.jsonl")

KIND_DECISION_SNAPSHOT = "decision_snapshot"
KIND_REALIZED_OUTCOME = "realized_outcome"


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):  # Enum
        return value.value
    return str(value)


def _append(entry: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True, default=_json_default) + "\n")


def _daytrading_fields(result) -> dict:
    narrative = result.narrative_bias
    affinity = result.liquidity_affinity
    ltf = result.ltf_execution
    risk = result.risk_management
    return {
        "narrative_profile": getattr(narrative, "expected_profile", None),
        "preferred_direction": getattr(narrative, "preferred_direction", None),
        "primary_draw": getattr(narrative, "primary_draw", None),
        "liquidity_affinity_status": getattr(affinity, "status", None) if affinity else None,
        "primary_target_price": getattr(affinity, "primary_target_price", None) if affinity else None,
        "ltf_status": getattr(ltf, "status", None) if ltf else None,
        "sweep_shift_aggregation": getattr(ltf.sweep_shift_result, "aggregation_status", None)
        if ltf is not None and ltf.sweep_shift_result is not None else None,
        "entry_reference_price": getattr(ltf, "entry_reference_price", None) if ltf else None,
        "structural_invalidation_reference": getattr(ltf, "structural_invalidation_reference", None) if ltf else None,
        "risk_status": getattr(risk, "status", None) if risk else None,
        "risk_reward": getattr(risk, "risk_reward", None) if risk else None,
        "direction": result.direction,
    }


def _smc_fields(result) -> dict:
    ec = result.entry_confirmation
    return {
        "structure_state": getattr(result.structure, "state", None) if result.structure else None,
        "liquidity_status": getattr(result.liquidity, "status", None) if result.liquidity else None,
        "entry_confirmation_overall_state": ec.overall_state.value if ec is not None else None,
        "skill_statuses": dict(result.skill_statuses),
    }


def record_decision(
    technique: str, symbol: str, evaluation_time: Optional[datetime], result,
    canonical_state: str, reason: Optional[str] = None, path: str = DEFAULT_JOURNAL_PATH,
) -> str:
    """Appends one decision_snapshot line and returns the generated `idea_id` (needed
    later to append a matching realized_outcome). Compact scalar summary only (spec
    section 20) -- never a full detector-payload dump."""
    idea_id = str(uuid.uuid4())
    entry = {
        "kind": KIND_DECISION_SNAPSHOT,
        "idea_id": idea_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "evaluation_time": evaluation_time.isoformat() if evaluation_time is not None else None,
        "technique": technique,
        "symbol": symbol,
        "canonical_state": canonical_state,
        "reason": reason,
        **(_daytrading_fields(result) if technique == "DAYTRADING" else _smc_fields(result)),
    }
    _append(entry, path)
    return idea_id


def record_realized_outcome(
    idea_id: str, executed: bool, broker_ticket: Optional[str] = None,
    result_r: Optional[float] = None, closed_at: Optional[datetime] = None,
    notes: Optional[str] = None, path: str = DEFAULT_JOURNAL_PATH,
) -> None:
    """Appends a separate realized_outcome line keyed by `idea_id` -- never mutates or
    rewrites the original decision_snapshot line (spec section 28)."""
    entry = {
        "kind": KIND_REALIZED_OUTCOME,
        "idea_id": idea_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "executed": executed,
        "broker_ticket": broker_ticket,
        "result_r": result_r,
        "closed_at": closed_at.isoformat() if closed_at is not None else None,
        "notes": notes,
    }
    _append(entry, path)


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
