Warning: truncated output (original token count: 7970)
Total output lines: 606

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
                     …2970 tokens truncated…pt["state"]
    delivery_counts = Counter(_delivery_bucket(state) for state in delivery_states.values())
    expected_delivery_keys = {(row["ticket_id"], row["state"]) for row in latest.values()
                              if row.get("ticket_id") and row.get("state")}
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
            event = latest_event.get((row.get("ticket_id"), row.get("state"))) or {}
            item = {"symbol": symbol, "ticket_id": row.get("ticket_id"),
                    "decision": row.get("state") if known else "COMPATIBILITY_ERROR",
                    "source": row.get("source"),
                    "reason_code": ((row.get("block_reasons") or [None])[0] if known else
                                    "UNKNOWN_CANONICAL_DECISION"),
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
