"""Canonical owner-facing ticket model (Phase E) and ASCII market-structure visual (Phase G).

Combines a V1 FX / crypto ticket (v1_tickets.fx / v1_tickets.crypto) with its actionability
result into a single deterministic owner-facing payload.  Execution authority is stamped
False on every ticket.  Logic / economic status come from the registry authority and are
never invented.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from typing import Any, Dict, List, Optional, Sequence

from ticket_delivery.identity import logical_ticket_id
from v1_tickets.actionability import (
    BLOCKED, EXPIRED, INSUFFICIENT_DATA, INFO_ONLY_INSUFFICIENT_REMAINING_R, INFO_ONLY_STALE, INFO_ONLY_SUPPRESSED,
    MISSED, NO_TRADE, OUT_OF_SESSION, WATCH_READY, evaluate_actionability,
)
from v1_tickets.authority import resolve_ticket_authority

CANONICAL_VERSION = "AG_CANONICAL_TICKET_V1"

# Mapping from actionability decision to ticket presentation type.
PRESENTATION_WATCH = "WATCH_READY"
PRESENTATION_INFO = "INFO_ONLY"
PRESENTATION_OTHER = "OTHER"

_INFO_REASONS = {
    INFO_ONLY_STALE: "INFO_ONLY_STALE",
    INFO_ONLY_SUPPRESSED: "INFO_ONLY_SUPPRESSED",
    INFO_ONLY_INSUFFICIENT_REMAINING_R: "INFO_ONLY_INSUFFICIENT_REMAINING_R",
    MISSED: "MISSED",
    EXPIRED: "EXPIRED",
}


def presentation_type(decision: str, reason: str) -> str:
    if decision == WATCH_READY:
        return PRESENTATION_WATCH
    if decision in _INFO_REASONS or decision == NO_TRADE:
        return PRESENTATION_INFO
    return PRESENTATION_OTHER


def _strategy_meta(ticket: Dict[str, Any]) -> Dict[str, str]:
    try:
        auth = resolve_ticket_authority(ticket["strategy_id"], ticket.get("strategy_version"))
        return {
            "logic_status": auth.logic_status_effective,
            "economic_status": auth.economic_status or "NOT_EVALUATED",
            "ticket_authority": auth.ticket_authority or "NONE",
        }
    except Exception:  # noqa: BLE001 -- fail closed: never invent status
        return {"logic_status": "NOT_VERIFIED", "economic_status": "NOT_EVALUATED",
                "ticket_authority": "NONE"}


def _venue(ticket: Dict[str, Any]) -> str:
    if ticket.get("profile") == "CRYPTO_PERP":
        return ticket.get("data_source") or "CRYPTO_PERP"
    if ticket.get("ticket_config"):
        return "MT5_VT_MARKETS_DEMO"  # crypto CFD v2/v3 path
    return "MT5_VT_MARKETS_DEMO"


NOT_AVAILABLE = "NOT_AVAILABLE"


def _context_labels(ticket: Dict[str, Any]) -> Dict[str, str]:
    """Market-context fields are PASS-THROUGH ONLY from the source ticket (Phase B).

    If a source did not supply a fact, we emit NOT_AVAILABLE rather than inventing a
    plausible interpretation (no \"H1 discount\"/\"H1 premium\", no synthetic POI).
    Source-supplied facts are copied verbatim.
    """
    src = ticket.get("context") if isinstance(ticket.get("context"), dict) else {}
    d1 = src.get("d1_context")
    h1 = src.get("h1_context")
    structure = src.get("structure")
    poi = src.get("poi")
    # Legacy: a manual_ticket may carry `regime` from the engine; that is SOURCE_FACT.
    if d1 is None and ticket.get("regime"):
        d1 = str(ticket.get("regime"))
    if structure is None and ticket.get("setup"):
        structure = str(ticket.get("setup"))
    return {
        "d1_context": d1 if d1 is not None else NOT_AVAILABLE,
        "h1_context": h1 if h1 is not None else NOT_AVAILABLE,
        "structure": structure if structure is not None else NOT_AVAILABLE,
        "poi": poi if poi is not None else NOT_AVAILABLE,
    }


def _fact_provenance(ticket: Dict[str, Any], ctx: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
    """Lightweight provenance record for market-context facts (Phase C).

    Status values: SOURCE_FACT, RUNTIME_FACT, POLICY_FACT, NOT_AVAILABLE.
    Formatting does not require separate provenance.  No INFERRED category.
    """
    src = ticket.get("context") if isinstance(ticket.get("context"), dict) else {}

    def _status_for(key: str, fallback_key: Optional[str] = None) -> Dict[str, Any]:
        if src.get(key) is not None:
            return {"status": "SOURCE_FACT", "source": "ticket.context"}
        if fallback_key is not None and ticket.get(fallback_key) is not None:
            return {"status": "RUNTIME_FACT", "source": f"ticket.{fallback_key}"}
        return {"status": "NOT_AVAILABLE", "source": None}

    return {
        "d1_context": _status_for("d1_context", "regime"),
        "h1_context": _status_for("h1_context"),
        "structure": _status_for("structure", "setup"),
        "poi": _status_for("poi"),
    }


def _fmt(value: Optional[float], symbol: Optional[str]) -> str:
    if value is None:
        return "—"
    digits = _price_digits(symbol)
    return f"{value:.{digits}f}"


def _freshness_line(f: Dict[str, Any]) -> str:
    status = "PASS" if f.get("status") == "PASS" else "FAIL"
    age = f.get("age_s") if f.get("age_s") is not None else 0
    limit = f.get("limit_s") if f.get("limit_s") is not None else 0
    return f"{status} ({age:.0f}s / limit {limit}s)"


def _price_digits(symbol: Optional[str]) -> int:
    if symbol in ("EURUSD", "GBPUSD"):
        return 5
    if symbol == "USDJPY":
        return 3
    if symbol in ("XAUUSD", "BTCUSD", "ETHUSD", "BTCUSDT", "ETHUSDT"):
        return 2
    return 5


def build_canonical_ticket(
    ticket: Dict[str, Any],
    *,
    now: dt.datetime,
    current_price: Optional[float] = None,
    window_end: Optional[dt.datetime] = None,
    proposal_eligibility: str = "INFORMATIONAL_WATCH",
    policy=None,
    policy_root: str = ".",
    policy_override_path: Optional[str] = None,
    policy_override_dict: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a deterministic canonical ticket dict combining strategy output + actionability.

    `ticket` is the raw V1 FX/crypto ticket (from v1_tickets.fx.build_fx_ticket or
    v1_tickets.crypto.build_crypto_ticket) or a manual_ticket dict.  This function never
    calls strategy engines, brokers or network.  Policy is injected via `policy` (a
    preloaded ActionabilityPolicy) or loaded from `policy_root` / override paths for DI.
    """
    action = evaluate_actionability(ticket, now=now, current_price=current_price, window_end=window_end,
                                    policy=policy, policy_root=policy_root,
                                    policy_override_path=policy_override_path,
                                    policy_override_dict=policy_override_dict)
    meta = _strategy_meta(ticket)
    ctx = _context_labels(ticket)
    provenance = _fact_provenance(ticket, ctx)
    sym = ticket.get("symbol")
    entry = action.get("entry_reference_price")
    sl = _safe_get(ticket, ("stop_loss", "sl"))
    tp1 = _first_present(ticket, ("tp1",), ("targets", 0, "price"))
    tp2 = _first_present(ticket, ("tp2",), ("targets", 1, "price"))
    direction = ticket.get("direction")
    cycle = ticket.get("cycle") or ticket.get("window") or "DAILY"
    session_date = ticket.get("session_date") or ticket.get("observation_date") or now.date().isoformat()
    trigger_ts = ticket.get("signal_timestamp") or action.get("trigger_bar_close_utc")

    # Expires at: trigger close + freshness window, OR trade window end, whichever is earlier.
    expires = None
    limit_s = action.get("freshness_limit_s")
    trigger_close = action.get("trigger_bar_close_utc")
    if trigger_close and limit_s:
        try:
            tc = dt.datetime.fromisoformat(trigger_close)
            expires = (tc + dt.timedelta(seconds=limit_s)).isoformat()
        except (TypeError, ValueError):
            expires = None
    if action["actionability_decision"] in (EXPIRED,):
        expires = action["evaluated_at"]

    if isinstance(session_date, str):
        try:
            td_date = dt.date.fromisoformat(session_date[:10])
        except ValueError:
            td_date = now.date()
    elif isinstance(session_date, dt.date):
        td_date = session_date
    else:
        td_date = now.date()
    ticket_id = logical_ticket_id(
        strategy_id=ticket.get("strategy_id", "UNKNOWN"),
        strategy_version=str(ticket.get("strategy_version", "?")),
        symbol=sym or "UNKNOWN",
        cycle=cycle,
        trading_date=td_date,
    )
    setup_status = action["actionability_decision"]
    canonical: Dict[str, Any] = {
        "schema": CANONICAL_VERSION,
        "label": "INFORMATIONAL TICKET — NOT A BROKER ORDER",
        "ticket_id": ticket_id,
        "proposal_id": ticket_id,
        "presentation": presentation_type(action["actionability_decision"], action["actionability_reason"]),
        "decision": action["actionability_decision"],
        "reason_code": action["actionability_reason"],
        "instrument": sym,
        "venue": _venue(ticket),
        "session": cycle,
        "session_date": session_date,
        "strategy_id": ticket.get("strategy_id"),
        "strategy_version": ticket.get("strategy_version"),
        "logic_status": meta["logic_status"],
        "economic_status": meta["economic_status"],
        "economic_edge": "NOT VERIFIED",
        "direction": direction,
        "context": ctx,
        "poi": ctx["poi"],
        "fact_provenance": provenance,
        "trigger": {
            "setup": ticket.get("setup"),
            "trigger_timestamp": trigger_ts,
            "trigger_bar_close_utc": action.get("trigger_bar_close_utc"),
        },
        "prices": {
            "entry_reference": _fmt(entry, sym),
            "current_send": _fmt(current_price, sym),
            "sl": _fmt(sl, sym),
            "tp1": _fmt(tp1, sym),
            "tp2": _fmt(tp2, sym),
            "entry_reference_raw": entry,
            "current_send_raw": current_price,
            "sl_raw": sl,
            "tp1_raw": tp1,
            "tp2_raw": tp2,
        },
        "risk": {
            "risk_distance": action.get("risk_distance"),
            "initial_R_tp1": action.get("initial_rr_tp1"),
            "initial_R_tp2": action.get("initial_rr_tp2"),
            "remaining_R_tp1": action.get("remaining_r_tp1"),
            "remaining_R_tp2": action.get("remaining_r_tp2"),
        },
        "freshness": {
            "status": action.get("freshness_status"),
            "age_s": action.get("freshness_age_s"),
            "limit_s": action.get("freshness_limit_s"),
            "policy": action.get("policy_version"),
        },
        "actionability": {
            "version": action.get("actionability_version"),
            "decision": action["actionability_decision"],
            "reason": action["actionability_reason"],
            "valid_at_trigger": action.get("valid_at_trigger"),
            "actionability_at_send": action.get("actionability_at_send"),
            "policy_id": action.get("actionability_policy_id"),
            "policy_version": action.get("actionability_policy_version"),
            "policy_status": action.get("policy_status"),
            "policy_reason": action.get("policy_reason"),
            "min_remaining_r": action.get("min_remaining_r"),
            "policy_source_identity": action.get("policy_source_identity"),
        },
        "setup_status": setup_status,
        "proposal_eligibility": proposal_eligibility,
        "execution_authorization": False,
        "demo_authorized": False,
        "live_authorized": False,
        "reason_codes": _collect_reason_codes(ticket, action),
        "created_at": action.get("evaluated_at"),
        "trigger_at": trigger_ts,
        "expires_at": expires,
        "send_timestamp": action.get("send_timestamp_utc"),
    }
    if isinstance(ticket.get("data_error"), dict):
        canonical["data_error"] = {
            "code": str(ticket["data_error"].get("code", "OTHER"))[:80],
            "detail": str(ticket["data_error"].get("detail", ""))[:300],
            "layer": str(ticket["data_error"].get("layer", "OTHER"))[:80],
        }
    canonical["structure_visual"] = render_structure_visual(canonical)
    canonical["checklist"] = _checklist_summary(ticket, canonical)
    return canonical


def _safe_get(d: Dict[str, Any], keys: Sequence[str]) -> Any:
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] is not None:
            return d[k]
    return None


