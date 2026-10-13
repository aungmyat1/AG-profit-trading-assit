"""Fail-closed directional target geometry (AGP-TQ-D1).

The frozen ST_ASIAN_SWEEP_5R_V1@1.1.2 contract declares `target_order_rule: FAIL_CLOSED_IF_TP1_BEYOND_TP2`
(changelog B-TGT-ORDER: "TP1 may pass TP2: unsafe -> FAIL_CLOSED on inversion"). This module states that
rule, plus the directional ordering it presupposes, once, so the canonical READY boundary
(v1_tickets.actionability) and the execution handoff (demo_execution.admission) apply the same check:

    LONG:  SL < ENTRY < TP1 <= TP2        SHORT: SL > ENTRY > TP1 >= TP2

Missing, malformed or non-finite levels, a non-positive risk distance, or an inverted target is a
violation. TP1 == TP2 is allowed (the rule forbids TP1 *beyond* TP2). Prices are never swapped or
relabelled. Pure: no I/O, no strategy-engine import.
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Optional

TARGET_ORDER_RULE = "FAIL_CLOSED_IF_TP1_BEYOND_TP2"
INCOMPLETE = "TARGET_GEOMETRY_INCOMPLETE"
DIRECTION_INVALID = "TARGET_GEOMETRY_DIRECTION_INVALID"
NON_POSITIVE_RISK = "NON_POSITIVE_RISK_DISTANCE"
TP1_SIDE_INVALID = "TP1_NOT_BEYOND_ENTRY"
TARGET_ORDER_INVALID = f"TARGET_ORDER_INVALID:{TARGET_ORDER_RULE}"


def _num(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def geometry_violation(entry: Any, sl: Any, tp1: Any, tp2: Any, direction: Any) -> Optional[str]:
    """None when the levels satisfy the ordering; otherwise the first violation reason."""
    levels = [_num(v) for v in (entry, sl, tp1, tp2)]
    if any(v is None for v in levels):
        return INCOMPLETE
    if direction not in ("LONG", "SHORT"):
        return DIRECTION_INVALID
    entry_f, sl_f, tp1_f, tp2_f = levels
    sign = 1.0 if direction == "LONG" else -1.0
    if sign * (entry_f - sl_f) <= 0:
        return NON_POSITIVE_RISK
    if sign * (tp1_f - entry_f) <= 0:
        return TP1_SIDE_INVALID
    if sign * (tp2_f - tp1_f) < 0:
        return TARGET_ORDER_INVALID
    return None


def ticket_levels(ticket: Mapping[str, Any]) -> dict:
    """Entry / stop / TP1 / TP2 / direction from a raw V1 ticket (tp1/tp2 keys or targets legs 1/2)."""
    tp1, tp2 = ticket.get("tp1"), ticket.get("tp2")
    for leg in ticket.get("targets") or []:
        if isinstance(leg, Mapping):
            if leg.get("leg") == 1 and tp1 is None:
                tp1 = leg.get("price")
            if leg.get("leg") == 2 and tp2 is None:
                tp2 = leg.get("price")
    return {"entry": ticket.get("entry"), "sl": ticket.get("stop_loss", ticket.get("sl")), "tp1": tp1, "tp2": tp2,
            "direction": ticket.get("direction")}


def ticket_geometry_violation(ticket: Mapping[str, Any]) -> Optional[str]:
    lv = ticket_levels(ticket)
    return geometry_violation(lv["entry"], lv["sl"], lv["tp1"], lv["tp2"], lv["direction"])
