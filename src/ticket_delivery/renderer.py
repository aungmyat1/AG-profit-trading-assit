"""WP2 (docs/plans/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1.md) -- canonical
informational ticket renderer. Wraps ALREADY-PERSISTED strategy-owned proposal/decision
data (the same shape post_asian_pilot.report.render_entry_ticket() already produces);
this module never computes entry/stop/target/risk/direction itself, and never calls
strategy_engine or any strategy-evaluation path.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

INFORMATIONAL_LABEL = "INFORMATIONAL PROPOSAL -- NOT A BROKER ORDER"

DECISION_READY = "READY"
DECISION_WATCH = "WATCH"
DECISION_NO_TRADE = "NO_TRADE"
DECISION_DATA_ERROR = "DATA_ERROR"
DECISION_BLOCKED = "BLOCKED"
_RENDERABLE_DECISIONS = {DECISION_READY}

REASON_NOT_READY = "DECISION_NOT_READY"
REASON_MISSING_FIELDS = "MISSING_MANDATORY_FIELDS"

# Dotted paths into the source proposal dict (post_asian_pilot.report.render_entry_ticket()
# shape) that MUST be present and non-None for a ticket to render. Fail-closed, never
# defaulted/invented, per WP2.
_MANDATORY_PATHS: Tuple[Tuple[str, ...], ...] = (
    ("identity", "setup_id"),
    ("strategy", "strategy_id"),
    ("strategy", "strategy_version"),
    ("application", "release_id"),
    ("market", "symbol"),
    ("market", "direction"),
    ("entry", "entry"),
    ("entry", "stop_loss"),
    ("entry", "tp1"),
    ("risk", "risk_percent"),
    ("risk", "normalized_volume"),
    ("timing", "created_at"),
    ("timing", "expires_at"),
    ("evidence", "reason_codes"),
)


@dataclass(frozen=True)
class RenderResult:
    status: str  # "RENDERED" | "BLOCKED"
    reason_code: Optional[str] = None
    missing_fields: Tuple[str, ...] = ()
    payload: Optional[Dict[str, Any]] = None
    payload_hash: Optional[str] = None


def _get_path(d: Dict[str, Any], path: Tuple[str, ...]) -> Any:
    cur: Any = d
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _canonical_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))


def payload_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def render_informational_ticket(
    *, logical_ticket_id: str, cycle: str, trading_date: str, decision_status: str,
    proposal: Dict[str, Any], venue: str = "MT5", freshness_status: str = "UNKNOWN",
) -> RenderResult:
    """`proposal` is the EXISTING render_entry_ticket()-shaped dict (or an equivalent
    subset) -- read verbatim, never recomputed. `decision_status` gates rendering:
    only READY renders a ticket; WATCH/NO_TRADE/DATA_ERROR/BLOCKED all return a
    non-RENDERED result (they remain archived by ticket_delivery.archive, but are never
    turned into a ticket) -- see test_watch_no_trade_data_error_blocked_never_render."""
    if decision_status not in _RENDERABLE_DECISIONS:
        return RenderResult(status="BLOCKED", reason_code=REASON_NOT_READY)

    missing = tuple(
        ".".join(path) for path in _MANDATORY_PATHS
        if _get_path(proposal, path) in (None, "", [])
    )
    if missing:
        return RenderResult(status="BLOCKED", reason_code=REASON_MISSING_FIELDS, missing_fields=missing)

    payload = {
        "label": INFORMATIONAL_LABEL,
        "logical_ticket_id": logical_ticket_id,
        "proposal_id": _get_path(proposal, ("identity", "proposal_id")),
        "setup_id": _get_path(proposal, ("identity", "setup_id")),
        "strategy_id": _get_path(proposal, ("strategy", "strategy_id")),
        "strategy_version": _get_path(proposal, ("strategy", "strategy_version")),
        "application_release": _get_path(proposal, ("application", "release_id")),
        "symbol": _get_path(proposal, ("market", "symbol")),
        "cycle": cycle,
        "trading_date": trading_date,
        "direction": _get_path(proposal, ("market", "direction")),
        "entry": _get_path(proposal, ("entry", "entry")),
        "stop_loss": _get_path(proposal, ("entry", "stop_loss")),
        "tp1": _get_path(proposal, ("entry", "tp1")),
        "tp2_runner": _get_path(proposal, ("entry", "tp2_runner")),
        "risk_percent": _get_path(proposal, ("risk", "risk_percent")),
        "normalized_volume": _get_path(proposal, ("risk", "normalized_volume")),
        "reason_codes": list(_get_path(proposal, ("evidence", "reason_codes")) or []),
        "created_at": _get_path(proposal, ("timing", "created_at")),
        "expires_at": _get_path(proposal, ("timing", "expires_at")),
        "venue": venue,
        "freshness_status": freshness_status,
        "authorization": {
            "strategy_authorized": False, "execution_authorized": False,
            "note": "advisory/informational only -- no broker order is created or implied by this message",
        },
    }
    return RenderResult(status="RENDERED", payload=payload, payload_hash=payload_hash(payload))


def format_message_text(payload: Dict[str, Any]) -> str:
    """Plain-text rendering for message-only delivery -- no inline keyboard, no buttons,
    no callback_data (WP5: message-only, never approval-shaped)."""
    lines = [
        payload["label"], "",
        f"{payload['symbol']}  {payload['direction']}  ({payload['cycle']})",
        f"Strategy: {payload['strategy_id']} v{payload['strategy_version']} (release {payload['application_release']})",
        f"Entry: {payload['entry']}   SL: {payload['stop_loss']}   TP1: {payload['tp1']}"
        + (f"   TP2: {payload['tp2_runner']}" if payload.get("tp2_runner") is not None else ""),
        f"Risk: {payload['risk_percent']}%   Volume: {payload['normalized_volume']}",
        f"Reason: {', '.join(payload['reason_codes']) if payload['reason_codes'] else 'N/A'}",
        f"Created: {payload['created_at']}   Expires: {payload['expires_at']}",
        f"Venue: {payload['venue']}   Freshness: {payload['freshness_status']}",
        "", f"Ticket: {payload['logical_ticket_id']}",
        "", "Execution authority: DISABLED for this message. This is not a broker order.",
    ]
    return "\n".join(lines)
