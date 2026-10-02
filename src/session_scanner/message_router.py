"""Additive adapter/router over authoritative Scanner and Checklist decisions.

No strategy or risk calculation belongs here: routing uses explicit upstream fields only.
"""
from __future__ import annotations

from dataclasses import fields
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from .message_models import MessageType, NormalizedMessage

_BLOCKED_RESULTS = {"BLOCKED", "INSUFFICIENT_DATA", "DATA_INVALID"}
_BLOCK_REASONS = {
    "INSUFFICIENT_DATA", "DATA_INVALID", "RISK_POLICY_AMBIGUOUS",
    "STRATEGY_CONTRACT_INCOMPLETE", "PROPOSAL_NOT_AUTHORIZED",
}


def _utc(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _reasons(source: Mapping[str, Any]) -> tuple[str, ...]:
    raw = source.get("reason_codes")
    if raw is None:
        raw = source.get("reason")
    if raw is None:
        return ()
    if isinstance(raw, str):
        return tuple(part.strip() for part in raw.split(",") if part.strip())
    return tuple(str(item) for item in raw)


def route_message(source: Mapping[str, Any], *, now_utc: Optional[datetime] = None) -> NormalizedMessage:
    """Normalize and route one upstream output without deriving trading eligibility."""
    now = _utc(now_utc or datetime.now(timezone.utc))
    timestamp = _utc(source.get("timestamp_utc") or source.get("utc_time")) or now
    result = str(source.get("result") or source.get("checklist_result") or "")
    strategy_status = source.get("strategy_status") or source.get("strategy_decision")
    proposal_eligible = source.get("proposal_eligible") is True
    opportunity = source.get("opportunity_detected") is True
    reasons = _reasons(source)
    system_event = source.get("system_event")

    if system_event is not None or source.get("is_system_event") is True:
        kind = MessageType.SYSTEM_STATUS
    elif result == "READY_FOR_PROPOSAL":
        kind = MessageType.INFORMATIONAL_TICKET
    elif strategy_status == "READY" and not proposal_eligible:
        kind = MessageType.INFORMATIONAL_TICKET
    elif opportunity and not proposal_eligible:
        kind = MessageType.OPPORTUNITY_ALERT
    elif result in {"NO_TRADE", "OUT_OF_SESSION"}:
        kind = MessageType.NO_TRADE_SUMMARY
    elif result in _BLOCKED_RESULTS or any(reason in _BLOCK_REASONS for reason in reasons):
        kind = MessageType.BLOCKED_ALERT
    else:
        # Unknown/non-final upstream states fail visibly rather than being promoted.
        kind = MessageType.BLOCKED_ALERT
        reasons = reasons or ("INSUFFICIENT_DATA",)

    expires = _utc(source.get("expires_at_utc") or source.get("expires_at"))
    expired = bool(expires and expires < now)
    governance_block = source.get("governance_block")
    if kind is MessageType.INFORMATIONAL_TICKET and not proposal_eligible and not governance_block:
        governance_block = source.get("risk_status") or (reasons[0] if reasons else "PROPOSAL_NOT_AUTHORIZED")

    # Checklist V1.1 nests the immutable Scanner ticket under ``proposal``. Flatten it
    # presentation-side; never mutate either upstream mapping.
    proposal = source.get("proposal") if isinstance(source.get("proposal"), Mapping) else {}
    adapted = dict(proposal)
    adapted.update({key: value for key, value in source.items() if value is not None})
    if "canonical_symbol" not in adapted:
        adapted["canonical_symbol"] = source.get("symbol")
    if "risk_status" not in adapted:
        adapted["risk_status"] = proposal.get("position_size_note")
    if "context" not in adapted:
        adapted["context"] = proposal.get("context_evidence") or proposal.get("market_context")
    if "location" not in adapted:
        adapted["location"] = proposal.get("location_evidence")
    if "trigger" not in adapted:
        adapted["trigger"] = proposal.get("trigger_evidence")
    if "targets" not in adapted:
        adapted["targets"] = tuple(value for value in
                                   (proposal.get("take_profit_1"), proposal.get("take_profit_2"))
                                   if value is not None)

    # Explicit allow-list prevents accidental transport/execution fields entering the model.
    values = {f.name: adapted.get(f.name) for f in fields(NormalizedMessage)}
    if kind is MessageType.SYSTEM_STATUS:
        for name in ("direction", "entry_reference", "entry_price", "stop_loss", "targets"):
            values[name] = () if name == "targets" else None
    values.update(
        message_type=kind,
        timestamp_utc=timestamp,
        strategy_status=strategy_status,
        checklist_result=result or None,
        proposal_eligible=proposal_eligible,
        execution_authorized=False,
        expires_at_utc=expires,
        reason_codes=reasons,
        governance_block=governance_block,
        opportunity_detected=opportunity,
        expired=expired,
        system_event=str(system_event) if system_event is not None else source.get("status_message"),
        targets=tuple(adapted.get("targets") or ()),
        checklist=source.get("checklist") or source.get("phases") or {},
        setup_valid=source.get("setup_valid") is True,
        data_source_degraded=source.get("data_source_degraded") is True,
    )
    return NormalizedMessage(**values)
