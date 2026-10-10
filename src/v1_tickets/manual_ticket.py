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
from v1_tickets.code_identity import code_sha
from v1_tickets.guards import SPREAD_TOO_WIDE, STALE_AFTER
from v1_tickets.logic_gate import (
    FAIL,
    L5_WARN,
    PASS,
    TICKET_EXPIRED,
    WARN,
    blocking_failures,
    l1_determinism,
    l2_rule_conformance,
    l3_geometry,
    l4_data_session,
    l5_cost,
    l6_freshness,
    order_block_reasons,
)
from v1_tickets.scan_record import (
    NO_SETUP,
    OPPORTUNITY,
    REFERENCE_NOT_READY,
    TICKET_BLOCKED,
    TICKET_READY,
    WATCH,
    append_jsonl,
    classify_fx_ticket,
)

EDGE_STATUS = "NOT VERIFIED — logic only"
AUTHORITY_TEXT = "MANUAL — no automatic order"
RISK_CONFIG_MISSING = "RISK_CONFIG_MISSING"
RISK_NOT_SET_TEXT = "OWNER RISK % NOT SET"
WARN_NOT_SET_TEXT = "WARN LEVEL NOT SET"
COST_ABOVE_BLOCK_R = "COST_ABOVE_BLOCK_R"
REQUIRED_OWNER_KEYS = ("risk_pct", "cost_warn_R", "cost_block_R")
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
    risk = _positive(block.get("risk_pct"))
    warn = _positive(block.get("cost_warn_R"))
    cost_block = _positive(block.get("cost_block_R"))
    config_status = "SET" if all(x is not None for x in (risk, warn, cost_block)) else RISK_CONFIG_MISSING
    return {"risk_pct": risk, "risk_status": config_status,
            "cost_warn_R": warn, "cost_block_R": cost_block,
            "warn_status": "SET" if warn is not None else "NOT_SET"}


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


