"""Read-only diagnostics from archived facts. Never strategy or order authority."""
from __future__ import annotations

import datetime as dt
import math

NA = "NOT_AVAILABLE"


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def _time(value):
    try:
        parsed = dt.datetime.fromisoformat(value)
        return parsed if parsed.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def diagnostic_lines(event):
    """No quote, cost, partial-stage or expiry inference from a completed badge."""
    payload = event.get("payload") or {}
    opp = payload.get("opportunity") or {}
    now, expiry = _time(event.get("evaluated_at")), _time(opp.get("expires_at"))
    signal = _time(opp.get("choch_time"))
    freshness = NA
    if now and expiry and signal and signal <= now < expiry:
        freshness = "AT_EVALUATION_ONLY"
    elif now and expiry and now >= expiry:
        freshness = "EXPIRED"
    entry, stop, target = (opp.get(k) for k in ("entry_reference", "stop_c10", "target_c11"))
    sign = {"LONG": 1, "SHORT": -1}.get(opp.get("direction"))
    valid = (sign and all(_number(x) for x in (entry, stop, target))
             and not opp.get("stop_reason") and not opp.get("target_reason")
             and sign * (entry - stop) > 0 and sign * (target - entry) > 0)
    rr = f"{abs((target - entry) / (entry - stop)):.3f}" if valid else NA
    reasons = payload.get("reason_codes") or []
    rejection = ",".join(str(x) for x in reasons) if event.get("to_state") == "REJECTED" and reasons else NA
    candidate = lambda x: f"{x:g}" if _number(x) else NA
    return [
        "M5 DIAGNOSTICS -- READ ONLY -- NO EXECUTION AUTHORITY",
        f"liquidity sweep time: {opp.get('sweep_time') if _time(opp.get('sweep_time')) else NA}",
        f"CHoCH time: {opp.get('choch_time') if signal else NA}; BOS: {NA}",
        f"displacement evidence: {NA}",
        f"entry candidate: {candidate(entry)}; stop candidate: {candidate(stop)}; target candidate: {candidate(target)}",
        f"gross R:R candidate: {rr}; net R:R: {NA}",
        f"spread: {NA}; total cost: {NA}",
        f"freshness: {freshness}; expires_at: {expiry.isoformat() if expiry else NA}",
        f"explicit rejection reason: {rejection}",
    ]
