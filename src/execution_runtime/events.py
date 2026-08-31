"""Compact structured event logging for AG_DAYTRADING_RUNTIME_V1 (spec LOGGING: "Compact
structured events only for meaningful state transitions ... not every poll iteration or
unchanged candle"). Reuses the repo's existing logging.getLogger convention (see
alerting/sink.py) rather than inventing a second logging setup.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any

logger = logging.getLogger("execution_runtime")

# The exact meaningful-transition vocabulary the spec names -- kept as one place so a
# caller cannot accidentally invent a slightly different spelling for the same concept.
EVENT_REFERENCE_READY = "REFERENCE_READY"
EVENT_SWEEP_DETECTED = "SWEEP_DETECTED"
EVENT_MSS_CONFIRMED = "MSS_CONFIRMED"
EVENT_RETEST_READY = "RETEST_READY"
EVENT_ENTRY_READY = "ENTRY_READY"
EVENT_CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
EVENT_EXECUTED = "EXECUTED"
EVENT_POSITION_RECONCILED = "POSITION_RECONCILED"
EVENT_PARTIAL_CLOSE = "PARTIAL_CLOSE"
EVENT_POSITION_CLOSED = "POSITION_CLOSED"
EVENT_REALIZED_R_RECORDED = "REALIZED_R_RECORDED"
EVENT_BLOCKED_OPEN_POSITION = "BLOCKED_OPEN_POSITION"
EVENT_BLOCKED_DAILY_LOSS = "BLOCKED_DAILY_LOSS"
EVENT_PROPOSAL_ONLY = "PROPOSAL_ONLY"


def _default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def emit(event: str, **fields: Any) -> None:
    """One compact JSON line per meaningful transition. Callers decide WHETHER an event is
    meaningful (e.g. cycle.py only calls this when a setup's state actually changed, or on
    a genuine lifecycle transition) -- this function itself never filters or de-dupes."""
    logger.info(json.dumps({"event": event, **fields}, default=_default, sort_keys=True))
