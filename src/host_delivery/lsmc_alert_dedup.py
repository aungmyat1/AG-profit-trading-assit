"""Delivery-layer exactly-once for Large-SMC OPPORTUNITY alerts (audit 2026-10-07, finding LSMC-DUP).

WatchTracker emits a transition whenever state or reference changes, which is correct for the
archive but not for delivery: a STALE poll suspends an OPPORTUNITY and the next FRESH poll
re-enters it with the identical ref (GBPUSD 2026-10-06 17:48/18:38 UTC), and a sibling sweep
re-anchors the same CHoCH under a new ref (BTCUSDT 17:58/18:53 UTC). Both re-alerted.

The confirmation identity is strategy + version + symbol + direction + POI + CHoCH bar. Sweep
anchor, invalidation, stop and target are parameters of a confirmation, not a new one. This
module only decides whether to *send*; detection output, transitions and archive records are
unchanged. The ledger persists, so a restart between evaluations cannot re-send.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from runtime_state.store import JsonKeyValueStore

SENT = "SENT"


def confirmation_key(event: Dict[str, Any]) -> Optional[str]:
    """Identity of the confirmed setup behind an OPPORTUNITY event; None when not derivable."""
    opp = (event.get("payload") or {}).get("opportunity") or {}
    parts = (event.get("strategy_id"), event.get("strategy_version"), event.get("symbol"),
             opp.get("direction"), opp.get("poi_id"), opp.get("choch_time"))
    return "|".join(str(p) for p in parts) if all(parts) else None


class AlertLedger:
    """Persistent set of confirmation keys already delivered (status SENT)."""

    def __init__(self, path: str):
        self.store = JsonKeyValueStore(path)

    def delivered(self, key: str) -> bool:
        return self.store.get(key) is not None

    def mark(self, key: str, record: Dict[str, Any]) -> None:
        self.store.put(key, record)


def deliver_once(event: Dict[str, Any], ledger: Optional[AlertLedger], send: Callable[[], str]) -> str:
    """Call `send()` unless this event's confirmation was already delivered. Returns the send
    status, or 'SUPPRESSED_DUPLICATE_CONFIRMATION'. Only a SENT status is recorded, so a failed
    or policy-blocked attempt never blocks a later genuine delivery."""
    key = confirmation_key(event) if ledger is not None and event.get("to_state") == "OPPORTUNITY" else None
    if key is not None and ledger.delivered(key):
        return "SUPPRESSED_DUPLICATE_CONFIRMATION"
    status = send()
    if key is not None and status == SENT:
        ledger.mark(key, {"reference_id": event.get("reference_id"), "transition_id": event.get("transition_id"),
                          "evaluated_at": event.get("evaluated_at")})
    return status