def collect_block_reasons(*, failed_gates: Sequence[str], base_state: str, base_reason: Optional[str],
                          lot_status: str, spread_check: Optional[str], expired: bool,
                          l5_status: str, owner_config_missing: bool = False,
                          cost_blocked: bool = False) -> "tuple[List[str], List[str]]":
    """(block_reasons, warnings) for a ticket with a signal. Pure; ordered by severity (A2)."""
    reasons: List[Optional[str]] = ["LOGIC_GATE_FAIL:" + g for g in failed_gates]
    if base_state != TICKET_READY:
        reasons.append(base_reason)
    if owner_config_missing:
        reasons.append(RISK_CONFIG_MISSING)
    if lot_status != "OK":
        reasons.append(lot_status)
    if cost_blocked:
        reasons.append(COST_ABOVE_BLOCK_R)
    # The legacy guard returns one decision (stale fires before spread), but it records the
    # spread result first; a too-wide spread is a block reason in its own tier either way.
    if spread_check == SPREAD_TOO_WIDE:
        reasons.append(SPREAD_TOO_WIDE)
    if expired:
        reasons.append(TICKET_EXPIRED)
    warnings = [L5_WARN] if l5_status != PASS else []      # advisory: never a block reason (owner decision 3)
    return order_block_reasons(reasons), warnings


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
        "spread": spread,
        "data_close_utc": _iso(data_close),
        "data_freshness_s": round((now - data_close).total_seconds(), 3) if data_close is not None else None,
        "invariants": {"order_ready": False, "broker_authorized": False, "edge_verified": False,
                       "orders_sent_by_system": 0},
        "window_utc": {"ref": [_iso(t) for t in windows["ref"]], "trade": [_iso(t) for t in windows["trade"]]},
        "logic_gate": {}, "owner_accept_allowed": False,
    }
    has_signal = base.get("direction") is not None
    warnings: List[str] = []
    if has_signal:
        digits = fx._digits(symbol)
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
        owner_config_missing = any(_positive(owner.get(key)) is None for key in REQUIRED_OWNER_KEYS)
        lot["symbol_meta"] = meta_provenance or {"source": "CALLER_SUPPLIED" if meta is not None else META_NONE,
                                                 "broker_symbol": meta.symbol if meta is not None else None}
        spread_r = spread / risk if spread is not None and risk else None
        cost_r = spread_r + (commission_r or 0.0) if spread_r is not None else None
        cost_block_r = _positive(owner.get("cost_block_R"))
        cost_blocked = cost_at_or_above_block(cost_r, cost_block_r)
        ticket.update({
            "branch": f"{base['setup']}:{base['reason_code'] if base['decision'] == 'READY' else base.get('engine_reason_code', base['reason_code'])}",
            "rule_evidence": gates["L2"]["checks"],
            "order_type": base["entry_order_type"], "sl": sl, "tp1": targets.get(1), "tp2": targets.get(2),
            "rr_tp1": round(abs(targets[1] - entry) / risk, 2) if risk else None,
            "rr_tp2": round(abs(targets[2] - entry) / risk, 2) if risk else None,
            "stop_distance": risk, "lot_size": lot["lot"],
            "risk_status": RISK_CONFIG_MISSING if owner_config_missing else lot["status"], "risk": lot,
            "cost_in_R": round(cost_r, 4) if cost_r is not None else None,
            "cost_warn_R": owner["cost_warn_R"] if owner["cost_warn_R"] is not None else WARN_NOT_SET_TEXT,
            "cost_block_R": cost_block_r if cost_block_r is not None else RISK_CONFIG_MISSING,
            "logic_gate": gates, "valid_until": _iso(valid_until), "stale_if": stale_if, "invalid_if": invalid_if,
            "signal_close_utc": _iso(signal_close),
        })
        block_reasons, gate_warnings = collect_block_reasons(
            failed_gates=blocking_failures(gates), base_state=state, base_reason=reason,
            lot_status=lot["status"], spread_check=base.get("spread_check"), expired=now >= valid_until,
            l5_status=gates["L5"]["status"], owner_config_missing=owner_config_missing,
            cost_blocked=cost_blocked)
        warnings.extend(gate_warnings)
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
        ticket["ticket_status"] = {NO_SETUP: "NO_SETUP", WATCH: "WATCH",
                                   REFERENCE_NOT_READY: REFERENCE_NOT_READY}.get(state, "BLOCKED")
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
    if t.get("strategy_id") == "ST_CRYPTO_CFD_SWEEP_RETEST_V1":
        return "\n".join([t["label"], f"{t['symbol']} {t['cycle']} {t['decision']}",
                          f"Reasons: {', '.join(t['reason_codes']) or 'NONE'}",
                          f"Warnings: {', '.join(t['warnings']) or 'NONE'}",
                          f"Entry {t.get('entry')} SL {t.get('stop_loss')} TP1 {t.get('tp1')} TP2 {t.get('tp2')}",
                          f"Cost {t.get('cost_in_R')} R; volume {t.get('volume')}",
                          "EDGE_VERIFIED=FALSE | EXECUTION AUTHORIZED=FALSE"])
    display_state = t["state"]
    display_reason = t.get("primary_block_reason")
    if display_state == TICKET_READY and t.get("logic_status") != "LOGIC_VERIFIED":
        display_state = TICKET_BLOCKED
        display_reason = display_reason or "LOGIC_STATUS_NOT_VERIFIED"
    lines = [
        "AG TRADE TICKET — MANUAL DECISION",
        f"#{t['ticket_id']}  Strategy {t['strategy']}  Session {t['session']}",
        f"State       {display_state}" + (f" ({display_reason})" if display_reason else "")
        + (f"  also: {', '.join(t['block_reasons'][1:])}" if len(t.get("block_reasons") or []) > 1 else "")
        + (f"  warn: {', '.join(t['warnings'])}" if t.get("warnings") else ""),
        f"Logic gate  {gate_line(t)}",
        f"logic_status: {t['logic_status']}",
        "EDGE_VERIFIED=FALSE",
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


def render_market_structure(t: Dict[str, Any], *, unicode_safe: bool = True) -> str:
    """Render validated ticket levels as a mobile-safe scenario diagram.

    This is presentation only: levels are copied from the ticket and never calculated or
    repaired here. Incomplete or non-actionable geometry fails gracefully. The word
    ``SCENARIO`` is deliberate; the diagram is not a price forecast or broker order.
    """
    direction = t.get("direction")
    entry, sl, tp1, tp2 = (t.get("entry"), t.get("sl"), t.get("tp1"), t.get("tp2"))
    if direction not in ("LONG", "SHORT") or any(v is None for v in (entry, sl, tp1, tp2)):
        return "MARKET STRUCTURE UNAVAILABLE — incomplete validated levels" if unicode_safe else \
            "MARKET STRUCTURE UNAVAILABLE - incomplete validated levels"
    valid = (sl < entry < tp1 <= tp2) if direction == "LONG" else (sl > entry > tp1 >= tp2)
    if not valid:
        return "MARKET STRUCTURE UNAVAILABLE — invalid level geometry" if unicode_safe else \
            "MARKET STRUCTURE UNAVAILABLE - invalid level geometry"

    rule = "─────────" if unicode_safe else "---------"
    arrow = "▲" if direction == "LONG" and unicode_safe else "▼" if unicode_safe else \
        "^" if direction == "LONG" else "v"
    liquidity = "SWEEP LOW" if direction == "LONG" else "SWEEP HIGH"
    setup = t.get("setup") or "VALIDATED TRIGGER"
    return "\n".join([
        f"{t.get('symbol', 'UNKNOWN')} {direction} — MARKET STRUCTURE SCENARIO"
        if unicode_safe else f"{t.get('symbol', 'UNKNOWN')} {direction} - MARKET STRUCTURE SCENARIO",
        "NOT A PRICE FORECAST | BROKER ORDER: NONE", "",
        f"{_p(tp2):>12}  {rule} TP2", f"{'':>16}{arrow}",
        f"{_p(tp1):>12}  {rule} TP1", f"{'':>16}{arrow}",
        f"{_p(entry):>12}  {rule} ENTRY", f"{'':>16}{arrow}",
        f"{_p(sl):>12}  {rule} SL  {liquidity}", "",
        f"Scenario: Liquidity Sweep -> {setup} -> Proposed Entry -> Liquidity Objective",
        f"Invalidation: {t.get('invalid_if') or 'UNAVAILABLE'}",
        f"Expiration: {t.get('valid_until') or 'UNAVAILABLE'}",
        "OWNER DECISION REQUIRED | EXECUTION AUTHORIZED = FALSE",
    ])


def render_mobile(t: Dict[str, Any], *, layout: str = "COMPACT", unicode_safe: bool = True) -> str:
    """Owner-selectable compact or expanded manual-ticket text."""
    if layout == "COMPACT":
        return render_text(t)
    if layout == "EXPANDED":
        return render_text(t) + "\n\n" + render_market_structure(t, unicode_safe=unicode_safe)
    raise ValueError("layout must be COMPACT or EXPANDED")


def content_hash(ticket: Dict[str, Any]) -> str:
    stable = {k: v for k, v in ticket.items() if k not in ("evaluated_at",)}
    return hashlib.sha256(json.dumps(stable, sort_keys=True, default=str).encode()).hexdigest()


def ticket_path(journal: str, day: dt.date) -> str:
    return os.path.join(journal, TICKET_DIR, f"{day.isoformat()}.jsonl")


def archive_manual_ticket(journal: str, ticket: Dict[str, Any]) -> str:
    """Append-only: a changed ticket is a new line; nothing is overwritten."""
    path = ticket_path(journal, dt.date.fromisoformat(ticket["session_date"]))
    # code_sha is provenance, kept outside content_hash so a deploy alone never re-archives a ticket.
    append_jsonl(path, {**ticket, "code_sha": code_sha(), "content_hash": content_hash(ticket)})
    return path


M5_CRYPTO = dt.timedelta(minutes=5)

# Crypto-CFD manual proposal adapter. The FX builder above and its frozen rules are
# deliberately untouched; this path consumes only the dedicated CFD contract result.
def crypto_cfd_commission(symbol: str, root: Path = REPO_ROOT) -> Optional[float]:
    """Only an explicit, symbol-bound host symbol_info commission in R is usable.

    MT5 symbol_info usually does not expose commission. Missing/unsupported evidence is
    UNKNOWN, never zero and never inferred from swap or a perp/FX fee schedule.
    """
    import math

    path = root / "status" / "evidence" / f"host_symbol_info_{symbol}.json"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict) or record.get("symbol") != symbol or record.get("commission_status") != "AVAILABLE":
        return None
    value = record.get("commission_R")
    return float(value) if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def cost_at_or_above_block(cost_r: Optional[float], block_r: Optional[float]) -> bool:
    """Shared FX/crypto threshold predicate: the configured boundary itself blocks."""
    return cost_r is not None and block_r is not None and cost_r >= block_r


