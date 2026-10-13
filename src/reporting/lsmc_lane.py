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
from reporting.common import archive_observation, block, observational_canonical

FAMILY = "large_smc"
CYCLE = "LSMC_WATCH"
_WATCH_STATES = {"DEVELOPING", "NEAR_POI"}
_CLOSED_STATES = {"INVALIDATED", "EXPIRED"}


def _base(event: Dict[str, Any]) -> Dict[str, Any]:
    return {"strategy_id": event.get("strategy_id"), "strategy_version": event.get("strategy_version"),
            "symbol": event.get("symbol"), "cycle": CYCLE, "session_date": event.get("trading_date"),
            "evaluated_at": event.get("evaluated_at"), "reference_id": event.get("reference_id"),
            "transition_id": event.get("transition_id")}


# Informational engine badges (e.g. D30: economics not evaluated) are notes, never blocking reasons.
INFORMATIONAL_CODES = frozenset({"D30_BADGE_ECONOMICS_NOT_EVALUATED"})


def _blocked_reasons(payload: Dict[str, Any], opportunity: Dict[str, Any], gate: Optional[str]) -> List[str]:
    """Specific evidence gap (stop / target reason) first, then the generic gate code, then other engine
    reasons; informational badges are excluded (see _notes)."""
    reasons = [r for r in (opportunity.get("stop_reason"), opportunity.get("target_reason"), gate) if r]
    reasons += [str(r) for r in payload.get("reason_codes") or [] if r]
    reasons = [r for r in dict.fromkeys(reasons) if r not in INFORMATIONAL_CODES]
    return reasons or ["REJECTED"]


def _notes(payload: Dict[str, Any]) -> List[str]:
    return [str(r) for r in payload.get("reason_codes") or [] if r in INFORMATIONAL_CODES]


def from_event(event: Dict[str, Any], *, now: dt.datetime, price: Optional[float] = None,
               policy=None) -> Dict[str, Any]:
    """Observation plus a stable setup identity (the tracker's reference id) and the transition. A WATCH
    is identified per setup, so NEAR_POI <-> DEVELOPING churn on one setup reports once; a different
    setup (new reference, e.g. a SHORT POI followed by a LONG POI) is a new observation."""
    canonical = _from_event(event, now=now, price=price, policy=policy)
    reference = event.get("reference_id")
    canonical["setup_id"] = reference
    canonical["transition"] = f"{event.get('from_state')}->{event.get('to_state')}"
    canonical["lsmc"] = _lsmc_details(event, canonical, price)
    if canonical.get("report_class") == "WATCH" and reference:
        canonical["candidate_signal_id"] = (f"{event.get('strategy_id')}@{event.get('strategy_version')}|"
                                            f"{event.get('symbol')}|{CYCLE}|SETUP|{reference}")
    return canonical


def _lsmc_details(event: Dict[str, Any], canonical: Dict[str, Any], price: Optional[float]) -> Dict[str, Any]:
    """POI zone / expiry / distance for the owner-approved alert layout (formatted to the symbol digits)."""
    from v1_tickets.canonical_ticket import _fmt
    payload = event.get("payload") or {}
    poi, opportunity = payload.get("poi") or {}, payload.get("opportunity") or {}
    symbol = canonical.get("instrument")
    low, high = poi.get("low"), poi.get("high")
    distance = None
    if price is not None and low is not None and high is not None:
        distance = 0.0 if low <= price <= high else (price - high if price > high else low - price)
    return {"poi_kind": poi.get("kind"), "poi_low": _fmt(low, symbol) if low is not None else None,
            "poi_high": _fmt(high, symbol) if high is not None else None, "distance_to_poi": distance,
            "expires_at": opportunity.get("expires_at") or payload.get("expires_at")}


def _from_event(event: Dict[str, Any], *, now: dt.datetime, price: Optional[float] = None,
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
    canonical["reason_code"] = reasons[0]
    canonical["reason_codes"] = reasons
    canonical["notes"] = _notes(payload)
    return canonical


def observe_events(events, *, now: dt.datetime, price: Optional[float], archive_root: str,
                   policy=None, bid: Optional[float] = None, ask: Optional[float] = None,
                   account: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Archive one observation per WatchTracker transition (the tracker already dedupes transitions).
    `bid`/`ask` are the fresh read-only MT5 tick the snapshot was evaluated with (None when missing or
    stale: a SHORT then stays BLOCKED MISSING_SPREAD; no synthetic spread). `account` = read-only
    {"balance", "commission_R"} for the display-only sizing preview."""
    from reporting.sizing_preview import attach_inputs
    account = account or {}
    out = []
    for event in events:
        canonical = from_event(event if isinstance(event, dict) else dict(event.__dict__), now=now, price=price,
                               policy=policy)
        attach_inputs(canonical, bid=bid, ask=ask, commission_R=account.get("commission_R"),
                      balance=account.get("balance"), account_currency=account.get("currency"),
                      quote_time=now.isoformat())      # the tick passed here is <= STALE_MIN old
        if canonical.get("report_class") == "CANDIDATE":
            canonical["verification_status"] = canonical.get("scope_verification_status") or "UNVERIFIED"
            if canonical["verification_status"] == "SUSPENDED":
                block(canonical, "SCOPE_SUSPENDED")
        archive_observation(archive_root, FAMILY, canonical)
        out.append(canonical)
    return out


def version_selection():
    """Configured report version; the registered frozen version remains 1.1.0."""
    from reporting.lsmc_version import selected_version
    return selected_version()
