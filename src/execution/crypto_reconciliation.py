"""Restart reconciliation (spec item 9): (local journal state, mocked exchange open
orders, mocked exchange positions) -> a reconciled view. All three inputs are plain
data (lists of dicts) supplied by the caller -- test fixtures/mocks in every call in this
phase; this module makes no network call and does not know how to fetch any of the three
inputs itself.

Fail-closed: any local/exchange disagreement this module cannot resolve unambiguously
comes back tagged STATE_AMBIGUOUS with a specific reason_code, never silently resolved by
a guess (e.g. "assume it filled" or "assume it didn't").
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

STATE_CONFIRMED_OPEN = "CONFIRMED_OPEN"
STATE_CONFIRMED_ABSENT = "CONFIRMED_ABSENT"
STATE_AMBIGUOUS = "AMBIGUOUS"

REASON_NO_EXCHANGE_EVIDENCE_FOR_CLAIM = "RECONCILIATION_AMBIGUOUS_NO_EXCHANGE_EVIDENCE_FOR_CLAIM"
REASON_LOCAL_EXECUTED_NOT_FOUND = "RECONCILIATION_AMBIGUOUS_LOCAL_EXECUTED_NOT_FOUND"
REASON_MULTIPLE_EXCHANGE_MATCHES = "RECONCILIATION_AMBIGUOUS_MULTIPLE_EXCHANGE_MATCHES"


@dataclass(frozen=True)
class ReconciledCommandState:
    command_id: str
    state: str  # STATE_CONFIRMED_OPEN / STATE_CONFIRMED_ABSENT / STATE_AMBIGUOUS
    reason_code: Optional[str] = None
    exchange_order_id: Optional[str] = None


def _matches(client_order_id: Optional[str], rows: Sequence[dict]) -> List[dict]:
    if not client_order_id:
        return []
    return [r for r in rows if r.get("clientOrderId") == client_order_id]


def reconcile(
    local_journal_entries: Sequence[dict],
    exchange_open_orders: Sequence[dict],
    exchange_positions: Sequence[dict],
) -> List[ReconciledCommandState]:
    """Each entry in local_journal_entries is expected to carry at least `command_id`,
    `client_order_id`, and `validation_state` (the last event recorded for that command --
    see execution/crypto_journal.py's own event shapes, e.g. "CLAIMED" or "EXECUTED").
    exchange_open_orders/exchange_positions entries are matched by `clientOrderId` (the
    field Binance's own API responses use), never by command_id (the exchange has no
    notion of this repo's command_id).
    """
    results: List[ReconciledCommandState] = []
    for entry in local_journal_entries:
        command_id = entry.get("command_id")
        client_order_id = entry.get("client_order_id")
        local_state = entry.get("validation_state")

        order_matches = _matches(client_order_id, exchange_open_orders)
        position_matches = _matches(client_order_id, exchange_positions)
        total_matches = order_matches + position_matches

        if len(order_matches) > 1 or len(position_matches) > 1:
            results.append(ReconciledCommandState(command_id, STATE_AMBIGUOUS, REASON_MULTIPLE_EXCHANGE_MATCHES))
            continue

        found = bool(total_matches)

        if found:
            match = total_matches[0]
            exchange_order_id = match.get("orderId")
            results.append(ReconciledCommandState(
                command_id, STATE_CONFIRMED_OPEN,
                exchange_order_id=str(exchange_order_id) if exchange_order_id is not None else None,
            ))
            continue

        if local_state == "CLAIMED":
            # Locally claimed but the process crashed before any confirmation, and the
            # exchange shows nothing under this client_order_id. This is genuinely
            # ambiguous: it could mean the order was never sent, OR it was sent and
            # already filled+closed, OR it was sent and rejected. Never guess.
            results.append(ReconciledCommandState(command_id, STATE_AMBIGUOUS, REASON_NO_EXCHANGE_EVIDENCE_FOR_CLAIM))
        elif local_state == "EXECUTED":
            # Local state claims a fill, but no exchange evidence confirms it now (could be
            # closed since, or the local record is simply wrong) -- fail closed rather than
            # trusting the local "EXECUTED" label at face value.
            results.append(ReconciledCommandState(command_id, STATE_AMBIGUOUS, REASON_LOCAL_EXECUTED_NOT_FOUND))
        else:
            # No local claim/execution evidence, and nothing on the exchange either --
            # this command genuinely never reached the exchange. Safe to confirm absent.
            results.append(ReconciledCommandState(command_id, STATE_CONFIRMED_ABSENT))

    return results
