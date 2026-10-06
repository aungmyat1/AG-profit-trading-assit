"""Manual Trade Ticket V1 Phase 5 -- the owner-facing MANUAL ticket.

Extends the existing V1 FX ticket dict (v1_tickets.fx.build_fx_ticket); there is no second
ticket model. Adds the logic gate, owner risk sizing (read-only balance), cost in R, expiry
and the plain-text render. Invariants, stamped on every ticket:

    TICKET_READY != ORDER_READY != BROKER_AUTHORIZED != EDGE_VERIFIED

No broker call exists here: balance and symbol metadata are injected values, and lot size
comes from the broker-free sizing_math boundary.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import yaml

from mt5.symbol_resolver import SymbolMeta
from sizing_math.risk import size_position
from strategy_engine import load_strategy
from strategy_engine.session import Candle
from ticket_delivery.identity import logical_ticket_id
from v1_tickets import fx
from v1_tickets.authority import REPO_ROOT, TicketAuthority, resolve_ticket_authority
from v1_tickets.guards import STALE_AFTER
from v1_tickets.logic_gate import (
    FAIL, L5_WARN, PASS, TICKET_EXPIRED, WARN, blocking_failures, l1_determinism, l2_rule_conformance,
    l3_geometry, l4_data_session, l5_cost, l6_freshness, order_block_reasons,
)
from v1_tickets.scan_record import (
    NO_SETUP, OPPORTUNITY, TICKET_BLOCKED, TICKET_READY, WATCH, append_jsonl, classify_fx_ticket,
)

EDGE_STATUS = "NOT VERIFIED — logic only"
AUTHORITY_TEXT = "MANUAL — no automatic order"
RISK_CONFIG_MISSING = "RISK_CONFIG_MISSING"
RISK_NOT_SET_TEXT = "OWNER RISK % NOT SET"
WARN_NOT_SET_TEXT = "WARN LEVEL NOT SET"
OWNER_CONFIG = "config/owner_ticket.yaml"
OWNER_CONFIG_LOCAL = "config/local/owner_ticket.yaml"
TICKET_DIR = os.path.join("ticket_delivery", "manual", "tickets")
M15 = dt.timedelta(minutes=15)
_MARK = {PASS: "✓", FAIL: "✗", WARN: "⚠"}


# ------------------------------------------------------------------------- owner config (C4)

def _positive(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if value > 0 else None


def load_owner_config(root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Host-local file wins when present. No default value exists for either field."""
    raw: Any = None
    for rel in (OWNER_CONFIG_LOCAL, OWNER_CONFIG):
        path = root / rel
        if path.is_file():
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            except yaml.YAMLError:
                raw = None
            break
    block = raw.get("owner_ticket") if isinstance(raw, dict) else None
    block = block if isinstance(block, dict) else {}
    risk, warn = _positive(block.get("risk_pct")), _positive(block.get("cost_warn_R"))
    return {"risk_pct": risk, "risk_status": "SET" if risk is not None else RISK_CONFIG_MISSING,
            "cost_warn_R": warn, "warn_status": "SET" if warn is not None else "NOT_SET"}


def symbol_meta_from_host(symbol: str) -> Optional[SymbolMeta]:
    """Verified host capture only (same authority as fx.host_record); None when absent."""
    record = fx.host_record(symbol)
    if record is None:
        return None
    f = record["fields"]
    try:
        return SymbolMeta(symbol=record["broker_symbol"], tick_size=float(f["trade_tick_size"]),
                          tick_value=float(f["trade_tick_value"]), contract_size=float(f["trade_contract_size"]),
                          volume_min=float(f["volume_min"]), volume_max=float(f["volume_max"]),
                          volume_step=float(f["volume_step"]), digits=int(f["digits"]), point=float(f["point"]))
    except (KeyError, TypeError, ValueError):
        return None


META_LIVE = "LIVE_SYMBOL_INFO"
META_CAPTURE_FALLBACK = "HOST_CAPTURE_FALLBACK"
META_NONE = "NONE"


def _usable(meta: Optional[SymbolMeta]) -> bool:
    return meta is not None and meta.tick_size > 0 and meta.tick_value > 0 and meta.volume_step > 0


