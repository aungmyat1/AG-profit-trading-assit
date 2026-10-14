"""Pass-through canonical rendering and opt-in HTTPS Bot API delivery.

No canonical builder import: evaluation, market data and authority stay upstream.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import logging
import os
import sqlite3
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from telegram_delivery.scope_policy import resolve as resolve_immediate_scope
from v1_tickets.scope_status import REPORT_ONLY_HEADER, report_header

LOG = logging.getLogger(__name__)
STATUSES = frozenset({"WATCH_READY", "INFO_ONLY_STALE", "INFO_ONLY_INSUFFICIENT_REMAINING_R",
                      "INFO_ONLY_POLICY_UNRESOLVED", "INFO_ONLY_SUPPRESSED", "NO_TRADE",
                      "EXPIRED", "MISSED", "BLOCKED", "INSUFFICIENT_DATA", "OUT_OF_SESSION"})
STATE_PENDING = "pending"
STATE_SENT = "sent"
STATE_DELIVERED = "DELIVERED"
STATE_UNCERTAIN = "DELIVERY_UNCERTAIN"
STATE_FAILED = "DELIVERY_FAILED"


class DeliveryInProgress(Exception):
    """Another process holds the delivery-key lock."""


class TelegramAPIError(RuntimeError):
    def __init__(self, error_code):
        super().__init__(f"Telegram API error {error_code}")
        self.error_code = str(error_code)
DELIVERED_STATES = frozenset({STATE_SENT, STATE_DELIVERED})


def value(ticket, *path):
    current = ticket
    for key in path:
        if not isinstance(current, dict) or key not in current or current[key] is None:
            return "SCHEMA_GAP: " + ".".join(path)
        current = current[key]
    # Keep each source fact on one line, including session-summary reasons.
    return " ".join(str(current).splitlines())


def _known_decision(decision):
    return isinstance(decision, str) and decision in STATUSES


def _informational_scope(decision):
    """WATCH_READY and non-suppressed INFO_ONLY_* -- gated by the C16 scope flag."""
    return isinstance(decision, str) and decision != "INFO_ONLY_SUPPRESSED" and (
        decision == "WATCH_READY" or decision.startswith("INFO_ONLY_"))


def displayed_decision(ticket):
    decision = ticket.get("decision")
    if decision in {"READY", "TICKET_READY", "WATCH_READY"} and ticket.get("logic_status") != "LOGIC_VERIFIED":
        return "NOT_READY"
    return decision


def validate(ticket):
    if ticket.get("schema") != "AG_CANONICAL_TICKET_V1":
        raise ValueError("Unsupported canonical schema")
    if not _known_decision(ticket.get("decision")):
        raise ValueError("Unsupported canonical decision")
    if not isinstance(ticket.get("ticket_id"), str) or not ticket["ticket_id"]:
        raise ValueError("SCHEMA_GAP: ticket_id")


def footer(ticket):
    logic_status = value(ticket, 'logic_status')
    actionability_decision = value(ticket, 'actionability', 'decision')
    actionability_reason = value(ticket, 'actionability', 'reason')
    if logic_status != "LOGIC_VERIFIED" and actionability_decision in {"READY", "TICKET_READY", "WATCH_READY"}:
        actionability_decision, actionability_reason = "NOT_READY", "LOGIC_STATUS_NOT_VERIFIED"
    scope = []
    if "scope_verification_status" in ticket:   # AGP-C18-R2 additive fields; absent on older tickets
        if ticket.get("scope_route") != "REPORT_ONLY":
            raise ValueError("Unsupported scope route")
        scope = [f"scope: {ticket['scope_verification_status']} | REPORT_ONLY ({value(ticket, 'scope_reason')})",
                 f"report_class: {value(ticket, 'report_class')}"]
    return scope + [f"logic_status: {logic_status}",
            f"Edge: {value(ticket, 'economic_edge')} ({value(ticket, 'economic_status')})",
            f"Actionability: {actionability_decision} / {actionability_reason}",
            "EDGE_VERIFIED=FALSE", "EXECUTION: DISABLED"]


def render_ticket(ticket):
    validate(ticket)
    lines = [f"Ticket: {ticket['ticket_id']}",
             f"{value(ticket, 'instrument')} | {displayed_decision(ticket)} | {value(ticket, 'direction')}",
             f"Session: {value(ticket, 'session_date')} / {value(ticket, 'session')}",
             f"Reason: {value(ticket, 'reason_code')}", "Levels (supplied prices only):"]
    for label, key in (("TP2", "tp2"), ("TP1", "tp1"), ("NOW", "current_send"),
                       ("ENTRY", "entry_reference"), ("SL", "sl")):
        lines.append(f"{label:<5} +---------------- {value(ticket, 'prices', key)}")
    lines += [f"Remaining R TP1: {value(ticket, 'risk', 'remaining_R_tp1')}",
              f"Remaining R TP2: {value(ticket, 'risk', 'remaining_R_tp2')}"]
    return "\n".join(lines + footer(ticket))


def render_summary(tickets, uncertain=()):
    tickets = list(tickets)
    for ticket in tickets:
        validate(ticket)
    if tickets and len({(t.get("session_date"), t.get("session")) for t in tickets}) != 1:
        raise ValueError("Summary must contain exactly one session")
    lines = ["Session summary", f"Rows: {len(tickets)}"]
    for index, ticket in enumerate(tickets, 1):
        lines.append(f"{index}. {ticket['ticket_id']} | {value(ticket, 'instrument')} | "
                     f"{displayed_decision(ticket)} | {value(ticket, 'reason_code')} | "
                     + " | ".join(footer(ticket)[:3] + footer(ticket)[3:4]))
    uncertain = list(uncertain)
    if uncertain:
        lines.append("Uncertain delivery:")
        for item in uncertain:
            identity = item["identity"] if isinstance(item, dict) else item[0]
            status = item.get("status", "") if isinstance(item, dict) else item[1]
            lines.append(f"- possibly undelivered: {identity} | {status} | {STATE_UNCERTAIN}")
    lines += ["Logic: see each row", "Edge: see each row", "Actionability: see each row",
              "EDGE_VERIFIED=FALSE",
              "EXECUTION: DISABLED"]
    return "\n".join(lines)


LSMC_CRYPTO_SUMMARY_SCHEMA = "AGP_HOST_LSMC_CRYPTO_SESSION_SUMMARY_V1"
CRYPTO_STRATEGY_SUMMARY_SCHEMA = "AGP_HOST_CRYPTO_STRATEGY_SESSION_SUMMARY_V1"
SCOPE_ROUTES = frozenset({"REPORT_ONLY"})   # the only route a status report may show (OD1012-ROUTING)


def scope_status_lines(statuses):
    """Per-scope verification status lines (pre-resolved upstream). Any non-REPORT_ONLY route is
    rejected: this renderer is report-only and never presents a scope as routable."""
    statuses = list(statuses or ())
    if not statuses:
        return []
    lines = [REPORT_ONLY_HEADER, "Scope verification status:"]
    for item in statuses:
        if item.get("route") not in SCOPE_ROUTES:
            raise ValueError("Unsupported scope route")
        detail = item.get("detail") or ""
        detail = f" [{detail}]" if detail and "/" not in detail else ""      # evidence paths stay in the archive
        lines.append(f"- {item.get('symbol', 'SCHEMA_GAP')}: {item.get('verification_status', 'SCHEMA_GAP')} | "
                     f"{item['route']} ({item.get('route_reason', 'SCHEMA_GAP')}){detail}")
    return lines


def render_crypto_strategy_summary(summary):
    """Render the crypto-strategy (BTCUSD/ETHUSD) window digest: per-instrument verification status
    and the latest archived outcome of each strategy source. Missing records render as NO_RECORD."""
    if summary.get("schema") != CRYPTO_STRATEGY_SUMMARY_SCHEMA:
        raise ValueError("Unsupported crypto strategy summary schema")
    session_date, session = summary.get("session_date"), summary.get("session")
    if not isinstance(session_date, str) or not session_date or not isinstance(session, str) or not session:
        raise ValueError("SCHEMA_GAP: session identity")
    lines = ["Crypto strategy summary -- INFORMATIONAL",
             f"Window: {session_date} / {session} "
             f"({value(summary, 'window_start_utc')} -> {value(summary, 'window_end_utc')})",
             f"Summary status: {value(summary, 'status')}"]
    lines += scope_status_lines(summary.get("scope_statuses"))
    lines.append("Latest outcomes:")
    for item in summary.get("per_instrument") or ():
        for label, key in (("CCFD", "ccfd"), ("RESEARCH", "research")):
            outcome = item.get(key) or {}
            reasons = ",".join(outcome.get("reason_codes") or []) or "-"
            lines.append(f"- {item.get('symbol', 'SCHEMA_GAP')} {label} {outcome.get('strategy', 'SCHEMA_GAP')}: "
                         f"{outcome.get('decision', 'NO_RECORD')} ({reasons})")
    lines.append(f"Delivery enabled: {str(bool(summary.get('delivery_enabled', False))).lower()}")
    lines.append("No broker order. Execution not authorized.")
    return "\n".join(lines)


def lsmc_diagnostic_lines(section):
    lines = []
    if section.get("config_missing"):
        lines.append("CONFIG_MISSING key=lsmc_min_remaining_reward_fraction")
    errors = section.get("archive_error_count", 0)
    if not isinstance(errors, int) or isinstance(errors, bool) or errors < 0:
        raise ValueError("Invalid Large-SMC archive error count")
    if errors:
        lines.append(f"ARCHIVE_ERROR n={errors}")
    return lines


def render_lsmc_crypto_summary(summary):
    """Render the Large-SMC crypto (BTCUSD/ETHUSD) window digest: opportunities sent and
    per-reason rejection counts. Zero counts are rendered, never omitted."""
    if summary.get("schema") != LSMC_CRYPTO_SUMMARY_SCHEMA:
        raise ValueError("Unsupported LSMC crypto summary schema")
    session_date, session = summary.get("session_date"), summary.get("session")
    if not isinstance(session_date, str) or not session_date or not isinstance(session, str) or not session:
        raise ValueError("SCHEMA_GAP: session identity")
    counts = {"evaluations": summary.get("evaluations"), "opportunities_sent": summary.get("opportunities_sent")}
    for key, count in counts.items():
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError(f"Invalid {key}")
    rejections = summary.get("rejection_counts") or {}
    lines = ["Large-SMC crypto watch summary -- INFORMATIONAL",
             f"Window: {session_date} / {session} "
             f"({value(summary, 'window_start_utc')} -> {value(summary, 'window_end_utc')})",
             f"Instruments: {', '.join(summary.get('instruments') or [])}",
             f"Evaluations: {counts['evaluations']}",
             f"Opportunities sent: {counts['opportunities_sent']}",
             "Rejections by reason:"]
    lines += [f"- {reason}: {n}" for reason, n in sorted(rejections.items())] or ["- none"]
    lines += lsmc_diagnostic_lines(summary.get("large_smc") or {})
    if counts["evaluations"] == 0:
        lines.append("NOTE: no evaluations recorded in this window (runner not running or no data); "
                     "not a market observation")
    lines.append(f"Delivery enabled: {str(bool(summary.get('delivery_enabled', False))).lower()}")
    lines.append("No broker order. Execution not authorized.")
    return "\n".join(lines)


REPORT_SCOPES = {"CANDIDATE": "REPORT_CANDIDATE", "BLOCKED": "REPORT_BLOCKED", "WATCH": "REPORT_WATCH"}
DAILY_REPORT_SUMMARY_SCHEMA = "AGP_HOST_DAILY_REPORT_SUMMARY_V1"


def report_identity(c):
    """Ledger identity of one observation: the per-signal id, else the scope/day ticket id + class + reason."""
    return c.get("candidate_signal_id") or "|".join(str(c.get(k)) for k in ("ticket_id", "report_class", "reason_code"))


def _r(c, key):
    value_r = (c.get("risk") or {}).get(key)
    return f"+{value_r:.2f}R" if isinstance(value_r, (int, float)) else "n/a"


_ASW_LEGS = {"tp1": "OPPOSITE_SESSION_BOUNDARY, 75%", "tp2": "FIXED_R_MULTIPLE_5, 25%"}


# Plain-English explanation of the most common blocking evidence gaps (reporting only).
BLOCK_EXPLANATIONS = {
    "C10_PIP_SIZE_NOT_EVIDENCED": "no verified pip size for this symbol; C10 stop not computed (owner input TQ-D3)",
    "MISSING_SPREAD": "no live spread; C10 SHORT stop not computed",
    "REJECT_NO_STOP": "no valid C10 stop",
    "REJECT_NO_TARGET": "no C11 liquidity target",
    "REJECT_STALE": "remaining reward below the owner threshold",
    "SUSPENDED_L3_REPAINT": "scope suspended for this strategy version (L3 repaint); not evaluated",
    "TARGET_ORDER_INVALID:FAIL_CLOSED_IF_TP1_BEYOND_TP2": "TP1 lies beyond TP2; the frozen contract fails closed",
    "INFO_ONLY_STALE": "signal older than its freshness window",
    "MISSED": "price already reached the stop or TP1",
    "EXPIRED": "trade window closed",
    "SPREAD_TOO_WIDE": "live spread above 15% of the stop distance (or the 2.0-pip cap)",
    "SCOPE_SUSPENDED": "scope suspended in the registry for this strategy version; observation only",
    "STALE": "market data or signal older than 15 minutes",
    "LOGIC_SCOPE_NOT_VERIFIED": "scope not logic-verified for this strategy version",
    "SCOPE_NOT_S1": "symbol/session is outside the S1 runtime scope (GBPUSD ASIAN_LONDON)",
    "SCOPE_IDENTITY_MISMATCH": "S1 contract or engine identity does not match the registry record",
    "BRANCH_OUTSIDE_VERIFIED_SCOPE": "engine emitted a branch outside the verified S1 RANGE_SWEEP scope",
    "SPREAD_NOT_EVALUATED": "no live spread available",
}


def render_cycle_status(c):
    """Compact ASCII S1 cycle status (AGP-S1-BLOCK-REASON-FIX-R1): decision, reason + detail, engine branch."""
    detail = c.get("engine_detail") or {}
    reason = str(c.get("reason_code") or "UNSPECIFIED")
    lines = [f"S1 CYCLE | {c.get('instrument')} {c.get('session')} | {c.get('session_date')}",
             f"decision: {c.get('decision')}",
             f"reason: {reason}" + (f" -- {BLOCK_EXPLANATIONS[reason]}" if reason in BLOCK_EXPLANATIONS else "")]
    source = detail.get("reason_code")
    if source and source != reason:
        lines.append(f"source reason: {source}"
                     + (f" -- {BLOCK_EXPLANATIONS[source]}" if source in BLOCK_EXPLANATIONS else ""))
    if detail.get("detail"):
        lines.append(f"detail: {detail['detail']}")
    if detail.get("regime") or detail.get("setup"):
        lines.append(f"engine: regime={detail.get('regime')} setup={detail.get('setup')}")
    lines += [f"evaluated: {c.get('created_at')}", "INFORMATIONAL -- NOT A BROKER ORDER | EXECUTION: DISABLED"]
    return "\n".join(lines).encode("ascii", "replace").decode("ascii")


def _blocked_lines(c):
    reasons = [str(r) for r in (c.get("reason_codes") or [c.get("reason_code")]) if r]
    primary = reasons[0] if reasons else "UNSPECIFIED"
    lines = [f"blocked by: {primary}" + (f" -- {BLOCK_EXPLANATIONS[primary]}" if primary in BLOCK_EXPLANATIONS else "")]
    if reasons[1:]:
        lines.append("also: " + ",".join(reasons[1:]))
    if c.get("notes"):
        lines.append("note: " + ",".join(str(n) for n in c["notes"]))
    return lines


def _broker_symbol(c):
    """MT5 broker symbol (e.g. GBPUSD-VIP) from the versioned canonical-to-broker map; canonical on failure."""
    sym = c.get("instrument")
    try:
        from mt5.canonical_broker_map import resolve
        return resolve(sym) if sym else "n/a"
    except Exception:  # noqa: BLE001 -- display only; never blocks a report
        return sym or "n/a"


def _report_ticket_lines(c, sym, direction, scope, ts, dist):
    """ASW / CCFD layout (owner example 2026-10-07 tickets), REPORT_ONLY header, never decision=READY."""
    prices = c.get("prices") or {}
    asw = c.get("strategy_id") == "ST_ASIAN_SWEEP_5R_V1"
    trigger = c.get("trigger") or {}
    lines = [f"{sym} {direction} ({value(c, 'session')})",
             f"{value(c, 'strategy_id')} v{value(c, 'strategy_version')}  report={value(c, 'report_class')}  {scope}",
             f"ticket_id: {c.get('ticket_id') or 'n/a'}"]
    if asw:
        lines.append(f"window: {value(c, 'session')} trade session  time invalidation 15:00 GMT")
    lines += [f"signal close: {ts(trigger.get('trigger_bar_close_utc'))}", f"expires_at: {ts(c.get('expires_at'))}"]
    if c.get("report_class") == "CANDIDATE":
        risk = (c.get("risk") or {}).get("risk_distance")
        lines.append(f"entry: {prices.get('entry_reference') or 'n/a'}  stop: {prices.get('sl') or 'n/a'}  "
                     f"risk: {dist(c.get('instrument'), risk) if isinstance(risk, (int, float)) else 'n/a'}")
        for leg, key, r_key in ((1, "tp1", "initial_R_tp1"), (2, "tp2", "initial_R_tp2")):
            if prices.get(key) is not None:
                label = f" ({_ASW_LEGS[key]})" if asw else ""
                lines.append(f"target leg {leg}{label}: {prices[key]}  = {_r(c, r_key)}")
        lines += _sizing_lines(c)
        lines += [f"guard: {v}" for v in c.get("guard_verdicts") or []]      # OD1014-FAST D4
        lines.append(f"data source: {c.get('venue') or 'n/a'}")
        lines.append(f"VALID UNTIL {ts(c.get('expires_at'))} -- STALE after; re-check before acting.")
    elif c.get("report_class") == "BLOCKED":
        lines += _blocked_lines(c)
        lines.append(f"data source: {c.get('venue') or 'n/a'}")
    else:
        lines.append(f"state: {value(c, 'reason_code')}")
    return lines


def _report_lsmc_lines(c, sym, direction, scope, ts, dist):
    """Large-SMC layout (owner example 2026-10-09 alerts), REPORT_ONLY header."""
    prices, lsmc = c.get("prices") or {}, c.get("lsmc") or {}
    to_state = str(c.get("transition") or "->").split("->")[-1] or "n/a"
    cls = value(c, "report_class")
    lines = [f"{sym} {to_state} ({cls})  direction: {direction}",
             f"{value(c, 'strategy_id')} v{value(c, 'strategy_version')}  economic_status=NOT_EVALUATED  {scope}",
             f"ref: {c.get('setup_id') or 'n/a'}",
             f"transition: {c.get('transition') or 'n/a'}",
             "timeframes: D1 context -> H1 bias + POI -> M5 sweep/CHoCH"]
    if lsmc.get("poi_low") and lsmc.get("poi_high"):
        lines.append(f"POI zone ({lsmc.get('poi_kind') or 'H1'}): {lsmc['poi_low']} - {lsmc['poi_high']}")
    if c.get("report_class") == "CANDIDATE":
        lines += [f"liquidity target: {prices.get('tp1') or 'n/a'}", f"stop (C10): {prices.get('sl') or 'n/a'}",
                  f"entry reference (CHoCH close): {prices.get('entry_reference') or 'n/a'}"]
        lines += _sizing_lines(c)
    elif c.get("report_class") == "BLOCKED":
        lines += _blocked_lines(c)
    if prices.get("current_send") is not None:
        lines.append(f"current price: {prices['current_send']}")
    if lsmc.get("distance_to_poi") is not None:
        lines.append("distance to POI: inside zone" if lsmc["distance_to_poi"] == 0
                     else f"distance to POI: {dist(c.get('instrument'), lsmc['distance_to_poi'])}")
    lines.append(f"expires_at: {ts(lsmc.get('expires_at'))}")
    return lines


def _sizing_lines(c):
    """OD1014 A3: display-only lot preview / cost-in-R, or `sizing: n/a (<reason>)`; never 0 or an estimate."""
    try:
        from reporting.sizing_preview import sizing_lines
        return sizing_lines(c)
    except Exception as exc:  # noqa: BLE001 -- display only; a fault omits the preview, never the report
        return [f"sizing: n/a (PREVIEW_FAILED:{type(exc).__name__})"]


def render_report(c):
    """ASCII REPORT_ONLY observation in the owner-approved ticket / Large-SMC alert layouts. Rejects any
    route other than REPORT_ONLY; shows the report class, never an executable decision."""
    if c.get("scope_route") != "REPORT_ONLY":
        raise ValueError("Unsupported scope route")
    from host_delivery.telegram_message import _dist, _ts
    sym, direction = _broker_symbol(c), c.get("direction") or "n/a"
    scope = f"scope={value(c, 'scope_verification_status')} ({value(c, 'scope_reason')})"
    build = _report_lsmc_lines if c.get("strategy_id") == "ST_LARGE_SMC_V1" else _report_ticket_lines
    lsmc = c.get("strategy_id") == "ST_LARGE_SMC_V1"
    lines = [report_header(c.get("report_class"), large_smc=lsmc,
                           verification_status=c.get("verification_status") or c.get("scope_verification_status"))]
    lines += build(c, sym, direction, scope, _ts, _dist)
    lines.append(f"evaluated: {_ts(c.get('created_at'))}")
    lines.append("REPORT ONLY - NOT AN ORDER | EXECUTION: DISABLED")
    return "\n".join(lines).encode("ascii", "replace").decode("ascii")


def render_daily_report_summary(summary):
    if summary.get("schema") != DAILY_REPORT_SUMMARY_SCHEMA:
        raise ValueError("Unsupported daily report summary schema")
    lines = [f"Daily strategy report -- REPORT ONLY -- {summary.get('session_date')}"]
    for family, row in sorted((summary.get("families") or {}).items()):
        counts = row.get("counts") or {}
        lines.append(f"{family}: " + (", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "no records"))
        if not counts.get("CANDIDATE"):
            lines.append(f"- {family}: NO OPPORTUNITY")
    lines.append(f"Delivery enabled: {str(bool(summary.get('delivery_enabled', False))).lower()}")
    lines.append("No broker order. Execution not authorized.")
    return "\n".join(lines)


def render_session_summary(summary):
    """Render one deterministic per-session digest from already-aggregated durable facts."""
    if summary.get("schema") != "AGP_HOST_TICKET_DELIVERY_R1_SESSION_SUMMARY_V1":
        raise ValueError("Unsupported session summary schema")
    session_date, session = summary.get("session_date"), summary.get("session")
    if not isinstance(session_date, str) or not session_date or not isinstance(session, str) or not session:
        raise ValueError("SCHEMA_GAP: session identity")
    expected, recorded = summary.get("expected_evaluations"), summary.get("recorded_evaluations")
    if not isinstance(expected, int) or isinstance(expected, bool) or expected < 0:
        raise ValueError("SCHEMA_GAP: expected_evaluations")
    if not isinstance(recorded, int) or isinstance(recorded, bool) or recorded < 0 or recorded > expected:
        raise ValueError("Invalid recorded_evaluations")
    terminal = summary.get("terminal_counts") or {}
    delivery = summary.get("delivery_counts") or {}
    lines = ["Canonical FX session summary -- INFORMATIONAL",
             f"Session: {session_date} / {session}",
             f"Durable evaluations: {recorded}/{expected}",
             f"Session status: {value(summary, 'status')}"]
    lines += scope_status_lines(summary.get("scope_statuses"))
    lines.append("Terminal outcomes:")
    nonzero = [(state, terminal.get(state, 0)) for state in sorted(STATUSES) if terminal.get(state, 0)]
    compatibility_count = summary.get("compatibility_error_count", terminal.get("COMPATIBILITY_ERROR", 0))
    if compatibility_count:
        nonzero.append(("COMPATIBILITY_ERROR", compatibility_count))
    lines += [f"- {state}: {count}" for state, count in nonzero] or ["- none recorded"]
    missed = list(summary.get("missed_pairs") or ())
    missed_count = summary.get("missed_count", len(missed))
    if not isinstance(missed_count, int) or isinstance(missed_count, bool) or missed_count < 0:
        raise ValueError("Invalid missed_count")
    lines.append(f"Missing scheduled evaluations (MISSED): {missed_count}")
    for item in missed:
        lines.append(f"- MISSED {item.get('symbol', 'SCHEMA_GAP')} | {item.get('reason_code', 'SCHEMA_GAP')}")
    out_of_session = list(summary.get("out_of_session_pairs") or ())
    lines.append(f"Out-of-session pairs: {len(out_of_session)}")
    for item in out_of_session:
        lines.append(f"- OUT_OF_SESSION {item.get('symbol', 'SCHEMA_GAP')} | "
                     f"{item.get('reason_code', 'SCHEMA_GAP')}")
    lines.append(f"Scope blocked: {summary.get('scope_blocked_count', 0)}")
    lines.append(f"Data failures: {summary.get('data_failure_count', 0)}")
    lines.append(f"Delivery enabled: {str(bool(summary.get('delivery_enabled', False))).lower()}")
    lines.append(f"TICKET_STORE persistence failures: {summary.get('persistence_failure_count', 0)}")
    lines.append(f"Compatibility errors: {summary.get('compatibility_error_count', 0)}")
    for label, key in (("SUCCEEDED", "succeeded"), ("FAILED", "failed"),
                       ("UNCERTAIN", "uncertain"), ("DISABLED", "disabled"),
                       ("BLOCKED", "blocked"), ("SUMMARY_ONLY", "summary_only"),
                       ("PERSISTENCE_FAILED", "persistence_failed"), ("NOT_ATTEMPTED", "not_attempted")):
        count = delivery.get(key, 0)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError(f"Invalid delivery count {key}")
        lines.append(f"Delivery {label}: {count}")
    uncertain = list(summary.get("uncertain_deliveries") or ())
    if uncertain:
        lines.append("Possibly undelivered (no automatic retry):")
        for item in sorted(uncertain, key=lambda x: (str(x.get("identity", "")), str(x.get("status", "")))):
            lines.append(f"- {item.get('identity', 'SCHEMA_GAP')} | {item.get('status', STATE_UNCERTAIN)}")
    if "large_smc" in summary:
        counts = summary["large_smc"]["rejection_counts"]
        lines.append("Large-SMC rejections (archived transitions):")
        lines += lsmc_diagnostic_lines(summary["large_smc"])
        for reason in ("REJECT_NO_STOP", "REJECT_NO_TARGET", "REJECT_STALE"):
            count = counts[reason]
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise ValueError("Invalid Large-SMC rejection count")
            lines.append(f"- {reason}: {count}")
    lines.append("EXECUTION: DISABLED")
    return "\n".join(lines)


@dataclass(frozen=True)
class Config:
    enabled: bool = False
    token: str = ""
    chat_id: str = ""
    owner_chat_ids: frozenset[str] = frozenset()
    # C16 (OWNER_DECISION_REGISTER, PENDING_OWNER): WATCH_READY and non-suppressed INFO_ONLY_*
    # are informational. They are sent (scheduled or owner-resent) only when this default-OFF
    # flag is explicitly enabled; otherwise they stay archive/summary-only.
    watch_info_scope: bool = False
    immediate_scopes: frozenset[str] = frozenset()
    scope_error: str | None = None

    @classmethod
    def from_env(cls, root="."):
        scope = resolve_immediate_scope(root, sender="canonical")
        return cls(os.getenv("TELEGRAM_DELIVERY_ENABLED", "false").lower() == "true",
                   os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
                   os.getenv("TELEGRAM_CHAT_ID", "").strip(),
                   frozenset(x.strip() for x in os.getenv("TELEGRAM_OWNER_CHAT_IDS", "").split(",") if x.strip()),
                   immediate_scopes=frozenset(scope["effective"]), scope_error=scope["error"])


def bot_api(token, chat_id, message):
    """Use monospace HTML; fallback only after an explicit HTML-format rejection.

    A timeout/reset may follow acceptance and must propagate to the durable journal.
    Never try a fallback for ambiguous transport failures or unrelated API errors.
    """
    def post(text, parse_mode=None):
        payload = {"chat_id": chat_id, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=15) as response:
            result = json.load(response)
        if result.get("ok") is not True:
            raise TelegramAPIError(result.get("error_code", "UNKNOWN"))
        sent_message = result.get("result") or {}
        message_id = sent_message.get("message_id")
        if message_id is None:
            raise TelegramAPIError("MISSING_MESSAGE_ID")
        return {"ok": True, "message_id": message_id,
                "chat_id": (sent_message.get("chat") or {}).get("id", chat_id)}

    try:
        return post("<pre>" + html.escape(message, quote=False) + "</pre>", "HTML")
    except TelegramAPIError as error:
        if error.error_code != "400":
            raise
        LOG.warning("Telegram HTML rejected; falling back to plain text")
        return post(message)
    except urllib.error.HTTPError as error:
        # Telegram explicitly rejects malformed/unsupported HTML with HTTP 400.
        # Do not downgrade authorization, chat, length, rate-limit or server errors.
        description = ""
        if error.code == 400 and error.fp is not None:
            try:
                description = json.loads(error.read()).get("description", "").lower()
            except (ValueError, TypeError, AttributeError):
                pass
        if error.code != 400 or not any(term in description for term in (
                "can't parse entities", "cannot parse entities", "unsupported start tag",
                "parse_mode", "parse mode")):
            raise
        LOG.warning("Telegram HTML rejected; falling back to plain text")
        return post(message)


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


class Sender:
    def __init__(self, store_path, config=None, transport=bot_api, sleep=time.sleep, attempts=3):
        if str(store_path) == ":memory:":
            raise ValueError("Persistent dedupe store required")
        if not 1 <= attempts <= 5:
            raise ValueError("attempts must be 1..5")
        self.path = Path(store_path)
        self.config = config if config is not None else Config.from_env()
        self.transport, self.sleep, self.attempts = transport, sleep, attempts
        self.require_api_receipt = transport is bot_api or bool(getattr(transport, "returns_telegram_receipt", False))

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=15)
        db.execute("CREATE TABLE IF NOT EXISTS sent (kind TEXT, identity TEXT, status TEXT, "
                   "state TEXT, actor TEXT, updated_at TEXT, error_class TEXT, "
                   "PRIMARY KEY(kind, identity, status))")
        cols = {row[1] for row in db.execute("PRAGMA table_info(sent)")}
        if "error_class" not in cols:
            db.execute("ALTER TABLE sent ADD COLUMN error_class TEXT")
        if "actor" not in cols:
            db.execute("ALTER TABLE sent ADD COLUMN actor TEXT")
        if "updated_at" not in cols:
            db.execute("ALTER TABLE sent ADD COLUMN updated_at TEXT")
        for column in ("message_id", "chat_suffix", "result_error_code"):
            if column not in cols:
                db.execute(f"ALTER TABLE sent ADD COLUMN {column} TEXT")
        db.execute(
            "CREATE TABLE IF NOT EXISTS compatibility_errors ("
            "kind TEXT NOT NULL, identity TEXT NOT NULL, error_code TEXT NOT NULL, "
            "observed_decision TEXT NOT NULL, expected_decisions TEXT NOT NULL, created_at TEXT NOT NULL, "
            "PRIMARY KEY(kind, identity, observed_decision))"
        )
        return db

    def _record_compatibility_error(self, ticket):
        decision = ticket.get("decision")
        observed = str(decision)[:120] if decision is not None else "<missing>"
        identity = ticket.get("ticket_id")
        if not isinstance(identity, str) or not identity:
            identity = "unkeyed:" + hashlib.sha256(
                json.dumps(ticket, sort_keys=True, separators=(",", ":"), default=str).encode()
            ).hexdigest()
        expected = json.dumps(sorted(STATUSES), separators=(",", ":"))
        try:
            with self._connect() as db:
                db.execute(
                    "INSERT OR IGNORE INTO compatibility_errors "
                    "(kind, identity, error_code, observed_decision, expected_decisions, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    ("ticket", identity, "UNKNOWN_CANONICAL_DECISION", observed, expected, _utc_now()),
                )
            LOG.error("Canonical delivery compatibility error: UNKNOWN_CANONICAL_DECISION identity=%s", identity)
            return "compatibility_error"
        except (OSError, sqlite3.Error):
            LOG.error("Canonical compatibility diagnostic persistence failed; delivery stopped")
            return "compatibility_error_unpersisted"

    def compatibility_errors(self):
        if not self.path.exists():
            return []
        with self._connect() as db:
            rows = db.execute(
                "SELECT kind, identity, error_code, observed_decision, expected_decisions, created_at "
                "FROM compatibility_errors ORDER BY created_at, identity"
            ).fetchall()
        return [{"kind": kind, "identity": identity, "error_code": code,
                 "observed_decision": observed, "expected_decisions": json.loads(expected),
                 "created_at": created}
                for kind, identity, code, observed, expected, created in rows]

    @contextmanager
    def _key_lock(self, kind, identity, status):
        # A separate SQLite lock per key serializes retries/recovery of that key,
        # without blocking unrelated tickets in the main journal during network I/O.
        directory = Path(str(self.path) + ".locks")
        directory.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(json.dumps([kind, identity, status]).encode()).hexdigest()
        lock = sqlite3.connect(directory / (key + ".sqlite"), timeout=0)
        try:
            try:
                lock.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError as error:
                if error.sqlite_errorcode in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                    raise DeliveryInProgress from error
                raise
            yield
        finally:
            lock.rollback()
            lock.close()

    @staticmethod
    def _recover_pending(db, kind, identity, status):
        # Caller holds the key lock: a surviving pending claim has no active sender.
        db.execute("UPDATE sent SET state=?, updated_at=?, error_class=? "
                   "WHERE kind=? AND identity=? AND status=? AND state=?",
                   (STATE_UNCERTAIN, _utc_now(), "InterruptedSend", kind, identity,
                    status, STATE_PENDING))

    def list_uncertain(self):
        if not self.path.exists():
            return []
        with self._connect() as db:
            rows = db.execute("SELECT kind, identity, status FROM sent WHERE state=?",
                              (STATE_PENDING,)).fetchall()
            for kind, identity, status in rows:
                try:
                    with self._key_lock(kind, identity, status):
                        self._recover_pending(db, kind, identity, status)
                        db.commit()
                except DeliveryInProgress:
                    continue  # An active request is not a crash-left pending claim.
            rows = db.execute(
                "SELECT kind, identity, status, error_class FROM sent WHERE state=?",
                (STATE_UNCERTAIN,),
            ).fetchall()
        return [{"kind": k, "identity": i, "status": s, "error_class": e} for k, i, s, e in rows]

    def delivery_attempts(self, kind, identities=()):
        """Read durable attempt state without creating a journal or exposing credentials."""
        if not self.path.exists():
            return []
        identities = tuple(sorted(set(identities)))
        with self._connect() as db:
            if identities:
                marks = ",".join("?" for _ in identities)
                rows = db.execute(
                    f"SELECT identity, status, state, error_class, updated_at, message_id, chat_suffix, "
                    f"result_error_code FROM sent "
                    f"WHERE kind=? AND identity IN ({marks}) ORDER BY identity, status",
                    (kind, *identities),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT identity, status, state, error_class, updated_at, message_id, chat_suffix, "
                    "result_error_code FROM sent "
                    "WHERE kind=? ORDER BY identity, status", (kind,)
                ).fetchall()
        return [{"identity": i, "status": s, "state": state, "error_class": error, "updated_at": at,
                 "message_id": message_id, "chat_suffix": chat_suffix,
                 "result_error_code": result_error_code}
                for i, s, state, error, at, message_id, chat_suffix, result_error_code in rows]

    def _send(self, kind, identity, status, message, *, force=False, actor="", allow_duplicate=False):
        cfg = self.config
        if not cfg.enabled:
            LOG.info("Telegram delivery disabled")
            return "disabled"
        if not cfg.token.strip() or not cfg.chat_id.strip() or cfg.chat_id not in cfg.owner_chat_ids:
            LOG.error("Telegram delivery blocked: missing credentials or owner allowlist")
            return "blocked"
        # Bot API limit is UTF-16 code units. Never truncate or split a session.
        if len(message.encode("utf-16-le")) // 2 > 4096:
            LOG.error("Telegram delivery blocked: message exceeds 4096 units")
            return "blocked"
        try:
            with self._key_lock(kind, identity, status), self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                self._recover_pending(db, kind, identity, status)
                row = db.execute("SELECT state FROM sent WHERE kind=? AND identity=? AND status=?",
                                 (kind, identity, status)).fetchone()
                if row:
                    if force and row[0] in (STATE_UNCERTAIN, STATE_FAILED):
                        LOG.info("Owner force resend actor=%s when=%s identity=%s",
                                 actor or "unspecified", _utc_now(), identity)
                    elif force and row[0] in DELIVERED_STATES and allow_duplicate:
                        LOG.info("Owner allow-duplicate resend actor=%s when=%s identity=%s",
                                 actor or "unspecified", _utc_now(), identity)
                    elif force:
                        LOG.error("Force resend refused: state=%s identity=%s actor=%s when=%s",
                                  row[0], identity, actor or "unspecified", _utc_now())
                        return "refused"
                    else:
                        LOG.info("DUPLICATE_SUPPRESSED kind=%s identity=%s state=%s",
                                 kind, identity, row[0])
                        return "duplicate"
                else:
                    if force:
                        LOG.error("Force resend refused: no UNCERTAIN claim identity=%s actor=%s",
                                  identity, actor or "unspecified")
                        return "refused"
                    # Durable claim before network: a crash/ambiguous timeout cannot resend on restart.
                    db.execute(
                        "INSERT INTO sent (kind, identity, status, state, actor, updated_at, error_class) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (kind, identity, status, STATE_PENDING, actor, _utc_now(), None),
                    )
                # Commit both new claims and forced-resend claims before network.
                if force:
                    db.execute("UPDATE sent SET state=?, actor=?, updated_at=?, error_class=NULL "
                               "WHERE kind=? AND identity=? AND status=?",
                               (STATE_PENDING, actor, _utc_now(), kind, identity, status))
                db.commit()
                for attempt in range(self.attempts):
                    try:
                        response = self.transport(cfg.token, cfg.chat_id, message)
                        message_id = response.get("message_id") if isinstance(response, dict) else None
                        if self.require_api_receipt and (message_id is None or response.get("ok") is not True):
                            code = (response.get("error_code", "INVALID_SUCCESS_RESPONSE")
                                    if isinstance(response, dict) else "MISSING_MESSAGE_ID")
                            db.execute("UPDATE sent SET state=?, updated_at=?, error_class=?, result_error_code=? "
                                       "WHERE kind=? AND identity=? AND status=?",
                                       (STATE_FAILED, _utc_now(), "TelegramAPIError", str(code), kind, identity, status))
                            db.commit()
                            return "failed"
                        response_chat = (response.get("chat_id", cfg.chat_id)
                                         if isinstance(response, dict) else cfg.chat_id)
                        db.execute("UPDATE sent SET state=?, actor=?, updated_at=?, error_class=? "
                                   "WHERE kind=? AND identity=? AND status=?",
                                   (STATE_DELIVERED, actor, _utc_now(), None, kind, identity, status))
                        db.execute("UPDATE sent SET message_id=?, chat_suffix=?, result_error_code=NULL "
                                   "WHERE kind=? AND identity=? AND status=?",
                                   (str(message_id) if message_id is not None else None,
                                    str(response_chat)[-4:] if message_id is not None else None,
                                    kind, identity, status))
                        db.commit()
                        return "sent"
                    except urllib.error.HTTPError as error:
                        LOG.error("Telegram HTTP failure: status=%s attempt=%s", error.code, attempt + 1)
                        db.execute("UPDATE sent SET result_error_code=? WHERE kind=? AND identity=? AND status=?",
                                   (str(error.code), kind, identity, status))
                        db.execute("UPDATE sent SET result_error_code=? WHERE kind=? AND identity=? AND status=?",
                                   (str(error.code), kind, identity, status))
                        # A 5xx may follow acceptance: preserve ambiguity without another send.
                        if error.code >= 500:
                            db.execute("UPDATE sent SET state=?, updated_at=?, error_class=? "
                                       "WHERE kind=? AND identity=? AND status=?",
                                       (STATE_UNCERTAIN, _utc_now(), "HTTPError", kind, identity, status))
                            db.commit()
                            return "uncertain"
                        if error.code != 429 or attempt + 1 == self.attempts:
                            break
                        self.sleep(2 ** attempt)
                    except TelegramAPIError as error:
                        db.execute("UPDATE sent SET state=?, updated_at=?, error_class=?, result_error_code=? "
                                   "WHERE kind=? AND identity=? AND status=?",
                                   (STATE_FAILED, _utc_now(), type(error).__name__, error.error_code,
                                    kind, identity, status))
                        db.commit()
                        return "failed"
                    except Exception as error:
                        # Persist only a safe type code; token-bearing URLs and exception bodies stay private.
                        LOG.error("Telegram delivery ambiguous; automatic resend suppressed")
                        code = "TIMEOUT" if isinstance(error, TimeoutError) else type(error).__name__.upper()
                        db.execute("UPDATE sent SET state=?, actor=?, updated_at=?, error_class=?, result_error_code=? "
                                   "WHERE kind=? AND identity=? AND status=?",
                                   (STATE_UNCERTAIN, actor, _utc_now(), type(error).__name__, code,
                                    kind, identity, status))
                        db.commit()
                        return "uncertain"
                db.execute("UPDATE sent SET state=?, updated_at=?, error_class=? "
                           "WHERE kind=? AND identity=? AND status=?",
                           (STATE_FAILED, _utc_now(), "HTTPError", kind, identity, status))
                db.commit()
                return "failed"
        except DeliveryInProgress:
            LOG.info("Telegram dedupe: delivery already in progress")
            return "duplicate"
        except (OSError, sqlite3.Error):
            LOG.error("Telegram dedupe persistence failure; delivery stopped")
            return "failed"

    def send_ticket(self, ticket):
        # The canonical store is written upstream before this router is called. Unknown taxonomy
        # values fail closed and leave a durable compatibility diagnostic in this adapter journal.
        if not _known_decision(ticket.get("decision")):
            return self._record_compatibility_error(ticket)
        validate(ticket)
        if self.config.scope_error:
            LOG.error("Telegram scope rejected: %s", self.config.scope_error)
            return "blocked"
        # The authority-suppressed READY is durable but must never become an immediate alert.
        if ticket["decision"] == "INFO_ONLY_SUPPRESSED":
            return "summary_only"
        # Other INFO_ONLY states remain explicitly informational (the renderer stamps execution
        # disabled); terminal non-alert decisions are visible through the session summary only.
        if ticket["decision"] != "WATCH_READY" and not ticket["decision"].startswith("INFO_ONLY_"):
            return "summary_only"
        if self.config.immediate_scopes and ticket["decision"] not in self.config.immediate_scopes:
            return "summary_only"
        # Same C16 scope flag as owner resend: informational states stay summary-only unless enabled.
        if not self.config.watch_info_scope:
            return "summary_only"
        return self._send("ticket", ticket["ticket_id"], ticket["decision"], render_ticket(ticket))

    def send_cycle_status(self, ticket):
        """AGP-S1-BLOCK-REASON-FIX-R1: one compact ASCII status per scheduled S1 cycle that produced no
        alert (BLOCKED / NO_TRADE / any non-alert decision), so no S1 session is ever summary-only.
        Informational only; deduped per (ticket, decision, reason) by `_send`."""
        if not _known_decision(ticket.get("decision")):
            return self._record_compatibility_error(ticket)
        validate(ticket)
        if self.config.scope_error:
            LOG.error("Telegram scope rejected: %s", self.config.scope_error)
            return "blocked"
        status = f"{ticket['decision']}|{ticket.get('reason_code')}"
        return self._send("cycle", ticket["ticket_id"], status, render_cycle_status(ticket))

    def send_summary(self, tickets):
        tickets = list(tickets)
        message = render_summary(tickets, uncertain=self.list_uncertain())
        if not tickets:
            raise ValueError("Session identity requires at least one ticket")
        identity = json.dumps([tickets[0]["session_date"], tickets[0]["session"]], separators=(",", ":"))
        return self._send("session", identity, "", message)

    def send_report(self, canonical):
        """AGP-C18-R2: one REPORT_ONLY observation (OD1013-C18-REPORT-SCOPE). Sent only when its scope
        REPORT_<class> is in the effective tracked scope; an empty scope set fails closed."""
        report_class = canonical.get("report_class")
        if canonical.get("scope_route") != "REPORT_ONLY" or report_class not in REPORT_SCOPES:
            return "summary_only"
        if REPORT_SCOPES[report_class] not in self.config.immediate_scopes:
            return "summary_only"
        identity = report_identity(canonical)
        if identity == canonical.get("candidate_signal_id") and self._signal_already_reported(canonical, identity):
            return "duplicate"
        return self._send("report", identity, report_class, render_report(canonical))

    def _signal_already_reported(self, canonical, identity):
        """One message per signal (OD1014-FAST D4, C22 E2). Prior per-signal reports count when sent, pending
        or uncertain (failed attempts don't). Same class repeats are deduped by `_send` itself. Across classes
        the only send allowed is exactly ONE upgrade BLOCKED -> CANDIDATE while the signal is still fresh;
        every other change (CANDIDATE -> anything, a stale CANDIDATE after BLOCKED) is a duplicate."""
        report_class = canonical.get("report_class")
        live = DELIVERED_STATES | {STATE_PENDING, STATE_UNCERTAIN}
        prior = {row.get("status") for row in self.delivery_attempts("report", [identity])
                 if row.get("state") in live and row.get("status") != report_class}
        if not prior:
            return False
        return not (report_class == "CANDIDATE" and prior == {"BLOCKED"} and self._fresh_signal(canonical))

    @staticmethod
    def _fresh_signal(canonical):
        """Fresh = the observation's own freshness verdict passed and it is not STALE/MISSED/EXPIRED."""
        return ((canonical.get("freshness") or {}).get("status") == "PASS"
                and canonical.get("decision") not in ("STALE", "INFO_ONLY_STALE", "MISSED", "EXPIRED")
                and not {"STALE_SIGNAL", "INFO_ONLY_STALE", "MISSED", "EXPIRED"}
                & set(canonical.get("reason_codes") or []))

    def send_session_summary(self, summary):
        schema = summary.get("schema")
        message = (render_lsmc_crypto_summary(summary) if schema == LSMC_CRYPTO_SUMMARY_SCHEMA
                   else render_crypto_strategy_summary(summary) if schema == CRYPTO_STRATEGY_SUMMARY_SCHEMA
                   else render_daily_report_summary(summary) if schema == DAILY_REPORT_SUMMARY_SCHEMA
                   else render_session_summary(summary))
        identity = json.dumps([summary["session_date"], summary["session"]], separators=(",", ":"))
        return self._send("session_summary", identity, "AGP_HOST_TICKET_DELIVERY_R1", message)

    def resend_ticket(self, ticket, *, force, actor, allow_duplicate=False):
        if not force:
            raise ValueError("owner-invoked --force required")
        if not actor or not str(actor).strip():
            raise ValueError("owner actor is an audit label and is required")
        cfg = self.config
        if not cfg.enabled or cfg.chat_id not in cfg.owner_chat_ids:
            LOG.error("Telegram force resend refused: not owner-invoked")
            return "blocked"
        if not _known_decision(ticket.get("decision")):
            return self._record_compatibility_error(ticket)
        validate(ticket)
        if cfg.scope_error:
            LOG.error("Telegram scope rejected: %s", cfg.scope_error)
            return "blocked"
        if ticket["decision"] == "INFO_ONLY_SUPPRESSED":
            return "summary_only"
        if ticket["decision"] != "WATCH_READY" and not ticket["decision"].startswith("INFO_ONLY_"):
            return "summary_only"
        if _informational_scope(ticket["decision"]) and not cfg.watch_info_scope:
            LOG.error("Telegram force resend refused: C16 informational scope not enabled")
            return "SCOPE_NOT_ENABLED"
        if cfg.immediate_scopes and ticket["decision"] not in cfg.immediate_scopes:
            LOG.error("Telegram force resend refused: decision is outside tracked immediate scope")
            return "SCOPE_NOT_ENABLED"
        LOG.info("Force resend requested actor=%s when=%s ticket_id=%s allow_duplicate=%s",
                 actor, _utc_now(), ticket["ticket_id"], allow_duplicate)
        return self._send("ticket", ticket["ticket_id"], ticket["decision"],
                          render_ticket(ticket), force=True, actor=actor,
                          allow_duplicate=allow_duplicate)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="telegram_delivery")
    sub = parser.add_subparsers(dest="command", required=True)
    resend = sub.add_parser("resend", help="Owner-only forced resend of an uncertain ticket")
    resend.add_argument("--ticket-id", required=True)
    resend.add_argument("--force", action="store_true")
    resend.add_argument("--store", required=True)
    resend.add_argument("--ticket-file", required=True, help="JSON object or array containing the ticket")
    resend.add_argument("--actor", default=os.getenv("USER", "owner"),
                        help="Audit label only; not authentication")
    resend.add_argument("--allow-duplicate", action="store_true",
                        help="Permit force resend when state is already DELIVERED")
    args = parser.parse_args(argv)
    payload = json.loads(Path(args.ticket_file).read_text())
    tickets = payload if isinstance(payload, list) else [payload]
    ticket = next((t for t in tickets if t.get("ticket_id") == args.ticket_id), None)
    if ticket is None:
        raise SystemExit("ticket-id not found")
    result = Sender(args.store).resend_ticket(
        ticket, force=args.force, actor=args.actor, allow_duplicate=args.allow_duplicate)
    print(result)
    return result


if __name__ == "__main__":
    main()