def crypto_cfd_cost_gate(distance: float, spread: float, commission_r: Optional[float],
                         policy: Dict[str, Any]) -> tuple[List[str], List[str], float, float]:
    """Owner D4/D2 friction thresholds; unknown commission contributes no invented fee."""
    import math

    required = ("spread_ok_pct", "spread_block_pct", "risk_pct", "cost_warn_R", "cost_block_R")
    if any(type(policy.get(k)) not in (int, float) or not math.isfinite(policy[k])
           or policy[k] <= 0 for k in required):
        return ["RISK_POLICY_AMBIGUOUS", "SPREAD_POLICY_UNDEFINED"], [], float("nan"), float("nan")
    if (policy["spread_ok_pct"] >= policy["spread_block_pct"]
            or policy["cost_warn_R"] >= policy["cost_block_R"] or policy["risk_pct"] > 100):
        return ["RISK_POLICY_AMBIGUOUS", "SPREAD_POLICY_UNDEFINED"], [], float("nan"), float("nan")
    if commission_r is not None and (type(commission_r) not in (int, float)
                                    or not math.isfinite(commission_r) or commission_r < 0):
        return ["COST_NOT_EVALUATED"], [], float("nan"), float("nan")
    if (type(distance) not in (int, float) or type(spread) not in (int, float)
            or not all(math.isfinite(x) for x in (distance, spread)) or distance <= 0 or spread < 0):
        return ["SPREAD_NOT_EVALUATED"], [], float("nan"), float("nan")
    pct = spread / distance * 100
    cost = spread / distance + (commission_r if commission_r is not None else 0)
    blocks, warnings = [], []
    if policy["spread_block_pct"] is not None and pct > policy["spread_block_pct"]:
        blocks.append("SPREAD_TOO_WIDE")
    elif policy["spread_ok_pct"] is not None and pct > policy["spread_ok_pct"]:
        warnings.append("SPREAD_WARN")
    if cost_at_or_above_block(cost, policy["cost_block_R"]):
        blocks.append("COST_TOO_HIGH")
    elif policy["cost_warn_R"] is not None and cost >= policy["cost_warn_R"]:
        warnings.append("COST_WARN")
    return blocks, warnings, pct, cost


