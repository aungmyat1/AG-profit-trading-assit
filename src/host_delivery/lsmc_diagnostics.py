"""Read-only diagnostics from archived facts. Never strategy or order authority."""
from __future__ import annotations

import datetime as dt
import math
import re
from collections.abc import Mapping

NA = "NOT_AVAILABLE"
MAX_ALERT_UNITS = 4000  # existing telegram_message.send_message transport budget
_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")


def _mapping(value):
    return value if isinstance(value, Mapping) else {}


def _number(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        return False
    try:
        return math.isfinite(value)
    except OverflowError:  # an unbounded JSON integer is not a usable price
        return False


def _time(value):
    if not isinstance(value, (str, dt.datetime)):
        return None
    try:
        parsed = value if isinstance(value, dt.datetime) else dt.datetime.fromisoformat(value)
        return parsed.astimezone(dt.timezone.utc) if parsed.utcoffset() is not None else None
    except (ValueError, OverflowError):
        return None


def _text(value):
    """Bound display evidence without truncating or accepting line injection."""
    return value if (isinstance(value, str) and 0 < len(value) <= 256
                     and value.isascii() and all(32 <= ord(c) <= 126 for c in value)) else NA


def _reasons(value):
    if (not isinstance(value, (list, tuple)) or not 0 < len(value) <= 8
            or not all(isinstance(code, str) and _CODE.fullmatch(code) for code in value)):
        return []
    return list(value)


def report_event(event):
    """Sanitized display copy only; never feed this projection to strategy/delivery identity."""
    event = _mapping(event)
    payload = dict(_mapping(event.get("payload")))
    opp = dict(_mapping(payload.get("opportunity")))
    poi = dict(_mapping(payload.get("poi")))
    for key in ("entry_reference", "stop_c10", "target_c11", "sweep_extreme", "choch_level"):
        opp[key] = opp.get(key) if _number(opp.get(key)) else None
    for key in ("low", "high"):
        poi[key] = poi.get(key) if _number(poi.get(key)) else None
    if poi["low"] is not None and poi["high"] is not None and poi["low"] > poi["high"]:
        poi["low"] = poi["high"] = None
    for key in ("stop_reason", "target_reason"):
        opp[key] = _text(opp[key]) if opp.get(key) is not None else None
    for key in ("sweep_time", "choch_time", "expires_at"):
        value = _time(opp.get(key))
        opp[key] = value.isoformat() if value else None
    for obj in (opp, poi):
        obj["direction"] = obj.get("direction") if obj.get("direction") in ("LONG", "SHORT") else None
    poi["kind"] = _text(poi.get("kind"))
    payload.update(poi=poi, opportunity=opp, reason_codes=_reasons(payload.get("reason_codes")),
                   bias=payload.get("bias") if payload.get("bias") in ("LONG", "SHORT") else None)
    expiry = _time(payload.get("expires_at"))
    payload["expires_at"] = expiry.isoformat() if expiry else None
    result = dict(event)
    for key in ("symbol", "strategy_id", "strategy_version", "reference_id", "to_state", "alert_level"):
        result[key] = _text(event.get(key))
    broker = event.get("display_broker_symbol")
    result["display_broker_symbol"] = _text(broker) if broker is not None else None
    result["payload"] = payload
    return result


def diagnostic_lines(event):
    """No quote, cost, partial-stage or expiry inference from a completed badge."""
    event = report_event(event)
    payload = event["payload"]
    opp = payload["opportunity"]
    now, expiry = _time(event.get("evaluated_at")), _time(opp.get("expires_at"))
    signal, sweep = _time(opp.get("choch_time")), _time(opp.get("sweep_time"))
    freshness = NA
    # Invalid signal chronology never becomes a freshness claim, including EXPIRED.
    if (now and expiry and signal and signal <= now and signal < expiry
            and (sweep is None or sweep <= signal)):
        freshness = "AT_EVALUATION_ONLY" if now < expiry else "EXPIRED"
    entry, stop, target = (opp.get(k) for k in ("entry_reference", "stop_c10", "target_c11"))
    direction = opp.get("direction")
    valid = (all(_number(x) for x in (entry, stop, target))
             and not opp.get("stop_reason") and not opp.get("target_reason")
             and ((stop < entry < target) if direction == "LONG" else
                  (target < entry < stop) if direction == "SHORT" else False))
    ratio = abs(target - entry) / abs(entry - stop) if valid else None
    rr = f"{ratio:.3f}" if _number(ratio) else NA
    rejection = ",".join(payload["reason_codes"]) if event.get("to_state") == "REJECTED" else ""

    def candidate(value):
        return f"{value:g}" if _number(value) else NA

    return [
        "M5 DIAGNOSTICS -- READ ONLY -- NO EXECUTION AUTHORITY",
        f"liquidity sweep time: {sweep.isoformat() if sweep else NA}",
        f"CHoCH time: {signal.isoformat() if signal else NA}; BOS: {NA}",
        f"displacement evidence: {NA}",
        f"entry candidate: {candidate(entry)}; stop candidate: {candidate(stop)}; target candidate: {candidate(target)}",
        f"gross R:R candidate: {rr}; net R:R: {NA}",
        f"spread: {NA}; total cost: {NA}",
        f"freshness: {freshness}; expires_at: {expiry.isoformat() if expiry else NA}",
        f"explicit rejection reason: {rejection or NA}",
    ]


def alert_units(text):
    """Telegram counts UTF-16 units; the existing transport reserves 96 of 4096."""
    return len(text.encode("utf-16-le")) // 2
