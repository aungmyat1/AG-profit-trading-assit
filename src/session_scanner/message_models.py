"""Typed, transport-neutral owner message contract for Scanner/Checklist output.

These models are presentation data only.  In particular, an informational ticket is not
an order and an opportunity is not authorization to trade.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Optional, Tuple


class MessageType(str, Enum):
    INFORMATIONAL_TICKET = "INFORMATIONAL_TICKET"
    OPPORTUNITY_ALERT = "OPPORTUNITY_ALERT"
    NO_TRADE_SUMMARY = "NO_TRADE_SUMMARY"
    BLOCKED_ALERT = "BLOCKED_ALERT"
    SYSTEM_STATUS = "SYSTEM_STATUS"


@dataclass(frozen=True)
class NormalizedMessage:
    message_type: MessageType
    timestamp_utc: datetime
    canonical_symbol: Optional[str] = None
    broker_symbol: Optional[str] = None
    asset_class: Optional[str] = None
    strategy_id: Optional[str] = None
    strategy_version: Optional[str] = None
    strategy_status: Optional[str] = None
    economic_status: Optional[str] = None
    session: Optional[str] = None
    direction: Optional[str] = None
    context: Any = None
    location: Any = None
    trigger: Any = None
    entry_reference: Any = None
    entry_type: Optional[str] = None
    entry_price: Any = None
    stop_loss: Any = None
    targets: Tuple[Any, ...] = ()
    invalidation: Any = None
    poi: Any = None
    current_price: Any = None
    distance_to_poi: Any = None
    risk_status: Optional[str] = None
    risk_pct: Any = None
    risk_amount: Any = None
    position_size: Any = None
    setup_valid: bool = False
    proposal_eligible: bool = False
    execution_authorized: bool = False
    expires_at_utc: Optional[datetime] = None
    data_source: Optional[str] = None
    data_freshness: Optional[str] = None
    data_source_degraded: bool = False
    checklist_result: Optional[str] = None
    checklist: Mapping[str, Any] = field(default_factory=dict)
    reason_codes: Tuple[str, ...] = ()
    governance_block: Optional[str] = None
    opportunity_detected: bool = False
    expired: bool = False
    system_event: Optional[str] = None

    def __post_init__(self) -> None:
        # Hard project-stage invariant, independent of untrusted/adapted input.
        if self.execution_authorized:
            raise ValueError("message output cannot carry execution authority")
        if self.message_type is MessageType.SYSTEM_STATUS:
            trading = (self.direction, self.entry_reference, self.entry_price, self.stop_loss, self.targets)
            if any(value not in (None, ()) for value in trading):
                raise ValueError("system status cannot carry trade geometry")
