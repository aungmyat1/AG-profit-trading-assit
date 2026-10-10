"""Host orchestration for canonical read-only FX evaluation and ticket delivery.

The scheduled caller supplies the accepted MT5 candle provider after its existing Demo-account
check. This module only composes that provider, daily_evaluator, TICKET_STORE_V1 and the
message-only adapter. Missing host/data prerequisites are persisted as REPLAY/NONE failure
records; no offline failure is mislabeled LIVE. No strategy rules or broker APIs are imported.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import yaml

from telegram_delivery.adapter import Config, Sender
from telegram_delivery.scope_policy import resolve as resolve_immediate_scope
from ticket_store.store import SCHEMA_EVALUATION, TicketStore, evaluation_id, read_jsonl
from v1_tickets.actionability import (
    BLOCKED, EXPIRED, INFO_ONLY_INSUFFICIENT_REMAINING_R, INFO_ONLY_POLICY_UNRESOLVED,
    INFO_ONLY_STALE, INFO_ONLY_SUPPRESSED, INSUFFICIENT_DATA, MISSED, NO_TRADE,
    OUT_OF_SESSION, WATCH_READY,
)
from v1_tickets.daily_evaluator import EvalResult, run_daily_evaluation
from v1_tickets.fx import V1_CYCLES, V1_FX_SYMBOLS, session_windows_utc

UTC = dt.timezone.utc
EVENT_SCHEMA = "AGP_HOST_TICKET_DELIVERY_R1_EVENT_V1"
SUMMARY_SCHEMA = "AGP_HOST_TICKET_DELIVERY_R1_SESSION_SUMMARY_V1"
START_SCHEMA = "AGP_HOST_TICKET_DELIVERY_R1_SCHEDULER_START_V1"
EVENT_SUBDIR = os.path.join("ticket_delivery", "canonical_fx", "sessions")
DELIVERY_DB = os.path.join("ticket_delivery", "canonical_fx", "delivery.sqlite")
SCHEDULER_START = os.path.join("ticket_delivery", "canonical_fx", "scheduler_start.json")
CANONICAL_OVERRIDE = "config/local/canonical_ticket_delivery.yaml"   # gitignored host-local recipient authorization
SUMMARY_GRACE = dt.timedelta(minutes=30)
CANONICAL_DECISIONS = frozenset({
    WATCH_READY, INFO_ONLY_STALE, INFO_ONLY_INSUFFICIENT_REMAINING_R,
    INFO_ONLY_POLICY_UNRESOLVED, INFO_ONLY_SUPPRESSED, NO_TRADE, EXPIRED,
    MISSED, BLOCKED, INSUFFICIENT_DATA, OUT_OF_SESSION,
})


def _known_canonical_decision(value: Any) -> bool:
    return isinstance(value, str) and value in CANONICAL_DECISIONS


class HostAcquisitionFailure(RuntimeError):
    """Explicit host prerequisite failure with a safe machine-readable reason code."""
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail[:300]


def _utc(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def active_cycles(now: dt.datetime, cycle_filter: Optional[str] = None) -> Tuple[str, ...]:
    """Only run a frozen cycle while its existing UTC trade window or 30-minute grace is open."""
    if cycle_filter is not None and cycle_filter not in V1_CYCLES:
        raise ValueError(f"unknown FX cycle {cycle_filter!r}")
    now = _utc(now)
    windows = session_windows_utc(now.date())
    return tuple(cycle for cycle in V1_CYCLES
                 if (cycle_filter is None or cycle == cycle_filter)
                 and windows[cycle]["trade"][0] <= now <= windows[cycle]["trade"][1] + SUMMARY_GRACE)


def build_sender(journal: str, *, root: str, transport=None, sleep=None) -> Sender:
    """Require both explicit local recipient authorization and the environment feature gate.

    The committed ticket_delivery.yaml remains ARCHIVE_ONLY. The local override is gitignored;
    absent/malformed override, disabled environment flag, missing credentials, or recipient
    mismatch all produce a disabled Sender. Tests inject a fake transport and never use Telegram.
    """
    env_enabled = os.getenv("TELEGRAM_DELIVERY_ENABLED", "false").strip().lower() == "true"
    env_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    env_chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    env_allow = frozenset(part.strip() for part in os.getenv("TELEGRAM_OWNER_CHAT_IDS", "").split(",")
                          if part.strip())
    local_path = Path(root) / CANONICAL_OVERRIDE
    scope = resolve_immediate_scope(root, sender="canonical")
    watch_info_flag = False
    try:
        raw = yaml.safe_load(local_path.read_text(encoding="utf-8")) or {}
        mode = raw.get("mode") if isinstance(raw, dict) else None
        # C16 informational scope (WATCH_READY / INFO_ONLY_*): default OFF, must be explicitly true.
        watch_info_flag = isinstance(raw, dict) and raw.get("watch_info_scope") is True
        local_ids_raw = raw.get("authorized_chat_ids") if isinstance(raw, dict) else None
        if not isinstance(local_ids_raw, list) or any(not isinstance(item, (str, int)) for item in local_ids_raw):
            local_ids = frozenset()
        else:
            local_ids = frozenset(str(item).strip() for item in local_ids_raw if str(item).strip())
    except (OSError, ValueError, yaml.YAMLError):
        mode, local_ids = None, frozenset()
    authorized = (mode == "MESSAGE_DELIVERY" and env_enabled and bool(env_token and env_chat)
                  and env_chat in env_allow and env_chat in local_ids)
    config = Config(enabled=authorized, token=env_token if authorized else "",
                    chat_id=env_chat if authorized else "",
                    owner_chat_ids=(env_allow & local_ids) if authorized else frozenset(),
                    watch_info_scope=bool(authorized and watch_info_flag),
                    immediate_scopes=frozenset(scope["effective"]), scope_error=scope["error"])
    kwargs = {"config": config}
    if transport is not None:
        kwargs["transport"] = transport
    if sleep is not None:
        kwargs["sleep"] = sleep
    return Sender(os.path.join(journal, DELIVERY_DB), **kwargs)


def _session_event_path(journal: str, session_date: str, session: str) -> str:
    try:
        dt.date.fromisoformat(session_date)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid session_date") from exc
    if session not in V1_CYCLES:
        raise ValueError(f"unknown FX cycle {session!r}")
    return os.path.join(journal, EVENT_SUBDIR, f"{session_date}_{session}.jsonl")


def append_session_event(journal: str, event: Dict[str, Any]) -> bool:
    """Append one sanitized, checksummed session event; exact duplicate event IDs are no-ops."""
    event = dict(event)
    event.setdefault("schema", EVENT_SCHEMA)
    session_date, session = event.get("session_date"), event.get("session")
    path = _session_event_path(journal, session_date, session)
    event_id = hashlib.sha256(json.dumps(event, sort_keys=True, separators=(",", ":"),
                               default=str).encode()).hexdigest()
    record = {**event, "event_id": event_id}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        if any(row.get("event_id") == event_id for _, row in read_jsonl(path)):
            return False
    with open(path, "a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, sort_keys=True, separators=(",", ":"), default=str) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return True


def failure_provider(code: str, detail: str):
    def provider(_symbol: str, _cycle: str, _day: dt.date, _now: dt.datetime):
        raise HostAcquisitionFailure(code, detail)
    return provider


def _store_status(result: EvalResult, verified: Optional[bool] = None) -> str:
    if result.ticket_store_error is not None or result.ticket_store_written is None or verified is False:
        return "FAILED"
    return "VERIFIED" if verified is True else ("WRITTEN" if result.ticket_store_written else "ALREADY_PRESENT")


def _verify_persisted_result(journal: str, result: EvalResult, ticket_source: str) -> bool:
    """Verify the exact durable TICKET_STORE_V1 row and its canonical-content digest."""
    canonical = result.canonical
    strategy = f"{canonical.get('strategy_id')}@{canonical.get('strategy_version')}"
    evaluated_at = canonical.get("created_at")
    if not isinstance(evaluated_at, str) or not evaluated_at:
        return False
    identity = {"strategy": strategy, "symbol": result.instrument, "session": result.session,
                "evaluated_at_utc": evaluated_at, "source": ticket_source}
    wanted_id = evaluation_id(identity)
    store = TicketStore(os.path.join(journal, "ticket_store"))
    path = os.path.join(store.evaluations_dir, f"{evaluated_at[:10]}.jsonl")
    from v1_tickets.canonical_ticket import canonical_hash
    expected_canonical_hash = canonical_hash(canonical)
    for _, record in read_jsonl(path):
        if record.get("evaluation_id") != wanted_id:
            continue
        payload = {key: value for key, value in record.items() if key != "record_sha256"}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                         default=str).encode()).hexdigest()
        provenance = record.get("provenance") or {}
        return (
            record.get("schema") == SCHEMA_EVALUATION
            and record.get("record_sha256") == digest
            and record.get("ticket_id") == result.ticket_id
            and record.get("strategy") == strategy
            and record.get("source") == ticket_source
            and record.get("symbol") == result.instrument
            and record.get("session") == result.session
            and record.get("evaluated_at_utc") == evaluated_at
            and record.get("state") == result.decision
            and provenance.get("canonical_hash") == expected_canonical_hash
        )
    return False


def _event_for_result(result: EvalResult, now: dt.datetime, *, stage: str, delivery_state: str,
                      ticket_source: str, error_class: Optional[str] = None,
                      store_status: Optional[str] = None,
                      store_error_class: Optional[str] = None) -> Dict[str, Any]:
    ticket = result.canonical
    ticket_id = result.ticket_id
    session_date = ticket.get("session_date") or ticket_id.rsplit("|", 1)[-1]
    data_error = ticket.get("data_error") or {}
    return {
        "event_type": "TICKET_DELIVERY", "stage": stage,
        "recorded_at_utc": _utc(now).isoformat(),
        "evaluated_at_utc": ticket.get("created_at"),
        "session_date": session_date, "session": result.session,
        "symbol": result.instrument, "ticket_id": ticket_id,
        "decision": result.decision, "reason_code": ticket.get("reason_code"),
        "compatibility_error_code": (None if _known_canonical_decision(result.decision)
                                      else "UNKNOWN_CANONICAL_DECISION"),
        "acquisition_error_code": data_error.get("code"),
        "ticket_store_status": store_status or _store_status(result),
        "ticket_store_error_class": (store_error_class or
                                     (result.ticket_store_error.split(":", 1)[0]
                                      if result.ticket_store_error else None)),
        "venue": result.venue, "source": ticket_source,
        "delivery_state": delivery_state, "delivery_error_class": error_class,
        "execution_authorized": False,
    }


def run_canonical_fx_cycle(
    provider, *, now: dt.datetime, journal: str, sender: Sender,
    cycles: Optional[Sequence[str]] = None, cycle_filter: Optional[str] = None,
    ticket_source: str = "LIVE", fx_data_source: str = "MT5_VT_MARKETS_DEMO",
    policy_root: str,
) -> Tuple[List[EvalResult], List[str]]:
    """Evaluate only active selected FX cycles; persist before delivery; journal every result."""
    now = _utc(now)
    if ticket_source not in ("LIVE", "REPLAY"):
        raise ValueError("ticket_source must be LIVE or REPLAY")
    active = set(active_cycles(now, cycle_filter))
    if cycles is not None:
        requested = set(cycles)
        unknown = requested - set(V1_CYCLES)
        if unknown:
            raise ValueError(f"unknown FX cycles: {sorted(unknown)}")
        active &= requested
    selected = tuple(cycle for cycle in V1_CYCLES if cycle in active)
    if not selected:
        return [], ["FX_CANONICAL NOTHING_IN_WINDOW"]
    results = run_daily_evaluation(
        now=now, day=now.date(), candle_provider=provider, archive_root=journal,
        include_crypto=False, fx_data_source=fx_data_source, policy_root=policy_root,
        ticket_source=ticket_source, cycles=selected)
    lines: List[str] = []
    for result in results:
        verify_error_class = None
        verified = None
        if _store_status(result) != "FAILED":
            try:
                verified = _verify_persisted_result(journal, result, ticket_source)
                if not verified:
                    verify_error_class = "TicketStoreVerificationFailed"
            except Exception as exc:  # noqa: BLE001 -- unreadable/tampered store blocks delivery
                verified = False
                verify_error_class = type(exc).__name__
        store_state = _store_status(result, verified)
        if store_state == "FAILED":
            delivery_state, error_class = "persistence_failed", None
        else:
            intent = _event_for_result(result, now, stage="INTENT", delivery_state="pending",
                                       ticket_source=ticket_source, store_status=store_state)
            try:
                append_session_event(journal, intent)
            except Exception as exc:  # noqa: BLE001 -- no send without a durable intent record
                lines.append(f"FX_CANONICAL {result.instrument} {result.session} "
                             f"ticket_store={store_state} delivery=journal_blocked "
                             f"error={type(exc).__name__}")
                continue
            try:
                delivery_state = sender.send_ticket(result.canonical)
                error_class = None
            except Exception as exc:  # noqa: BLE001 -- classify only; never blind-retry here
                delivery_state, error_class = "delivery_exception", type(exc).__name__
        event = _event_for_result(result, now, stage="RESULT", delivery_state=delivery_state,
                                  ticket_source=ticket_source, error_class=error_class,
                                  store_status=store_state, store_error_class=verify_error_class)
        try:
            append_session_event(journal, event)
        except Exception as exc:  # noqa: BLE001 -- sender SQLite is the fallback for network attempts
            event_error = type(exc).__name__
        else:
            event_error = None
        suffix = f" journal_error={event_error}" if event_error else ""
        lines.append(f"FX_CANONICAL {result.instrument} {result.session} decision={result.decision} "
                     f"ticket_store={store_state} delivery={delivery_state}{suffix}")
    return results, lines


def _date_from_ticket_id(ticket_id: Any) -> Optional[str]:
    if not isinstance(ticket_id, str):
        return None
    candidate = ticket_id.rsplit("|", 1)[-1]
    try:
        return dt.date.fromisoformat(candidate).isoformat()
    except ValueError:
        return None


def _latest_record(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    def key(row):
        timestamp = dt.datetime.fromisoformat(row["evaluated_at_utc"])
        if timestamp.tzinfo is None:
            raise ValueError("naive evaluation timestamp in TICKET_STORE_V1")
        return (timestamp.astimezone(UTC), row.get("source") == "LIVE", row.get("evaluation_id", ""))
    return max(rows, key=key)


def _market_closed_for_session(day: dt.date, session: str) -> bool:
    """Reuse the existing host FX weekend classifier; no new holiday/session calendar."""
    from large_smc_watch.watch import fx_market_closed
    window = session_windows_utc(day)[session]["trade"]
    midpoint = window[0] + (window[1] - window[0]) / 2
    return fx_market_closed(midpoint)


def _read_session_events(journal: str, day: str, session: str) -> List[Dict[str, Any]]:
    path = _session_event_path(journal, day, session)
    return [row for _, row in read_jsonl(path)]


def _delivery_bucket(state: str) -> str:
    if state in ("sent", "DELIVERED"):
        return "succeeded"
    if state in ("uncertain", "DELIVERY_UNCERTAIN", "pending"):
        return "uncertain"
    if state in ("failed", "DELIVERY_FAILED", "delivery_exception", "compatibility_error",
                 "compatibility_error_unpersisted"):
        return "failed"
    if state == "disabled":
        return "disabled"
    if state == "blocked":
        return "blocked"
    if state == "summary_only":
        return "summary_only"
    if state == "persistence_failed":
        return "persistence_failed"
    return "not_attempted"


def lsmc_rejection_counts(journal: str, start: dt.datetime, end: dt.datetime) -> Dict[str, int]:
    """Count durable rejection transitions within [start, end), without setup details.

    Archive filenames use the NY trading date; the event UTC time determines the
    session. Primary records only: correction wrappers are not extra transitions.
    An unreadable/malformed archive blocks the summary rather than inventing zeros.
    """
    counts = {reason: 0 for reason in ("REJECT_NO_STOP", "REJECT_NO_TARGET", "REJECT_STALE")}
    root = Path(journal) / "ticket_delivery/archive/fx_ticket_archive/ST_LARGE_SMC_V1"
    seen = set()
    for path in sorted(root.glob("*/LSMC_WATCH-*/*/????-??-??.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        event = record["payload"]
        if record["strategy_id"] != "ST_LARGE_SMC_V1" or event["to_state"] != "REJECTED":
            continue
        at = dt.datetime.fromisoformat(record["evaluation_time_utc"])
        if at.tzinfo is None:
            raise ValueError("naive Large-SMC rejection timestamp")
        if not start <= at.astimezone(UTC) < end:
            continue
        transition_id = event["transition_id"]
        if not isinstance(transition_id, str) or not transition_id:
            raise ValueError("missing Large-SMC rejection identity")
        reason = next((r for r in record["reason_codes"] if r in counts), None)
        if reason is None:
            raise ValueError("missing Large-SMC rejection reason")
        if transition_id not in seen:
            counts[reason] += 1
            seen.add(transition_id)
    return counts


def build_session_summary(journal: str, *, session_date: dt.date, session: str,
                          sender: Sender) -> Dict[str, Any]:
    """Build a deterministic digest from durable store/journal facts; never fabricate prices."""
    if session not in V1_CYCLES:
        raise ValueError(f"unknown FX cycle {session!r}")
    day = session_date.isoformat()
    store = TicketStore(os.path.join(journal, "ticket_store"))
    eval_path = os.path.join(store.evaluations_dir, f"{day}.jsonl")
    rows = [row for _, row in read_jsonl(eval_path)]
    expected_symbols = tuple(V1_FX_SYMBOLS)
    candidates: Dict[str, List[Dict[str, Any]]] = {symbol: [] for symbol in expected_symbols}
    for row in rows:
        if row.get("session") != session or _date_from_ticket_id(row.get("ticket_id")) != day:
            continue
        symbol = row.get("symbol")
        if symbol in candidates and row.get("source") in ("LIVE", "REPLAY"):
            candidates[symbol].append({**row, "record_source": "TICKET_STORE"})
    latest: Dict[str, Dict[str, Any]] = {
        symbol: _latest_record(items) for symbol, items in candidates.items() if items
    }

    event_rows = _read_session_events(journal, day, session)
    latest_event: Dict[Tuple[str, str], Dict[str, Any]] = {}
    # Reason lookup is keyed by the evaluation source too: LIVE and REPLAY rows may share a
    # ticket id and decision, and the digest must report the reason of the selected record.
    latest_event_by_source: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    persistence_failures: Dict[str, Dict[str, Any]] = {}
    for event in event_rows:
        if event.get("event_type") != "TICKET_DELIVERY" or event.get("stage") != "RESULT":
            continue
        key = (event.get("ticket_id", ""), event.get("decision", ""))
        prior = latest_event.get(key)
        if prior is None or str(event.get("recorded_at_utc", "")) >= str(prior.get("recorded_at_utc", "")):
            latest_event[key] = event
        source_key = (*key, event.get("source") or "")
        prior = latest_event_by_source.get(source_key)
        if prior is None or str(event.get("recorded_at_utc", "")) >= str(prior.get("recorded_at_utc", "")):
            latest_event_by_source[source_key] = event
        symbol = event.get("symbol")
        if (event.get("ticket_store_status") == "FAILED" and symbol in candidates
                and event.get("source") in ("LIVE", "REPLAY")):
            prior_failure = persistence_failures.get(symbol)
            if prior_failure is None or str(event.get("evaluated_at_utc", "")) >= str(
                    prior_failure.get("evaluated_at_utc", "")):
                persistence_failures[symbol] = event

    def timestamp(row: Dict[str, Any]) -> dt.datetime:
        value = row.get("evaluated_at_utc")
        if not value:
            return dt.datetime.min.replace(tzinfo=UTC)
        parsed = dt.datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            raise ValueError("naive evaluation timestamp in durable record")
        return parsed.astimezone(UTC)

    # A failed TICKET_STORE write is still an attempted evaluation when its explicit result
    # diagnostic reached the fsynced session journal. Use it only when it is newer than any
    # successfully stored row; otherwise the later store result is authoritative.
    for symbol, event in persistence_failures.items():
        failed = {
            "ticket_id": event.get("ticket_id"), "symbol": symbol, "session": session,
            "state": event.get("decision"), "source": event.get("source"),
            "evaluated_at_utc": event.get("evaluated_at_utc") or event.get("recorded_at_utc"),
            "block_reasons": [event.get("reason_code")] if event.get("reason_code") else [],
            "record_source": "PERSISTENCE_FAILURE_JOURNAL", "ticket_store_status": "FAILED",
        }
        if symbol not in latest or timestamp(failed) > timestamp(latest[symbol]):
            latest[symbol] = failed

    recorded = len(latest)
    market_closed = _market_closed_for_session(session_date, session)
    missing = [symbol for symbol in expected_symbols if symbol not in latest]
    missed_pairs = ([] if market_closed else [
        {"symbol": symbol, "reason_code": "SCHEDULED_EVALUATION_NOT_RECOVERED"} for symbol in missing
    ])
    out_of_session_pairs = ([
        {"symbol": symbol, "reason_code": "FX_MARKET_CLOSED"} for symbol in missing
    ] if market_closed else [])
    terminal_counts: Counter = Counter(
        row["state"] if _known_canonical_decision(row.get("state")) else "COMPATIBILITY_ERROR"
        for row in latest.values()
    )
    source_counts = Counter(row["source"] for row in latest.values())
    compatibility_errors = [
        {"symbol": symbol, "ticket_id": row.get("ticket_id"),
         "error_code": "UNKNOWN_CANONICAL_DECISION", "observed_decision": str(row.get("state"))[:120]}
        for symbol, row in sorted(latest.items()) if not _known_canonical_decision(row.get("state"))
    ]

    ticket_ids = {row["ticket_id"] for row in latest.values() if row.get("ticket_id")}
    for event in latest_event.values():
        if event.get("ticket_id"):
            ticket_ids.add(event["ticket_id"])
    delivery_states: Dict[Tuple[str, str], str] = {
        key: str(event.get("delivery_state", "not_attempted")) for key, event in latest_event.items()
    }
    for attempt in sender.delivery_attempts("ticket", ticket_ids):
        delivery_states[(attempt["identity"], attempt["status"])] = attempt["state"]
    expected_delivery_keys = {(row["ticket_id"], row["state"]) for row in latest.values()
                              if row.get("ticket_id") and row.get("state")}
    # A symbol may be evaluated more than once inside one session (e.g. INFO_ONLY_STALE ->
    # WATCH_READY). Only the latest terminal decision per symbol is counted; superseded
    # (ticket_id, decision) pairs stay in the audit journal and in `delivery_states`, but they
    # must never add a second delivery outcome for the same instrument.
    delivery_counts = Counter(_delivery_bucket(state) for key, state in delivery_states.items()
                              if key in expected_delivery_keys)
    for key in expected_delivery_keys - set(delivery_states):
        delivery_counts["not_attempted"] += 1

    uncertain = [item for item in sender.list_uncertain()
                 if item.get("kind") == "ticket" and item.get("identity") in ticket_ids]
    windows = session_windows_utc(session_date)[session]["trade"]
    if compatibility_errors:
        status = "COMPATIBILITY_ERROR"
    elif not missing:
        status = "COMPLETE"
    else:
        status = "OUT_OF_SESSION" if market_closed else "INCOMPLETE_WITH_MISSED"
    per_instrument = []
    for symbol in expected_symbols:
        row = latest.get(symbol)
        if row:
            known = _known_canonical_decision(row.get("state"))
            # The typed acquisition code and the persistence verification live on the fsynced
            # session event; TICKET_STORE_V1 keeps its frozen schema and canonical reason codes.
            event = latest_event_by_source.get((row.get("ticket_id"), row.get("state"), row.get("source"))) or {}
            item = {"symbol": symbol, "ticket_id": row.get("ticket_id"),
                    "decision": row.get("state") if known else "COMPATIBILITY_ERROR",
                    "source": row.get("source"),
                    # The event row carries the ticket's own reason code, so a SIGNAL_TIME_UNAVAILABLE
                    # DATA_ERROR stays distinguishable from an acquisition DATA_ERROR; the stored
                    # block_reasons are the fallback when no session event exists.
                    "reason_code": ((event.get("reason_code") or (row.get("block_reasons") or [None])[0])
                                    if known else "UNKNOWN_CANONICAL_DECISION"),
                    "acquisition_error_code": event.get("acquisition_error_code"),
                    "record_source": row.get("record_source", "TICKET_STORE"),
                    "ticket_store_status": event.get("ticket_store_status")
                    or row.get("ticket_store_status", "WRITTEN")}
            if not known:
                item["observed_decision"] = str(row.get("state"))[:120]
            per_instrument.append(item)
    return {
        "schema": SUMMARY_SCHEMA, "session_date": day, "session": session,
        "session_start_utc": windows[0].isoformat(), "session_end_utc": windows[1].isoformat(),
        "status": status, "expected_instruments": list(expected_symbols),
        "expected_evaluations": len(expected_symbols), "recorded_evaluations": recorded,
        "terminal_counts": dict(sorted(terminal_counts.items())),
        "large_smc": {"rejection_counts": lsmc_rejection_counts(journal, *windows)},
        "source_counts": dict(sorted(source_counts.items())),
        "data_failure_count": sum(terminal_counts[state] for state in (BLOCKED, INSUFFICIENT_DATA)),
        "persistence_failure_count": sum(row.get("ticket_store_status") == "FAILED"
                                          for row in latest.values()),
        "compatibility_error_count": len(compatibility_errors),
        "compatibility_errors": compatibility_errors,
        "missed_count": len(missed_pairs), "missed_pairs": missed_pairs,
        "out_of_session_count": len(out_of_session_pairs), "out_of_session_pairs": out_of_session_pairs,
        "per_instrument": per_instrument,
        "delivery_counts": {key: delivery_counts[key] for key in
                             ("succeeded", "failed", "uncertain", "disabled", "blocked",
                              "summary_only", "persistence_failed", "not_attempted")},
        "uncertain_deliveries": sorted(uncertain, key=lambda row: (row.get("identity", ""), row.get("status", ""))),
        "delivery_enabled": bool(sender.config.enabled),
        "execution_authorized": False,
    }

def _scheduler_start_path(journal: str) -> str:
    return os.path.join(journal, SCHEDULER_START)


def ensure_scheduler_start(journal: str, now: dt.datetime) -> dt.datetime:
    """Persist the first canonical-task time so catch-up never invents pre-deployment misses."""
    path = _scheduler_start_path(journal)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if raw.get("schema") != START_SCHEMA:
            raise ValueError("invalid canonical scheduler-start schema")
        started = dt.datetime.fromisoformat(raw["started_at_utc"])
        if started.tzinfo is None:
            raise ValueError("scheduler-start timestamp must be timezone-aware")
        return started.astimezone(UTC)
    started = _utc(now)
    record = {"schema": START_SCHEMA, "started_at_utc": started.isoformat()}
    try:
        with open(path, "x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        return ensure_scheduler_start(journal, now)
    return started


def _latest_summary_result(events: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    rows = [event for event in events if event.get("event_type") == "SESSION_SUMMARY_DELIVERY"
            and event.get("stage") == "RESULT"]
    return max(rows, key=lambda event: str(event.get("recorded_at_utc", ""))) if rows else None


def process_due_session_summaries(now: dt.datetime, *, journal: str, sender: Sender) -> List[str]:
    """Reconcile every due session since deployment; missing weekday runs become MISSED.

    Successful/uncertain/failed sends are not retried automatically. A previously disabled
    summary may be sent only after the explicit local+environment owner gates become enabled.
    """
    now = _utc(now)
    try:
        started = ensure_scheduler_start(journal, now)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        return [f"FX_SESSION_SUMMARY BLOCKED scheduler_journal={type(exc).__name__}"]
    lines: List[str] = []
    span = max(0, (now.date() - started.date()).days)
    for offset in range(span + 1):
        day = started.date() + dt.timedelta(days=offset)
        for session in V1_CYCLES:
            window = session_windows_utc(day)[session]["trade"]
            end_with_grace = window[1] + SUMMARY_GRACE
            if end_with_grace <= started or now <= end_with_grace:
                continue
            day_text = day.isoformat()
            try:
                prior_events = _read_session_events(journal, day_text, session)
                prior = _latest_summary_result(prior_events)
                if prior is not None:
                    prior_state = prior.get("delivery_state")
                    if prior_state in ("sent", "duplicate", "uncertain", "failed", "delivery_exception"):
                        continue
                    if prior_state in ("disabled", "blocked"):
                        if bool(prior.get("sender_enabled")) == bool(sender.config.enabled) or not sender.config.enabled:
                            continue
                summary = build_session_summary(journal, session_date=day, session=session, sender=sender)
            except Exception as exc:  # noqa: BLE001 -- a corrupt store must never produce a summary send
                blocked_event = {
                    "event_type": "SESSION_SUMMARY_DELIVERY", "stage": "RESULT",
                    "recorded_at_utc": now.isoformat(), "session_date": day_text, "session": session,
                    "delivery_state": "store_read_failed", "sender_enabled": bool(sender.config.enabled),
                    "error_class": type(exc).__name__, "execution_authorized": False,
                }
                try:
                    append_session_event(journal, blocked_event)
                except Exception:
                    pass
                lines.append(f"FX_SESSION_SUMMARY {day_text} {session} blocked={type(exc).__name__}")
                continue
            intent = {
                "event_type": "SESSION_SUMMARY_DELIVERY", "stage": "INTENT",
                "recorded_at_utc": now.isoformat(), "session_date": day_text, "session": session,
                "summary_status": summary["status"], "recorded_evaluations": summary["recorded_evaluations"],
                "expected_evaluations": summary["expected_evaluations"],
                "sender_enabled": bool(sender.config.enabled), "delivery_state": "pending",
                "execution_authorized": False,
            }
            try:
                append_session_event(journal, intent)
            except Exception as exc:  # noqa: BLE001 -- no message send without a durable intent
                lines.append(f"FX_SESSION_SUMMARY {day_text} {session} delivery=journal_blocked "
                             f"error={type(exc).__name__}")
                continue
            try:
                delivery_state = sender.send_session_summary(summary)
                error_class = None
            except Exception as exc:  # noqa: BLE001 -- never auto-retry an ambiguous result here
                delivery_state, error_class = "delivery_exception", type(exc).__name__
            outcome = {
                "event_type": "SESSION_SUMMARY_DELIVERY", "stage": "RESULT",
                "recorded_at_utc": now.isoformat(), "session_date": day_text, "session": session,
                "summary_status": summary["status"], "recorded_evaluations": summary["recorded_evaluations"],
                "expected_evaluations": summary["expected_evaluations"],
                "sender_enabled": bool(sender.config.enabled), "delivery_state": delivery_state,
                "error_class": error_class, "execution_authorized": False,
            }
            try:
                append_session_event(journal, outcome)
            except Exception as exc:  # noqa: BLE001 -- adapter SQLite is authoritative for sent attempts
                error_class = type(exc).__name__
            suffix = f" journal_error={error_class}" if error_class else ""
            lines.append(f"FX_SESSION_SUMMARY {day_text} {session} status={summary['status']} "
                         f"delivery={delivery_state}{suffix}")
    return lines
