"""Lifecycle events for the C3 execution-message builders (no message text here).

The guard and the reconciliation monitor emit one event per execution milestone to an injected sink.
A sink is observational: it never decides anything, and a sink that raises is ignored so a delivery
failure can never change an order step.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional

SENT = "SENT"
BROKER_ACK = "BROKER_ACK"
FILLED = "FILLED"
SEND_UNKNOWN = "SEND_UNKNOWN"
CHECK_REJECTED = "CHECK_REJECTED"
CLOSED = "CLOSED"
EVENT_KINDS = (SENT, BROKER_ACK, FILLED, SEND_UNKNOWN, CHECK_REJECTED, CLOSED)

EventSink = Callable[["LifecycleEvent"], Any]


@dataclass(frozen=True)
class LifecycleEvent:
    kind: str
    ticket_id: str
    at_utc: str
    reason_code: Optional[str] = None
    broker_order_id: Optional[str] = None
    broker_deal_id: Optional[str] = None
    broker_position_id: Optional[str] = None
    details: Mapping[str, Any] = field(default_factory=dict)


def emit(sink: Optional[EventSink], event: LifecycleEvent) -> bool:
    """Deliver to the sink; True when delivered. A missing or failing sink is never an error."""
    if sink is None or event.kind not in EVENT_KINDS:
        return False
    try:
        sink(event)
    except Exception:  # noqa: BLE001 -- observational only
        return False
    return True
