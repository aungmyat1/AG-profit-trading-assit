"""LSMC observational lane (AGP-C18-R2).

Maps a WatchTracker AlertEvent (large_smc_watch.watch, unmodified) to a REPORT_ONLY observation:
DEVELOPING / NEAR_POI -> WATCH; an OPPORTUNITY with a C10 stop and a C11 target that passes the existing
opportunity gate -> priced CANDIDATE; a rejected opportunity -> BLOCKED with the specific evidence gap
(e.g. C10_PIP_SIZE_NOT_EVIDENCED, MISSING_SPREAD); INVALIDATED / EXPIRED -> NO_OPPORTUNITY. No stop or
target price is ever invented: a BLOCKED observation carries no levels.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from large_smc_watch.watch import opportunity_rejection
from reporting.common import archive_observation, observational_canonical

FAMILY = "large_smc"
CYCLE = "LSMC_WATCH"
_WATCH_STATES = {"DEVELOPING", "NEAR_POI"}
_CLOSED_STATES = {"INVALIDATED", "EXPIRED"}


def _base(event: Dict[str, Any]) -> Dict[str, Any]:
    return {"strategy_id": event.get("strategy_id"), "strategy_version": event.get("strategy_version"),
            "symbol": event.get("symbol"), "cycle": CYCLE, "session_date": event.get("trading_date"),
            "evaluated_at": event.get("evaluated_at"), "reference_id": event.get("reference_id"),
            "transition_id": event.get("transition_id")}


def _blocked_reasons(payload: Dict[str, Any], opportunity: Dict[str, Any], gate: Optional[str]) -> List[str]:
    reasons = [r for r in (gate, opportunity.get("stop_reason"), opportunity.get("target_reason")) if r]
    reasons += [str(r) for r in payload.get("reason_codes") or [] if r]
    return list(dict.fromkeys(reasons)) or ["REJECTED"]


def from_event(event: Dict[str, Any], *, now: dt.datetime, price: Optional[float] = None,
               policy=None) -> Dict[str, Any]:
    payload = event.get("payload") or {}
    opportunity = payload.get("opportunity") or {}
    base = _base(event)
    state = event.get("to_state")
    if state in _WATCH_STATES:
        poi = payload.get("poi") or {}
        raw = {**base, "decision": "NO_TRADE", "reason_code": f"LSMC_{state}",
               "direction": poi.get("direction") or payload.get("bias")}
        return observational_canonical(raw, now=now, current_price=price, report_class="WATCH", policy=policy)
    if state in _CLOSED_STATES:
        raw = {**base, "decision": "NO_TRADE", "reason_code": f"LSMC_{state}"}
        return observational_canonical(raw, now=now, report_class="NO_OPPORTUNITY", policy=policy)
    gate = opportunity_rejection(opportunity, price) if opportunity else "REJECT_NO_OPPORTUNITY_PAYLOAD"
    if state == "OPPORTUNITY" and gate is None:
        raw = {**base, "decision": "SHADOW_INFO_ONLY", "reason_code": "LSMC_OPPORTUNITY",
               "direction": opportunity.get("direction"), "entry": opportunity.get("entry_reference"),
               "stop_loss": opportunity.get("stop_c10"), "tp1": opportunity.get("target_c11"),
               "signal_timestamp": opportunity.get("choch_time")}
        return observational_canonical(raw, now=now, current_price=price, report_class="CANDIDATE", policy=policy)
    reasons = _blocked_reasons(payload, opportunity, gate)
    raw = {**base, "decision": "BLOCKED", "reason_code": reasons[0], "block_reasons": reasons,
           "direction": opportunity.get("direction")}
    canonical = observational_canonical(raw, now=now, report_class="BLOCKED", policy=policy)
    canonical["reason_codes"] = list(dict.fromkeys(list(canonical.get("reason_codes") or []) + reasons))
    return canonical


def observe_events(events, *, now: dt.datetime, price: Optional[float], archive_root: str,
                   policy=None) -> List[Dict[str, Any]]:
    """Archive one observation per WatchTracker transition (the tracker already dedupes transitions)."""
    out = []
    for event in events:
        canonical = from_event(event if isinstance(event, dict) else dict(event.__dict__), now=now, price=price,
                               policy=policy)
        archive_observation(archive_root, FAMILY, canonical)
        out.append(canonical)
    return out