def _first_present(d: Dict[str, Any], *paths) -> Any:
    for path in paths:
        cur: Any = d
        ok = True
        for p in path:
            if isinstance(cur, list) and isinstance(p, int):
                if 0 <= p < len(cur):
                    cur = cur[p]
                else:
                    ok = False
                    break
            elif isinstance(cur, dict):
                cur = cur.get(p)
                if cur is None:
                    ok = False
                    break
            else:
                ok = False
                break
        if ok and cur is not None:
            return cur
    return None


def _collect_reason_codes(ticket: Dict[str, Any], action: Dict[str, Any]) -> List[str]:
    codes: List[str] = []
    rc = ticket.get("reason_code")
    if isinstance(rc, str) and rc:
        codes.append(rc)
    rcl = ticket.get("reason_codes")
    if isinstance(rcl, (list, tuple)):
        codes.extend(str(c) for c in rcl if c)
    if action.get("actionability_reason"):
        codes.append(action["actionability_reason"])
    # Deduplicate preserving order.
    seen = set()
    out = []
    for c in codes:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


# ----------------------------------------------------------------- checklist (Phase H)

_CHECKLIST_PHASES = (
    ("CONTEXT", "D1/H1 structure alignment with direction (advisory)"),
    ("LOCATION", "POI zone identified"),
    ("TRIGGER", "Frozen-strategy trigger fired (sweep of reference boundary)"),
    ("RISK", "Stop geometry + spread check"),
    ("EXECUTION/COST", "Execution cost in R; advisory only — no order sent"),
    ("POST-TRADE/AUDIT", "Archived decision record + identity"),
)


