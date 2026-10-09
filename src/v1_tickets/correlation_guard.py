"""Correlated-READY warning (post-signal actionability layer, WARN-ONLY).

Owner decision (PR #48 disposition, 2026-10-08): the actionability layer stays separate
from strategy logic, and correlated READYs are warned, never suppressed. This module runs
after the strategy engines and after v1_tickets.actionability; it never changes a decision,
a price or a strategy rule, and never calls a broker.

Correlation rule (conservative implementation choice, no owner-stated threshold exists, so
no return-correlation number is used): two READY signals are correlated when they carry
same-sign exposure to a common currency/asset leg. LONG = +base / -quote, SHORT = -base /
+quote. Example: LONG EURUSD and LONG GBPUSD are both short USD -> warned. USDT is treated
as USD (both are USD-quoted legs).
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

CORRELATED_READY = "CORRELATED_READY"
READY_DECISIONS = frozenset({"READY", "WATCH_READY", "OPPORTUNITY"})
_LEG_ALIAS = {"USDT": "USD"}


def legs(symbol: str) -> Optional[Tuple[str, str]]:
    """(base, quote) for a 6-character FX/metal/crypto CFD symbol or a *USDT pair; else None."""
    s = symbol.upper().split("-")[0]
    if s.endswith("USDT"):
        base, quote = s[:-4], "USDT"
    elif len(s) == 6:
        base, quote = s[:3], s[3:]
    else:
        return None
    return _LEG_ALIAS.get(base, base), _LEG_ALIAS.get(quote, quote)


def _exposure(symbol: str, direction: str) -> Dict[str, int]:
    pair = legs(symbol)
    if pair is None or direction not in ("LONG", "SHORT"):
        return {}
    sign = 1 if direction == "LONG" else -1
    return {pair[0]: sign, pair[1]: -sign}


def correlated_ready_warnings(signals: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Warnings for READY signals that share same-sign exposure to a leg. Input items need
    `symbol`, `direction`, `decision`; `strategy_id` is passed through. Inputs are not mutated
    and nothing is filtered: the caller attaches the warnings, every READY stays READY."""
    ready = [s for s in signals if s.get("decision") in READY_DECISIONS]
    groups: Dict[Tuple[str, int], List[Dict[str, Any]]] = {}
    for s in ready:
        for leg, sign in _exposure(str(s.get("symbol", "")), str(s.get("direction", ""))).items():
            groups.setdefault((leg, sign), []).append(s)
    out = []
    for (leg, sign), members in sorted(groups.items()):
        if len({m.get("symbol") for m in members}) < 2:
            continue
        out.append({
            "code": CORRELATED_READY, "severity": "WARN", "blocking": False, "leg": leg,
            "exposure": "LONG" if sign > 0 else "SHORT",
            "members": [{"strategy_id": m.get("strategy_id"), "symbol": m.get("symbol"),
                         "direction": m.get("direction")} for m in members],
        })
    return out