def build_crypto_cfd_manual_ticket(
    result: Dict[str, Any], *, now: dt.datetime, window: str, spread: Optional[float],
    balance: Optional[float] = None, meta: Optional[SymbolMeta] = None,
    commission_r: Optional[float] = None, policy: Optional[Dict[str, Any]] = None,
    quote_time: Optional[dt.datetime] = None,
) -> Dict[str, Any]:
    """Map the dedicated closed-candle engine result to a non-executing manual ticket.

    No strategy version can become READY until a matching L1-L6 identity has been
    registered and ticket_ready explicitly activated. Neither this adapter nor the
    evidence source can grant that authority.
    """
    import math

    from crypto_cfd_contract.contract import CONTRACT_ID, CONTRACT_VERSION
    from v1_tickets.authority import load_registry, logic_identity
    from v1_tickets.crypto_cfd_policy import load_ticket_policy

    if result.get("contract_id") != CONTRACT_ID or result.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("crypto CFD contract identity mismatch")
    symbol = result["symbol"]
    cfg = policy if policy is not None else load_ticket_policy()
    if commission_r is not None and (not math.isfinite(commission_r) or commission_r < 0):
        commission_r = None
    reasons = [r for r in ("SPREAD_POLICY_UNDEFINED", "RISK_POLICY_AMBIGUOUS")
               if r in cfg["open_authorities"]]
    warnings = ["COMMISSION_UNKNOWN"] if commission_r is None else []
    lot = None
    plan = result.get("evidence", {}).get("target_plan") or {}
    entry, sl = plan.get("entry"), plan.get("stop_loss")
    distance = abs(entry - sl) if entry is not None and sl is not None else None
    spread_pct = spread_r = cost_r = None
    if result["result"] == "REFERENCE_INCOMPLETE":
        decision = "DATA_ERROR"
        reasons.extend(result["reason_codes"])
    elif result["result"] != "ENTRY_VALID":
        decision = "NO_TRADE"
        reasons.extend(result["reason_codes"])
    else:
        decision = "READY"
        if distance is None or not math.isfinite(distance) or distance <= 0:
            reasons.append("INVALID_STOP_DISTANCE")
        if spread is None or distance is None:
            reasons.append("SPREAD_NOT_EVALUATED")
        else:
            cost_blocks, cost_warnings, spread_pct, cost_r = crypto_cfd_cost_gate(
                distance, spread, commission_r, cfg)
            reasons.extend(cost_blocks)
            warnings.extend(cost_warnings)
            spread_r = spread / distance if distance > 0 else None
        if quote_time is None or quote_time.tzinfo is None or not dt.timedelta(0) <= now - quote_time <= M15:
            reasons.append("QUOTE_STALE_OR_MISSING")
        signal_time = dt.datetime.fromisoformat(result["evidence"]["retest"]["candle_time_utc"])
        if now > signal_time + M5_CRYPTO + M15:
            reasons.append("SIGNAL_STALE")
        lot = lot_size(entry, sl, {"risk_pct": cfg["risk_pct"]}, balance, meta) if cfg["risk_pct"] else None
        if lot is not None and lot["status"] != "OK":
            reasons.append(lot["status"])
        registry = load_registry(REPO_ROOT).get(CONTRACT_ID) or {}
        identity = logic_identity(CONTRACT_ID, CONTRACT_VERSION)
        verified = (identity is not None and registry.get("logic_status") == "LOGIC_VERIFIED"
                    and registry.get("logic_verified_identity") == identity["digest"])
        if not (verified and registry.get("active") is True and registry.get("ticket_ready") == "ACTIVE"):
            reasons.append("LOGIC_STATUS_NOT_VERIFIED")
        if reasons:
            decision = "BLOCKED"
    if reasons and decision in ("NO_TRADE", "DATA_ERROR") and any(r in reasons for r in
                                                   ("SPREAD_POLICY_UNDEFINED", "RISK_POLICY_AMBIGUOUS")):
        decision = "BLOCKED"
    if decision == "READY" and reasons:
        raise RuntimeError("READY with blocking reasons")
    return {
        "label": "INFORMATIONAL PROPOSAL -- NOT A BROKER ORDER",
        "strategy_id": CONTRACT_ID, "strategy_version": CONTRACT_VERSION,
        "symbol": symbol, "cycle": window, "evaluated_at": now.astimezone(dt.timezone.utc).isoformat(),
        "decision": decision, "reason_codes": list(dict.fromkeys(reasons)), "warnings": list(dict.fromkeys(warnings)),
        "engine_result": result, "spread_pct_of_stop": spread_pct, "spread_R": spread_r,
        "cost_in_R": cost_r, "commission_R": commission_r,
        "risk_pct": cfg["risk_pct"], "volume": lot["lot"] if result["result"] == "ENTRY_VALID" and lot else None,
        "entry": entry, "stop_loss": sl, "tp1": plan.get("tp1"), "tp2": plan.get("tp2"),
        "direction": plan.get("direction"), "valid_until": (
            (dt.datetime.fromisoformat(result["evidence"]["retest"]["candle_time_utc"]) + M5_CRYPTO + M15).isoformat()
            if result["result"] == "ENTRY_VALID" else None), "execution_authorized": False,
        "owner_accept_allowed": decision == "READY", "edge_verified": False,
    }