def _checklist_summary(ticket: Dict[str, Any], canonical: Dict[str, Any]) -> List[Dict[str, Any]]:
    decision = canonical["decision"]
    has_signal = ticket.get("direction") is not None
    out: List[Dict[str, Any]] = []
    status_map: Dict[str, str] = {}
    # 1 CONTEXT: strategy regime provides this (supporting unless frozen strategy declared it required).
    status_map["CONTEXT"] = ("strategy-required" if ticket.get("regime") else "missing") \
        if has_signal else "supporting-information"
    # 2 LOCATION: POI/box exists.
    box = ticket.get("box") or {}
    status_map["LOCATION"] = "strategy-required" if (box.get("high") is not None and box.get("low") is not None) \
        and has_signal else ("supporting-information" if not has_signal else "missing")
    # 3 TRIGGER: strategy engine said SIGNAL.
    status_map["TRIGGER"] = "strategy-required" if ticket.get("decision") == "READY" or \
        ticket.get("suppressed_decision") == "READY" else ("not-applicable" if not has_signal else "missing")
    # 4 RISK: stop geometry present + spread gate.
    sp = ticket.get("spread_check")
    has_risk = canonical["prices"]["sl_raw"] is not None and canonical["risk"]["risk_distance"]
    status_map["RISK"] = "strategy-required" if has_risk and sp == "PASS" else (
        "missing" if has_signal else "not-applicable")
    # 5 EXECUTION/COST: always supporting/NA — no execution in this pipeline.
    status_map["EXECUTION/COST"] = "supporting-information"
    # 6 AUDIT: always strategy-required (archive exists before send).
    status_map["POST-TRADE/AUDIT"] = "strategy-required"
    for phase, desc in _CHECKLIST_PHASES:
        out.append({"phase": phase, "description": desc, "status": status_map.get(phase, "not-applicable")})
    return out


