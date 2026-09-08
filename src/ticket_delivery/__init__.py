"""Exactly-once informational FX ticket delivery foundation
(docs/plans/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1.md WP1/WP3/WP6). ADVISORY /
INFORMATIONAL ONLY -- no module in this package imports or calls execution.executor,
execution.mt5_gateway, mt5.management_gateway, or any broker order-submission boundary;
see tests/test_ticket_delivery_execution_boundary.py for the static guard.
"""
from .archive import CycleDecisionRecord, archive_cycle_decision
from .attempt_journal import AttemptJournal
from .identity import correction_id, delivery_attempt_id, logical_ticket_id
from .models import (
    ALL_STATES,
    STATE_DELIVERED,
    STATE_DELIVERY_AMBIGUOUS,
    STATE_DELIVERY_CLAIMED,
    STATE_DELIVERY_FAILED_RETRYABLE,
    STATE_DELIVERY_FAILED_TERMINAL,
    STATE_NOT_APPLICABLE,
    STATE_READY_TO_DELIVER,
)
from .delivery_store import TicketDeliveryStore
from .fx_cycle_integration import PairOutcome, process_pair_result
from .policy import CatchUpPolicy, RetryPolicy
from .telegram_adapter import (
    DeliveryOutcome,
    TelegramConfigError,
    TelegramDestinationConfig,
    deliver_informational_ticket,
    deliver_informational_ticket_with_retry,
)

__all__ = [
    "CycleDecisionRecord", "archive_cycle_decision",
    "logical_ticket_id", "delivery_attempt_id", "correction_id",
    "TicketDeliveryStore",
    "ALL_STATES", "STATE_NOT_APPLICABLE", "STATE_READY_TO_DELIVER", "STATE_DELIVERY_CLAIMED",
    "STATE_DELIVERED", "STATE_DELIVERY_FAILED_RETRYABLE", "STATE_DELIVERY_FAILED_TERMINAL",
    "STATE_DELIVERY_AMBIGUOUS",
    "process_pair_result", "PairOutcome",
    "CatchUpPolicy", "RetryPolicy",
    "AttemptJournal",
    "TelegramConfigError", "TelegramDestinationConfig", "DeliveryOutcome",
    "deliver_informational_ticket", "deliver_informational_ticket_with_retry",
]
