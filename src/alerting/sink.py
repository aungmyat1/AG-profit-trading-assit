"""AlertSink (spec section 27): `publish(alert)` only. Concise by design (spec section
43) -- never logs a full candle dataset, only the scalar summary fields already on
SMCConditionAlert/SessionTradeProposal.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import os
from datetime import date, datetime
from typing import Any, Protocol

logger = logging.getLogger("alerting")

DEFAULT_ALERT_JOURNAL_PATH = os.path.join("journal", "smc_alerts.jsonl")


class AlertSink(Protocol):
    def publish(self, alert: Any) -> None: ...


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "value"):  # Enum
        return value.value
    return str(value)


def _summary_line(alert: Any) -> str:
    triggered = getattr(alert, "triggered_conditions", None) or (getattr(alert, "proposal_status", None),)
    symbol = getattr(alert, "symbol", "?")
    identifier = getattr(alert, "alert_id", None) or getattr(alert, "strategy_id", "?")
    return f"[{identifier}] {symbol} {'+'.join(str(t) for t in triggered)}"


class LogAlertSink:
    """Concise runtime log line only -- spec section 43's [SMC]/[SESSION] examples."""

    def publish(self, alert: Any) -> None:
        logger.info(_summary_line(alert))


class JsonlAlertSink:
    """Append-only JSONL journal, same convention as assistant/idea_journal.py."""

    def __init__(self, path: str = DEFAULT_ALERT_JOURNAL_PATH):
        self.path = path

    def publish(self, alert: Any) -> None:
        entry = dataclasses.asdict(alert) if dataclasses.is_dataclass(alert) else dict(alert)
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True, default=_json_default) + "\n")