# ----------------------------------------------------------------- structure visual (Phase G)

def render_structure_visual(canonical: Dict[str, Any], *, width: int = 32) -> str:
    """ASCII structure diagram. No candlesticks. Lines for TP2 / TP1 / NOW / ENTRY / POI / SL,
    with an estimated direction arrow drawn with `·` that is explicitly labelled.
    Returns an empty string when there is no directional setup (NO_TRADE / INSUFFICIENT_DATA etc.).
    """
    p = canonical.get("prices") or {}
    direction = canonical.get("direction")
    decision = canonical.get("decision")
    entry, sl, tp1, tp2 = (p.get("entry_reference_raw"), p.get("sl_raw"),
                           p.get("tp1_raw"), p.get("tp2_raw"))
    current = p.get("current_send_raw")
    sym = canonical.get("instrument")
    if direction not in ("LONG", "SHORT") or entry is None or sl is None or tp1 is None:
        return "(no structure — no directional signal)"
    # If source did not supply a POI, the diagram POI band is a structural estimate only
    # (between SL and entry by the visual heuristic) and is so labelled.
    poi_supplied = (canonical.get("context") or {}).get("poi") not in (None, NOT_AVAILABLE)
    levels: List[tuple] = []
    if tp2 is not None:
        levels.append(("TP2", tp2))
    levels.append(("TP1", tp1))
    levels.append(("NOW", current if current is not None else entry))
    levels.append(("ENTRY", entry))
    # POI band: place one line just above/below SL representing the swept liquidity zone.
    poi_low, poi_high = _poi_band(entry, sl, direction)
    levels.append(("POI_LO", poi_low))
    levels.append(("POI_HI", poi_high))
    levels.append(("SL", sl))

    # Sort ascending (top = high price for LONG; but we print TP2 at top for both directions).
    levels_sorted = sorted(levels, key=lambda x: x[1], reverse=True)
    labels = {name for name, _ in levels_sorted}
    lines: List[str] = []
    n = width
    # Build a visual column. Labels are left-aligned; the horizontal line spans columns.
    for name, val in levels_sorted:
        if name == "POI_LO":
            continue
        if name == "POI_HI":
            # POI band uses `=` instead of `-`, spans both POI_LO and POI_HI.
            lines.append(f"POI  {'═' * n}  {_fmt(poi_high, sym)}–{_fmt(poi_low, sym)}")
            continue
        prefix = f"{name:<5}"
        if name == "NOW":
            marker = "←"
        elif name == "ENTRY":
            marker = ""
        else:
            marker = ""
        lines.append(f"{prefix} {'─' * n}  {_fmt(val, sym)}{('  ' + marker) if marker else ''}")

    # Direction estimate: place arrow/dots between TP1 and TP2 to indicate expected direction.
    if direction == "LONG":
        note = "                ·\n                · estimated path (upwards)\n                ↑"
        insert_at = _find_insert(levels_sorted, "TP1")
    else:
        note = "                ↑\n                · estimated path (downwards)\n                ·"
        insert_at = _find_insert(levels_sorted, "NOW") if "NOW" in labels else 0
    # Insert note at a sensible spot.
    lines.insert(min(insert_at + 1, len(lines)), note)
    footer_parts = ["(dotted line is a structural estimate, not a forecast)"]
    if not poi_supplied:
        footer_parts.append("(POI zone not supplied by source; band shown is a structural estimate)")
    return "\n".join(lines) + "\n" + "\n".join(footer_parts)


