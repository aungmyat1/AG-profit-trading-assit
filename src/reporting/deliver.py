"""Telegram delivery of archived REPORT_ONLY observations (AGP-C18-R2 PR C).

Order per observation: (already archived by its lane) -> INTENT event -> Sender.send_report -> RESULT
event with the ledger's message id. The Sender ledger dedupes (`duplicate`), never auto-retries an
uncertain or failed send, and the tracked scope (OD1013-C18-REPORT-SCOPE) decides what is immediate;
NO_OPPORTUNITY / DATA_ERROR / OUT_OF_SESSION stay summary-only. An attempted send is never recorded
as delivered unless the ledger holds a Telegram message id.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from collections import Counter
from typing import Any, Dict, Iterable, List

from telegram_delivery.adapter import REPORT_SCOPES, report_identity

DELIVERY_SUBDIR = os.path.join("ticket_delivery", "report_lane")

_NON_DELIVERABLE_TICKET_DECISIONS = frozenset({
    "INSUFFICIENT_DATA", "MISSED", "INFO_ONLY_STALE", "INFO_ONLY_SUPPRESSED",
    "NO_TRADE", "READY", "TICKET_READY", "WATCH_READY",
})


def _ticket_setup_skip_reason(canonical: Dict[str, Any]) -> str | None:
    """Only send priced ASW/CCFD REPORT_ONLY observations; reports never confer authority."""
    if canonical.get("scope_route") != "REPORT_ONLY":
        return "NOT_REPORT_ONLY"
    if canonical.get("strategy_id") not in {
            "ST_ASIAN_SWEEP_5R_V1", "ST_CRYPTO_CFD_SWEEP_RETEST_V1"}:
        return "FAMILY_NOT_IN_TICKET_REPORT_LANE"
    if canonical.get("report_class") not in {"CANDIDATE", "BLOCKED"}:
        return "REPORT_CLASS_SUMMARY_ONLY"
    if canonical.get("decision") in _NON_DELIVERABLE_TICKET_DECISIONS:
        return "DECISION_SUMMARY_ONLY"
    prices = canonical.get("prices") or {}
    if (canonical.get("direction") not in {"LONG", "SHORT"}
            or prices.get("entry_reference_raw") is None
            or prices.get("sl_raw") is None
            or prices.get("tp1_raw") is None):
        return "SETUP_INCOMPLETE"
    return None


def _event(path: str, row: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(row, sort_keys=True, default=str) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def deliver_observations(observations: Iterable[Dict[str, Any]], *, sender, journal: str,
                         now: dt.datetime, label: str = "", ticket_setup_only: bool = False) -> List[str]:
    path = os.path.join(journal, DELIVERY_SUBDIR, f"delivery_{now.date().isoformat()}.jsonl")
    states: Counter = Counter()
    for c in observations:
        if ticket_setup_only:
            skip_reason = _ticket_setup_skip_reason(c)
            if skip_reason is not None:
                identity = report_identity(c)
                base = {"identity": identity, "report_class": c.get("report_class"),
                        "instrument": c.get("instrument"),
                        "strategy": f"{c.get('strategy_id')}@{c.get('strategy_version')}",
                        "execution_authorized": False}
                _event(path, {**base, "stage": "RESULT", "recorded_at_utc": now.isoformat(),
                              "delivery_state": "summary_only", "skip_reason": skip_reason,
                              "telegram_message_id": None})
                states["summary_only"] += 1
                continue
        if c.get("report_class") not in REPORT_SCOPES:
            continue
        identity = report_identity(c)
        base = {"identity": identity, "report_class": c.get("report_class"), "instrument": c.get("instrument"),
                "strategy": f"{c.get('strategy_id')}@{c.get('strategy_version')}", "execution_authorized": False}
        _event(path, {**base, "stage": "INTENT", "recorded_at_utc": now.isoformat()})
        try:
            state = sender.send_report(c)
        except Exception as exc:  # noqa: BLE001 -- never auto-retried; recorded as such
            state = f"delivery_exception:{type(exc).__name__}"
        attempts = sender.delivery_attempts("report", [identity]) if state != "summary_only" else []
        meta = attempts[-1] if attempts else {}
        if state == "sent" and not meta.get("message_id"):
            state = "failed"
        _event(path, {**base, "stage": "RESULT", "recorded_at_utc": now.isoformat(), "delivery_state": state,
                      "telegram_message_id": meta.get("message_id")})
        states[state] += 1
    return [f"REPORT_DELIVERY {label} " + (" ".join(f"{k}={v}" for k, v in sorted(states.items())) or "none")]