def resolve_symbol_meta(symbol: str, live: Optional[SymbolMeta], now: dt.datetime) -> tuple:
    """Sizing metadata authority: fresh read-only broker symbol_info first; the verified host
    capture only as an explicit, provenance-stamped fallback; otherwise None (fail closed)."""
    expected = fx.REQUIRED_BROKER_SYMBOL.get(symbol)
    if _usable(live) and (expected is None or live.symbol == expected):
        return live, {"source": META_LIVE, "broker_symbol": live.symbol}
    record = fx.host_record(symbol)
    meta = symbol_meta_from_host(symbol)
    if _usable(meta):
        captured = record.get("captured_at_utc")
        try:
            age_h = int((now - dt.datetime.fromisoformat(captured)).total_seconds() // 3600)
        except (TypeError, ValueError):
            age_h = None
        return meta, {"source": META_CAPTURE_FALLBACK, "broker_symbol": meta.symbol, "captured_at": captured,
                      "capture_age_h": age_h, "live_unavailable": live is None}
    return None, {"source": META_NONE, "broker_symbol": None}


def lot_size(entry: Optional[float], sl: Optional[float], owner: Dict[str, Any], balance: Optional[float],
             meta: Optional[SymbolMeta]) -> Dict[str, Any]:
    if owner["risk_pct"] is None:
        return {"lot": RISK_NOT_SET_TEXT, "status": RISK_CONFIG_MISSING, "risk_pct": None}
    if balance is None or not balance > 0:
        return {"lot": None, "status": "ACCOUNT_BALANCE_UNAVAILABLE", "risk_pct": owner["risk_pct"]}
    if meta is None or not meta.tick_size > 0 or not meta.tick_value > 0 or not meta.volume_step > 0:
        return {"lot": None, "status": "SYMBOL_METADATA_MISSING", "risk_pct": owner["risk_pct"]}
    if entry is None or sl is None:
        return {"lot": None, "status": "INVALID_STOP_DISTANCE", "risk_pct": owner["risk_pct"]}
    volume, risk_amount, reason = size_position(entry, sl, balance, owner["risk_pct"], meta)
    return {"lot": volume, "status": reason or "OK", "risk_pct": owner["risk_pct"],
            "risk_amount": round(risk_amount, 2) if risk_amount is not None else None, "balance": balance}


# ------------------------------------------------------------------------- build

def _iso(t: Optional[dt.datetime]) -> Optional[str]:
    return t.isoformat() if t else None


def build_manual_ticket(
    symbol: str, cycle: str, session_date: dt.date, session: Sequence[Candle], expected_bar_count: int,
    post: Sequence[Candle], *, now: dt.datetime, data_close: Optional[dt.datetime], spread: Optional[float],
    owner: Dict[str, Any], balance: Optional[float] = None, meta: Optional[SymbolMeta] = None,
    commission_r: Optional[float] = None, data_source: str = "MT5_VT_MARKETS_DEMO",
    authority: Optional[TicketAuthority] = None, meta_provenance: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    strategy = load_strategy(fx.STRATEGY_PATH)
    windows = fx.session_windows_utc(session_date)[cycle]
    pair = next(p for p in strategy.session_pairs if p.pair_id == cycle)

    def build() -> Dict[str, Any]:
        return fx.build_fx_ticket(symbol, cycle, session_date, session, expected_bar_count, post,
                                  data_source=data_source, evaluated_at=now, data_close=data_close, spread=spread)

    base = build()
    authority = authority or resolve_ticket_authority(base["strategy_id"], base["strategy_version"])
    state, stage, reason = classify_fx_ticket(base, now=now, window_end=windows["trade"][1])
    ticket: Dict[str, Any] = {
        **base,
        "ticket_id": logical_ticket_id(strategy_id=base["strategy_id"], strategy_version=base["strategy_version"],
                                       symbol=symbol, cycle=cycle, trading_date=session_date),
        "strategy": f"{base['strategy_id']}@{base['strategy_version']}",
        "session": cycle,
        "edge_status": EDGE_STATUS, "economic_status": authority.economic_status,
        "authority": AUTHORITY_TEXT, "ticket_authority": authority.ticket_authority,
        "logic_status": authority.logic_status_effective,
        "logic_identity": (authority.logic_identity or {}).get("digest"),
        "invariants": {"order_ready": False, "broker_authorized": False, "edge_verified": False,
                       "orders_sent_by_system": 0},
        "window_utc": {"ref": [_iso(t) for t in windows["ref"]], "trade": [_iso(t) for t in windows["trade"]]},
        "logic_gate": {}, "owner_accept_allowed": False,
    }
    has_signal = base.get("direction") is not None
    warnings: List[str] = []
    if has_signal:
        digits = fx._digits(symbol)
        long = base["direction"] == "LONG"
        entry, sl, risk = base["entry"], base["stop_loss"], base["risk_distance"]
        targets = {t["leg"]: t["price"] for t in base["targets"]}
        sig_open = (dt.datetime.fromisoformat(base["signal_timestamp"]) if base.get("signal_timestamp")
                    else (post[0].time if post else None))
        signal_close = sig_open + M15 if sig_open else None
        time_invalid = dt.datetime.combine(session_date, dt.time(15), tzinfo=dt.timezone.utc)
        valid_until = min(t for t in (signal_close + STALE_AFTER if signal_close else None,
                                      windows["trade"][1], time_invalid) if t is not None)
        stale_if = {"rule": "LONG: ask above entry / SHORT: bid below entry before manual fill -- the MARKET "
                            "entry at the signal close is no longer available", "entry": entry,
                    "direction": base["direction"], "or_after": _iso(valid_until)}
        invalid_if = {"sl_touched_before_fill": sl, "time_invalidation_utc": _iso(time_invalid),
                      "structural": strategy.structural_invalidation}
        gates = {
            "L1": l1_determinism(build, list(session) + list(post), now),
            "L2": l2_rule_conformance(strategy, base, session, expected_bar_count, post, digits=digits, spread=spread),
            "L3": l3_geometry(base, post, digits=digits,
                              declared_rr=next((leg.fixed_r_multiple for leg in strategy.legs
                                                if leg.target_type == "FIXED_R_MULTIPLE"), None)),
            "L4": l4_data_session(base, ref_window=windows["ref"], trade_window=windows["trade"],
                                  reference_name=pair.reference_session.name, session=session,
                                  expected_bar_count=expected_bar_count, post=post, data_close=data_close, now=now),
            "L5": l5_cost(spread, risk, commission_r=commission_r, warn_r=owner["cost_warn_R"]),
            "L6": l6_freshness(_iso(valid_until), stale_if, invalid_if),
        }
        lot = lot_size(entry, sl, owner, balance, meta)
        lot["symbol_meta"] = meta_provenance or {"source": "CALLER_SUPPLIED" if meta is not None else META_NONE,
                                                 "broker_symbol": meta.symbol if meta is not None else None}
        spread_r = spread / risk if spread is not None and risk else None
        ticket.update({
            "branch": f"{base['setup']}:{base['reason_code'] if base['decision'] == 'READY' else base.get('engine_reason_code', base['reason_code'])}",
            "rule_evidence": gates["L2"]["checks"],
            "order_type": base["entry_order_type"], "sl": sl, "tp1": targets.get(1), "tp2": targets.get(2),
            "rr_tp1": round(abs(targets[1] - entry) / risk, 2) if risk else None,
            "rr_tp2": round(abs(targets[2] - entry) / risk, 2) if risk else None,
            "stop_distance": risk, "lot_size": lot["lot"], "risk_status": lot["status"], "risk": lot,
            "cost_in_R": round(spread_r + (commission_r or 0.0), 4) if spread_r is not None else None,
            "cost_warn_R": owner["cost_warn_R"] if owner["cost_warn_R"] is not None else WARN_NOT_SET_TEXT,
            "logic_gate": gates, "valid_until": _iso(valid_until), "stale_if": stale_if, "invalid_if": invalid_if,
            "signal_close_utc": _iso(signal_close),
        })
        failed = blocking_failures(gates)
        # Collect every blocking reason (A2), then order by severity; the primary is the most severe.
        reasons: List[Optional[str]] = ["LOGIC_GATE_FAIL:" + g for g in failed]
        if state != TICKET_READY:
            reasons.append(reason)
        if lot["status"] != "OK":
            reasons.append(lot["status"])
        if now >= valid_until:
            reasons.append(TICKET_EXPIRED)
        if gates["L5"]["status"] != PASS:
            warnings.append(L5_WARN)            # advisory: never a block reason (owner decision 3)
        block_reasons = order_block_reasons(reasons)
        if block_reasons:
            state, reason = TICKET_BLOCKED, block_reasons[0]
            stage = ("LOGIC_GATE" if reason.startswith("LOGIC_GATE_FAIL:") else
                     "RISK" if reason == lot["status"] else "TICKET" if reason == TICKET_EXPIRED else stage)
        elif state == TICKET_READY:
            reason = None
        if state == TICKET_READY and not authority.ticket_eligible:
            state, stage, reason = OPPORTUNITY, "AUTHORITY", authority.reason
            block_reasons = order_block_reasons([reason] + block_reasons)
        ticket["owner_accept_allowed"] = state == TICKET_READY and now < valid_until
        ticket["ticket_status"] = ("EXPIRED" if now >= valid_until else
                                   {TICKET_READY: "READY", OPPORTUNITY: "OPPORTUNITY"}.get(state, "BLOCKED"))
    else:
        block_reasons = order_block_reasons([reason])
        ticket["ticket_status"] = {NO_SETUP: "NO_SETUP", WATCH: "WATCH"}.get(state, "BLOCKED")
    primary = reason if reason in block_reasons else (block_reasons[0] if block_reasons and state != TICKET_READY
                                                       else None)
    if state == TICKET_READY:
        if block_reasons:                               # invariant: a READY ticket carries no block reason
            raise RuntimeError(f"TICKET_READY with block_reasons {block_reasons}")
    ticket.update({"block_reasons": block_reasons, "primary_block_reason": primary, "warnings": warnings})
    # `stop_reason` is kept only as an alias of primary_block_reason for existing readers.
    ticket.update({"state": state, "stage_reached": stage, "stop_reason": primary,
                   # The legacy informational decision is recorded beside, never merged into, the manual state.
                   "legacy_informational_decision": base["decision"],
                   "legacy_informational_ready": base["decision"] == "READY"})
    return ticket


# ------------------------------------------------------------------------- render / archive

def gate_line(ticket: Dict[str, Any]) -> str:
    gates = ticket.get("logic_gate") or {}
    return " ".join(f"{g} {_MARK.get(gates.get(g, {}).get('status'), '–')}" for g in ("L1", "L2", "L3", "L4", "L5", "L6"))


def _p(value: Any) -> str:
    return "-" if value is None else str(value)


def _meta_note(prov: Optional[Dict[str, Any]]) -> str:
    if not prov or prov.get("source") == META_LIVE:
        return ""
    if prov.get("source") == META_CAPTURE_FALLBACK:
        return f" [SIZED FROM CAPTURED METADATA {prov.get('captured_at')}, age {prov.get('capture_age_h')} h]"
    return " [SYMBOL METADATA UNAVAILABLE]"


def render_text(t: Dict[str, Any]) -> str:
    """Plain text in the owner's layout. Delivered only through the existing channel."""
    lines = [
        "AG TRADE TICKET — MANUAL DECISION",
        f"#{t['ticket_id']}  Strategy {t['strategy']}  Session {t['session']}",
        f"State       {t['state']}" + (f" ({t['primary_block_reason']})" if t.get("primary_block_reason") else "")
        + (f"  also: {', '.join(t['block_reasons'][1:])}" if len(t.get("block_reasons") or []) > 1 else "")
        + (f"  warn: {', '.join(t['warnings'])}" if t.get("warnings") else ""),
        f"Logic gate  {gate_line(t)}",
        f"Logic status {t['logic_status']} (strategy)   Economic {t['economic_status']}",
        f"Edge status {t['edge_status']}",
        f"Authority   {t['authority']}",
    ]
    if t.get("direction") is None:
        return "\n".join(lines + [f"{t['symbol']} — no setup"])
    box = t.get("box") or {}
    l5 = {c["id"]: c for c in t["logic_gate"]["L5"]["checks"]}
    lines += [
        f"{t['symbol']} {t['direction']}",
        f"WHY: context {t.get('regime')} / range {box.get('low')}-{box.get('high')} (mid {box.get('mid')}) / "
        f"liquidity {'reference low' if t['direction'] == 'LONG' else 'reference high'} / "
        f"trigger {t.get('signal_timestamp') or 'box close'} / branch {t['branch']}",
        f"ORDER FIELDS: type {t['order_type']}, entry {_p(t['entry'])}, SL {_p(t['sl'])}, "
        f"TP1 {_p(t['tp1'])} ({_p(t['rr_tp1'])}R), TP2 {_p(t['tp2'])} ({_p(t['rr_tp2'])}R)",
        f"RISK: stop {_p(t['stop_distance'])}, lot {_p(t['lot_size'])} @ "
        f"{_p(t['risk']['risk_pct']) + ' %' if t['risk']['risk_pct'] is not None else RISK_NOT_SET_TEXT}"
        f" [{t['risk_status']}], cost {_p(t['cost_in_R'])} R"
        f" (warn {t['cost_warn_R']}; {l5['L5.commission_R']['note'] or 'commission incl.'})"
        + _meta_note(t['risk'].get('symbol_meta')),
        f"VALID UNTIL {t['valid_until']} / STALE IF {t['stale_if']['rule']} / "
        f"INVALID IF SL {t['invalid_if']['sl_touched_before_fill']} touched before fill or after "
        f"{t['invalid_if']['time_invalidation_utc']}",
    ]
    return "\n".join(lines)


def content_hash(ticket: Dict[str, Any]) -> str:
    stable = {k: v for k, v in ticket.items() if k not in ("evaluated_at",)}
    return hashlib.sha256(json.dumps(stable, sort_keys=True, default=str).encode()).hexdigest()


def ticket_path(journal: str, day: dt.date) -> str:
    return os.path.join(journal, TICKET_DIR, f"{day.isoformat()}.jsonl")


def archive_manual_ticket(journal: str, ticket: Dict[str, Any]) -> str:
    """Append-only: a changed ticket is a new line; nothing is overwritten."""
    path = ticket_path(journal, dt.date.fromisoformat(ticket["session_date"]))
    append_jsonl(path, {**ticket, "content_hash": content_hash(ticket)})
    return path