def _find_insert(levels_sorted: List[tuple], name: str) -> int:
    for i, (n, _) in enumerate(levels_sorted):
        if n == name:
            return i
    return 0


def _poi_band(entry: float, sl: float, direction: str) -> tuple:
    """POI is a small zone between SL and entry representing the swept liquidity/support."""
    span = abs(entry - sl)
    margin = span * 0.15 if span > 0 else 0
    if direction == "LONG":
        # SL is below entry; POI sits around and just above SL.
        return sl + margin * 0.2, sl + margin
    else:
        # SL is above entry.
        return sl - margin, sl - margin * 0.2


# ----------------------------------------------------------------- render WATCH_READY / INFO_ONLY text

def render_watch_ready(canonical: Dict[str, Any]) -> str:
    """Compact WATCH_READY ticket in the owner-specified layout."""
    p = canonical["prices"]
    r = canonical["risk"]
    f = canonical["freshness"]
    inst = canonical["instrument"]
    direction = canonical["direction"] or "—"
    session = canonical["session"]
    ctx = canonical["context"]
    lines = [
        f"{inst} — {direction} — WATCH_READY",
        session.replace("_", "→"),
        "",
        "Context",
        f"D1 {ctx['d1_context']} | H1 {ctx['h1_context']}",
        "",
        "Structure",
        ctx["structure"],
        "",
        "POI",
        canonical["poi"],
        "",
        "Entry reference",
        str(p["entry_reference"]),
        "",
        "Current",
        str(p["current_send"]),
        "",
        "SL",
        str(p["sl"]),
        "",
        "TP1",
        str(p["tp1"]),
        "",
        "TP2",
        str(p["tp2"]),
        "",
        "Initial R",
        (f"1:{r['initial_R_tp1']:.1f}" if r.get("initial_R_tp1") is not None else "—"),
        "",
        "Remaining R",
        (f"{r['remaining_R_tp1']:.1f}R" if r.get("remaining_R_tp1") is not None else "—"),
        "",
        "Freshness",
        _freshness_line(f),
        "",
        "Economic edge",
        canonical["economic_edge"],
        "",
        "Execution",
        "NOT AUTHORIZED",
        "",
        f"Ticket {canonical['ticket_id']}",
        f"Strategy {canonical['strategy_id']}@{canonical['strategy_version']}  "
        f"logic={canonical['logic_status']}  economic={canonical['economic_status']}",
    ]
    return "\n".join(lines)


