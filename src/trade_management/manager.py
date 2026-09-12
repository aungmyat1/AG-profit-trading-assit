"""Orchestrates one management cycle for one claimed ticket:

read position -> reconcile state -> evaluate the applicable rule -> validate -> gateway
-> journal -> persist state.

This is the only module that sequences MT5 reads + the gateway + the pure
claims/state/rules/validator functions together; scripts/manage_positions.py just loops
this over every claimed ticket. Kept deliberately thin -- all actual decision logic lives
in rules.py/validator.py/state.py, which are pure and independently tested.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from mt5 import account as mt5_account
from mt5 import management_gateway
from mt5.market_data import get_tick
from mt5.symbol_resolver import get_symbol_meta
from notifications.trade_management_alerts import notify_confirmed_action, notify_position_closed

from . import journal
from .close_reason import resolve_close_reason
from .claims import load_claims
from .models import (
    ACTION_CLOSE,
    ACTION_HOLD,
    ACTION_MOVE_SL,
    ACTION_PARTIAL_CLOSE,
    STATE_BREAKEVEN_DONE,
    STATE_CLOSED,
    STATE_MANAGED_OPEN,
    STATE_MANAGEMENT_BLOCKED,
    STATE_RUNNER_ACTIVE,
    STATE_TP1_PARTIAL_DONE,
    STATE_TP1_PENDING,
    ManagementIntent,
)
from .position_monitor import CLASSIFICATION_FOREIGN, classify, normalize_position
from .rules import evaluate_breakeven, evaluate_exit, evaluate_partial_profit
from .state import load_state, reconcile, save_state
from .state import REASON_OK as RECONCILE_OK
from .validator import validate


@dataclass(frozen=True)
class CycleResult:
    ticket: int
    outcome: str  # e.g. "HOLD", "EXECUTED", "DRY_RUN", "BLOCKED", "CLOSED", "FOREIGN"
    detail: str
    intent: Optional[ManagementIntent] = None


def run_cycle_for_ticket(
    ticket: int,
    claims_path: str = "journal/claims.json",
    base_dir: str = "journal",
    expected_action: Optional[str] = None,
) -> CycleResult:
    claims = load_claims(claims_path)
    claim = claims.get(ticket)
    if claim is None:
        return CycleResult(ticket=ticket, outcome="FOREIGN", detail=CLASSIFICATION_FOREIGN)

    account = mt5_account.account()
    raw_positions = mt5_account.positions(ticket=ticket)
    tick = get_tick(claim.symbol) if raw_positions else None
    position = normalize_position(raw_positions[0], tick, account) if raw_positions else None

    classification = classify(ticket, claims, position)

    record = load_state(ticket, base_dir)
    record, reconcile_reason = reconcile(claim, record, position)
    save_state(record, base_dir)

    if position is None and record.state == STATE_CLOSED:
        _notify_broker_side_close(ticket, claim.symbol, base_dir)

    if reconcile_reason != RECONCILE_OK:
        journal.record_event(ticket, "MANAGEMENT_BLOCKED", base_dir, reason_code=reconcile_reason)
        return CycleResult(ticket=ticket, outcome="BLOCKED", detail=reconcile_reason)

    if record.state == STATE_CLOSED:
        return CycleResult(ticket=ticket, outcome="CLOSED", detail="POSITION_CLOSED")

    if position is None:
        return CycleResult(ticket=ticket, outcome="BLOCKED", detail="POSITION_NOT_FOUND")

    symbol_meta = get_symbol_meta(claim.symbol)

    if record.state in (STATE_MANAGED_OPEN, STATE_TP1_PENDING):
        intent = evaluate_partial_profit(claim, position, record, symbol_meta)
    elif record.state == STATE_TP1_PARTIAL_DONE:
        intent = evaluate_breakeven(claim, position, record)
    elif record.state in (STATE_BREAKEVEN_DONE, STATE_RUNNER_ACTIVE):
        intent = evaluate_exit(claim, position, record)
    else:
        return CycleResult(ticket=ticket, outcome="BLOCKED", detail=f"UNMANAGEABLE_STATE:{record.state}")

    if intent.action == ACTION_HOLD:
        return CycleResult(ticket=ticket, outcome="HOLD", detail=intent.reason_code, intent=intent)

    completed_ids = journal.completed_intent_ids(ticket, base_dir)
    validation = validate(intent, claim, position, completed_ids, symbol_meta)
    if not validation.ok:
        journal.record_event(
            ticket, "MANAGEMENT_BLOCKED", base_dir, reason_code=validation.reason_code, intent_id=intent.intent_id
        )
        return CycleResult(ticket=ticket, outcome="BLOCKED", detail=validation.reason_code, intent=intent)

    if expected_action is not None and intent.action != expected_action:
        return CycleResult(
            ticket=ticket,
            outcome="BLOCKED",
            detail=f"REQUESTED_ACTION_NOT_ELIGIBLE:{expected_action}:NEXT_ACTION:{intent.action}",
            intent=intent,
        )

    journal.record_event(
        ticket,
        f"{intent.action}_REQUESTED",
        base_dir,
        intent_id=intent.intent_id,
        reason_code=intent.reason_code,
        requested_volume=intent.requested_volume,
        new_sl=intent.new_sl,
    )

    gateway_result = _dispatch(intent, claim, position)

    if gateway_result.dry_run:
        journal.record_event(ticket, f"{intent.action}_DRY_RUN", base_dir, intent_id=intent.intent_id, request=gateway_result.request)
        return CycleResult(ticket=ticket, outcome="DRY_RUN", detail=intent.action, intent=intent)

    if gateway_result.violation:
        record = record.with_update(state=STATE_MANAGEMENT_BLOCKED)
        save_state(record, base_dir)
        journal.record_event(ticket, "CRITICAL_MANAGEMENT_VIOLATION", base_dir, detail=gateway_result.violation)
        return CycleResult(ticket=ticket, outcome="BLOCKED", detail=gateway_result.violation, intent=intent)

    if not gateway_result.executed:
        journal.record_event(
            ticket, f"{intent.action}_REJECTED", base_dir, intent_id=intent.intent_id, comment=gateway_result.comment
        )
        return CycleResult(ticket=ticket, outcome="BROKER_REJECTED", detail=str(gateway_result.comment), intent=intent)

    journal.record_event(
        ticket,
        f"{intent.action}_CONFIRMED",
        base_dir,
        intent_id=intent.intent_id,
        volume_after=gateway_result.volume_after,
    )
    try:
        notify_confirmed_action(ticket, claim.symbol, intent.action, reason_code=intent.reason_code, base_dir=base_dir)
    except Exception:  # noqa: BLE001 -- a notification failure must never affect this state transition
        pass
    record = _advance_state(record, intent, gateway_result.volume_after)
    save_state(record, base_dir)
    return CycleResult(ticket=ticket, outcome="EXECUTED", detail=intent.action, intent=intent)


_CLOSE_DETECTED_EVENT = "BROKER_SIDE_CLOSE_DETECTED"


def _notify_broker_side_close(ticket: int, symbol: str, base_dir: str) -> None:
    """The position is gone broker-side (stop-loss hit, broker TP, manual close, stop
    out). Before this hook existed, reconcile() moved the record to STATE_CLOSED and the
    cycle returned silently -- so breakeven/partial/TP-exit alerted but an SL hit never
    did.

    Idempotency is journal-backed, not state-backed: the durable
    BROKER_SIDE_CLOSE_DETECTED event is what suppresses a second alert on restart or on
    any later re-reconcile of the same closed ticket. It is written BEFORE the Telegram
    attempt, so a transport failure still cannot turn into a repeat-alert loop (the
    separate {event}_TELEGRAM_NOTIFY_FAILED record is the audit trail for that).

    A close this manager itself performed already fired CLOSE_CONFIRMED +
    notify_confirmed_action, so it is skipped here rather than double-reported.

    Never raises: notification is a side effect of an already-committed reconciliation.
    """
    try:
        events = journal.read_events(ticket, base_dir)
        seen = {e.get("event") for e in events}
        if _CLOSE_DETECTED_EVENT in seen:
            return  # already detected + notified on an earlier cycle
        if "CLOSE_CONFIRMED" in seen:
            # our own managed exit -- notify_confirmed_action("CLOSE") already reported it
            journal.record_event(ticket, _CLOSE_DETECTED_EVENT, base_dir, close_reason="SELF_MANAGED_CLOSE", notified=False)
            return

        close_reason = resolve_close_reason(ticket)
        journal.record_event(ticket, _CLOSE_DETECTED_EVENT, base_dir, close_reason=close_reason, notified=True)
        notify_position_closed(ticket, symbol, close_reason, base_dir=base_dir)
    except Exception:  # noqa: BLE001 -- must never affect the reconciled state transition
        pass


def _dispatch(intent: ManagementIntent, claim, position) -> "management_gateway.GatewayResult":
    if intent.action == ACTION_PARTIAL_CLOSE:
        return management_gateway.partial_close_position(
            claim.ticket, claim.symbol, claim.direction, intent.requested_volume, position.current_price
        )
    if intent.action == ACTION_MOVE_SL:
        return management_gateway.modify_position_sl(claim.ticket, claim.symbol, intent.new_sl)
    if intent.action == ACTION_CLOSE:
        return management_gateway.close_position(
            claim.ticket, claim.symbol, claim.direction, intent.requested_volume, position.current_price
        )
    raise ValueError(f"Unhandled action: {intent.action}")


def _advance_state(record, intent: ManagementIntent, volume_after: Optional[float]):
    if intent.action == ACTION_PARTIAL_CLOSE:
        return record.with_update(
            state=STATE_TP1_PARTIAL_DONE,
            confirmed_partial_volume=volume_after,
            last_completed_intent_id=intent.intent_id,
        )
    if intent.action == ACTION_MOVE_SL:
        return record.with_update(
            state=STATE_RUNNER_ACTIVE,
            breakeven_confirmed=True,
            last_completed_intent_id=intent.intent_id,
        )
    if intent.action == ACTION_CLOSE:
        return record.with_update(state=STATE_CLOSED, last_completed_intent_id=intent.intent_id)
    return record
