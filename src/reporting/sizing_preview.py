"""Display-only lot preview and cost-in-R for a REPORT_ONLY CANDIDATE (OD1014 A3).

Never an order size: the preview is computed by the single sizing authority (sizing_math.risk.size_position)
at the owner ticket risk_pct (config/owner_ticket.yaml via manual_ticket.load_owner_config -- no fallback),
only from evidenced inputs the lane attached as `sizing_inputs` (broker symbol metadata, pip evidence,
read-only bid/ask, commission_R, balance). Any missing or invalid input omits the value with a reason;
zero, NaN and estimates are never shown.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional

_META_FIELDS = ("tick_size", "tick_value", "contract_size", "volume_min", "volume_max", "volume_step")


def _pos(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        return None
    return float(value)


def _risk_pct(owner: Optional[Dict[str, Any]]) -> Optional[float]:
    if owner is None:
        try:
            from v1_tickets.manual_ticket import load_owner_config
            owner = load_owner_config()
        except Exception:  # noqa: BLE001 -- unreadable config: no preview, never a fallback
            return None
    return _pos(owner.get("risk_pct")) if owner.get("risk_status", "SET") == "SET" else None


def sizing_preview(c: Dict[str, Any], owner: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """{'risk_pct', 'lot', 'cost_in_R', 'lot_reason', 'cost_reason'}; a value is None whenever its reason is set."""
    out: Dict[str, Any] = {"risk_pct": None, "lot": None, "cost_in_R": None, "lot_reason": None, "cost_reason": None}

    def fail(reason: str, *, cost: bool = True) -> Dict[str, Any]:
        out["lot_reason"] = out["lot_reason"] or reason
        if cost:
            out["cost_reason"] = out["cost_reason"] or reason
        return out

    inputs = c.get("sizing_inputs")
    if not isinstance(inputs, dict):
        return fail("SIZING_INPUTS_MISSING")
    prices = c.get("prices") or {}
    entry, sl = _pos(prices.get("entry_reference_raw")), _pos(prices.get("sl_raw"))
    if entry is None or sl is None or entry == sl:
        return fail("PLAN_INCOMPLETE")
    risk = abs(entry - sl)
    meta = inputs.get("symbol_meta")
    if (not isinstance(meta, dict) or any(_pos(meta.get(k)) is None for k in _META_FIELDS if k != "tick_value")
            or meta.get("metadata_source", "EXCHANGE_VERIFIED") != "EXCHANGE_VERIFIED"):
        return fail("SYMBOL_METADATA_MISSING")
    if _pos(inputs.get("pip_size")) is None:
        return fail("PIP_EVIDENCE_MISSING")
    bid, ask = _pos(inputs.get("bid")), _pos(inputs.get("ask"))
    if bid is None or ask is None:
        return fail("QUOTE_MISSING")
    spread = ask - bid
    if not math.isfinite(spread) or spread <= 0:
        return fail("SPREAD_INVALID")
    if _pos(meta.get("tick_value")) is None:
        return fail("CONVERSION_UNAVAILABLE")
    commission_r = inputs.get("commission_R")
    if (isinstance(commission_r, bool) or not isinstance(commission_r, (int, float))
            or not math.isfinite(commission_r) or commission_r < 0):
        out["cost_reason"] = "COMMISSION_UNKNOWN"
    else:
        cost = spread / risk + commission_r
        if math.isfinite(cost) and cost > 0:
            out["cost_in_R"] = cost
        else:
            out["cost_reason"] = "COST_INVALID"
    risk_pct = _risk_pct(owner)
    if risk_pct is None:
        return fail("RISK_CONFIG_MISSING", cost=False)
    out["risk_pct"] = risk_pct
    balance = _pos(inputs.get("balance"))
    if balance is None:
        return fail("BALANCE_UNAVAILABLE", cost=False)
    from types import SimpleNamespace

    from sizing_math.risk import size_position
    symbol_meta = SimpleNamespace(symbol=str(c.get("instrument") or ""), tick_size=float(meta["tick_size"]),
                             tick_value=float(meta["tick_value"]), contract_size=float(meta["contract_size"]),
                             volume_min=float(meta["volume_min"]), volume_max=float(meta["volume_max"]),
                             volume_step=float(meta["volume_step"]), digits=int(meta.get("digits") or 0))
    volume, _, reason = size_position(entry, sl, balance, risk_pct, symbol_meta)
    if reason is not None or _pos(volume) is None:
        return fail(reason or "VOLUME_INVALID", cost=False)
    out["lot"] = volume
    return out


def sizing_lines(c: Dict[str, Any], owner: Optional[Dict[str, Any]] = None) -> list:
    p = sizing_preview(c, owner)
    lines = []
    if p["lot"] is not None:
        lines.append(f"lot preview @ {p['risk_pct']:g}% risk: {p['lot']:g} (display only, not an order)")
    else:
        lines.append(f"sizing: n/a ({p['lot_reason']})")
    if p["cost_in_R"] is not None:
        lines.append(f"cost: {p['cost_in_R']:.2f}R (spread+commission)")
    elif p["cost_reason"] != p["lot_reason"]:
        lines.append(f"cost: n/a ({p['cost_reason']})")
    return lines