def render_info_only(canonical: Dict[str, Any]) -> str:
    """INFO_ONLY ticket, clearly labelled with why it is not actionable."""
    reason = canonical["reason_code"]
    p = canonical["prices"]
    r = canonical["risk"]
    lines = [
        f"{canonical['instrument']} — {canonical['direction'] or '—'} — {reason}",
        canonical["session"].replace("_", "→"),
        "",
        f"Signal was valid at trigger: {canonical['actionability']['valid_at_trigger']}",
        f"Actionability at send: {canonical['actionability']['actionability_at_send']}",
        "",
    ]
    if p.get("entry_reference") is not None:
        lines += [
            f"Entry ref {p['entry_reference']}   SL {p['sl']}   TP1 {p['tp1']}"
            + (f"   TP2 {p['tp2']}" if p.get("tp2") else ""),
        ]
        if r.get("remaining_R_tp1") is not None:
            lines.append(f"Remaining R to TP1 at send: {r['remaining_R_tp1']:.2f}R")
    lines += [
        "",
        f"Evaluated at {canonical['created_at']}",
        f"Trigger at {canonical['trigger_at'] or 'n/a'}",
        f"Expires at {canonical['expires_at'] or 'n/a'}",
        "",
        "Economic edge: NOT VERIFIED",
        "Execution: NOT AUTHORIZED — informational only",
        f"Ticket {canonical['ticket_id']}",
    ]
    return "\n".join(lines)


def render_canonical(canonical: Dict[str, Any]) -> str:
    if canonical["presentation"] == PRESENTATION_WATCH:
        return render_watch_ready(canonical)
    if canonical["presentation"] == PRESENTATION_INFO:
        return render_info_only(canonical)
    # OTHER (BLOCKED / INSUFFICIENT_DATA / OUT_OF_SESSION)
    return (f"{canonical['instrument']} — {canonical['session']} — {canonical['decision']}\n"
            f"reason: {canonical['reason_code']}\n"
            f"evaluated at {canonical['created_at']}\n"
            f"Ticket {canonical['ticket_id']}")


def canonical_hash(canonical: Dict[str, Any]) -> str:
    stable = {k: v for k, v in canonical.items() if k not in ("structure_visual",)}
    return hashlib.sha256(json.dumps(stable, sort_keys=True, default=str).encode()).hexdigest()


def append_archive(path: str, canonical: Dict[str, Any]) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    record = dict(canonical)
    record["canonical_hash"] = canonical_hash(canonical)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True, default=str) + "\n")
