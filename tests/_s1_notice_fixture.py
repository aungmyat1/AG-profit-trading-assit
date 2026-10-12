"""Synthetic notice receipts for offline tests; never sends Telegram."""
from demo_execution.notification import NOTICE_KIND, notice_binding
from ticket_store.store import LIVE, build_outcome


def append_notice(store, ticket, now, *, delivered=True, **updates):
    payload = {"ticket_binding": notice_binding(ticket), "delivered": delivered,
               "channel": "TELEGRAM", "api_ok": delivered, "message_id": 1}
    payload.update(updates)
    receipt = build_outcome(ticket_id=ticket["ticket_id"], source=LIVE, outcome_kind=NOTICE_KIND,
                            recorded_at_utc=now.isoformat(), result="DELIVERED" if delivered is True else "FAILED",
                            payload=payload, provenance={"writer": "TEST_ONLY_SYNTHETIC_NOTICE"})
    store.append_outcome(receipt)
    return receipt
