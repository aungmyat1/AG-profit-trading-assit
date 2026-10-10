"""TICKET_STORE_V1 -- append-only JSONL source of truth for ticket evaluations and outcomes.

Layout under a store root (default `<archive_root>/ticket_store`):
    evaluations/<YYYY-MM-DD>.jsonl   one EVALUATION per strategy x symbol x session evaluation,
                                     every terminal state (not only READY); day = evaluated_at_utc
    outcomes/<YYYY-MM-DD>.jsonl      OUTCOME records keyed by ticket_id; day = recorded_at_utc
                                     ("undated.jsonl" when the source carried no time)
    index.sqlite                     rebuildable index (ticket_store.index); never authoritative

Records are never mutated or deleted. Writes are idempotent: an evaluation is identified by
(strategy, symbol, session, evaluated_at_utc, source); re-appending the same record (process
restart, retry) is a no-op, while a different record under the same identity is refused
(TicketStoreConflict). A file whose last line is truncated is refused (TicketStoreCorrupt) --
the store never repairs or rewrites it. Single writer per store root: writes are serialized
within a process; separate processes must not write the same root concurrently (the host
scheduler already serializes FX runs).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from typing import Any, Dict, Iterator, List, Optional, Tuple

SCHEMA_EVALUATION = "TICKET_STORE_V1_EVALUATION"
SCHEMA_OUTCOME = "TICKET_STORE_V1_OUTCOME"
LIVE, REPLAY, LEGACY, DEMO = "LIVE", "REPLAY", "LEGACY", "DEMO"
SOURCES = (LIVE, REPLAY, LEGACY, DEMO)

# Field order is the schema. Every field is always present; absent facts are null, never inferred.
EVALUATION_FIELDS = (
    "schema", "evaluation_id", "ticket_id", "strategy", "spec_sha256", "code_sha", "source",
    "symbol", "session", "evaluated_at_utc", "signal_close_utc", "state", "block_reasons", "warnings",
    "direction", "entry", "sl", "tp1", "tp2", "spread_at_signal", "spread_measured_at_utc",
    "input_bar_hashes", "delivery_status", "owner_decision_ref", "provenance", "record_sha256",
)
OUTCOME_FIELDS = (
    "schema", "outcome_id", "ticket_id", "source", "outcome_kind", "recorded_at_utc", "result",
    "payload", "provenance", "record_sha256",
)
_EVALUATION_KEY = ("strategy", "symbol", "session", "evaluated_at_utc", "source")
_LOCKS: Dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


class TicketStoreError(RuntimeError):
    pass


class TicketStoreConflict(TicketStoreError):
    """Same identity, different content: tickets are never mutated."""


class TicketStoreCorrupt(TicketStoreError):
    """Unparseable or truncated JSONL line; the store does not repair it."""


def _sha256(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _lock(path: str) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(os.path.abspath(path), threading.Lock())


def evaluation_id(record: Dict[str, Any]) -> str:
    return _sha256([record.get(k) for k in _EVALUATION_KEY])


def outcome_id(record: Dict[str, Any]) -> str:
    return _sha256([record.get("ticket_id"), record.get("outcome_kind"), record.get("source"),
                    record.get("recorded_at_utc"), _sha256(record.get("payload"))])


def _seal(record: Dict[str, Any], fields: Tuple[str, ...]) -> Dict[str, Any]:
    out = {k: record.get(k) for k in fields}
    out["record_sha256"] = _sha256({k: v for k, v in out.items() if k != "record_sha256"})
    return out


def build_evaluation(**fields: Any) -> Dict[str, Any]:
    unknown = set(fields) - set(EVALUATION_FIELDS)
    if unknown:
        raise TicketStoreError(f"unknown evaluation fields: {sorted(unknown)}")
    rec = {k: fields.get(k) for k in EVALUATION_FIELDS}
    rec["schema"] = SCHEMA_EVALUATION
    rec["block_reasons"] = list(rec["block_reasons"] or [])
    rec["warnings"] = list(rec["warnings"] or [])
    if rec["source"] not in SOURCES:
        raise TicketStoreError(f"source {rec['source']!r} not in {SOURCES}")
    missing = [k for k in ("strategy", "symbol", "session", "evaluated_at_utc", "state") if not rec.get(k)]
    if missing:
        raise TicketStoreError(f"evaluation identity/state fields missing: {missing}")
    rec["evaluation_id"] = evaluation_id(rec)
    return _seal(rec, EVALUATION_FIELDS)


def build_outcome(**fields: Any) -> Dict[str, Any]:
    unknown = set(fields) - set(OUTCOME_FIELDS)
    if unknown:
        raise TicketStoreError(f"unknown outcome fields: {sorted(unknown)}")
    rec = {k: fields.get(k) for k in OUTCOME_FIELDS}
    rec["schema"] = SCHEMA_OUTCOME
    if rec["source"] not in SOURCES:
        raise TicketStoreError(f"source {rec['source']!r} not in {SOURCES}")
    if not rec.get("ticket_id") or not rec.get("outcome_kind"):
        raise TicketStoreError("outcome requires ticket_id and outcome_kind")
    rec["outcome_id"] = outcome_id(rec)
    return _seal(rec, OUTCOME_FIELDS)


def read_jsonl(path: str) -> Iterator[Tuple[int, Dict[str, Any]]]:
    """(1-based line, record). Any unparseable line -- including a truncated tail -- raises."""
    if not os.path.exists(path):
        return
    with open(path, "rb") as f:
        data = f.read()
    if data and not data.endswith(b"\n"):
        raise TicketStoreCorrupt(f"{path}: last line is truncated (no trailing newline)")
    for n, raw in enumerate(data.splitlines(), 1):
        if not raw.strip():
            continue
        try:
            yield n, json.loads(raw)
        except ValueError as exc:
            raise TicketStoreCorrupt(f"{path}:{n}: {exc}") from exc


class TicketStore:
    def __init__(self, root: str):
        self.root = root
        self.evaluations_dir = os.path.join(root, "evaluations")
        self.outcomes_dir = os.path.join(root, "outcomes")

    # ------------------------------------------------------------------ paths
    def evaluation_path(self, record: Dict[str, Any]) -> str:
        return os.path.join(self.evaluations_dir, f"{str(record['evaluated_at_utc'])[:10]}.jsonl")

    def outcome_path(self, record: Dict[str, Any]) -> str:
        day = str(record.get("recorded_at_utc") or "")[:10] or "undated"
        return os.path.join(self.outcomes_dir, f"{day}.jsonl")

    def files(self, kind: str) -> List[str]:
        from ticket_store.v2 import FIELDS
        if kind not in ("evaluations", "outcomes") and kind not in FIELDS:
            raise TicketStoreError(f"unknown record kind: {kind}")
        d = os.path.join(self.root, kind)
        return sorted(os.path.join(d, f) for f in os.listdir(d) if f.endswith(".jsonl")) if os.path.isdir(d) else []

    # ------------------------------------------------------------------ writes
    def _append(self, path: str, record: Dict[str, Any], id_field: str, scan: List[str]) -> bool:
        with _lock(path):
            for other in scan:
                for _, existing in read_jsonl(other):
                    if existing.get(id_field) == record[id_field]:
                        if existing.get("record_sha256") == record["record_sha256"]:
                            return False                       # idempotent re-write
                        raise TicketStoreConflict(f"{id_field} {record[id_field]} already stored with different "
                                                  f"content in {other}; records are never mutated")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(record, sort_keys=True, default=str) + "\n")
                f.flush()
                os.fsync(f.fileno())
            return True

    def append_evaluation(self, record: Dict[str, Any]) -> bool:
        """True when written, False when the identical record is already stored."""
        if record.get("schema") != SCHEMA_EVALUATION or record.get("record_sha256") is None:
            raise TicketStoreError("append_evaluation takes a record from build_evaluation()")
        path = self.evaluation_path(record)
        return self._append(path, record, "evaluation_id", [path])   # identity fixes the day file

    def append_outcome(self, record: Dict[str, Any]) -> bool:
        if record.get("schema") != SCHEMA_OUTCOME or record.get("record_sha256") is None:
            raise TicketStoreError("append_outcome takes a record from build_outcome()")
        path = self.outcome_path(record)
        return self._append(path, record, "outcome_id", [path])

    # ------------------------------------------------------------------ reads
    def iter_records(self, kind: str) -> Iterator[Tuple[str, int, Dict[str, Any]]]:
        for path in self.files(kind):
            for n, rec in read_jsonl(path):
                if kind not in ("evaluations", "outcomes"):
                    from ticket_store.v2 import build_record
                    try:
                        if not isinstance(rec, dict) or build_record(kind, **rec) != rec:
                            raise TicketStoreError("record seal or identity mismatch")
                    except (TicketStoreError, TypeError, KeyError) as exc:
                        raise TicketStoreCorrupt(f"{path}:{n}: {exc}") from exc
                yield path, n, rec

    def evaluations(self) -> List[Dict[str, Any]]:
        return [r for _, _, r in self.iter_records("evaluations")]

    def outcomes(self, ticket_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return [r for _, _, r in self.iter_records("outcomes") if ticket_id is None or r.get("ticket_id") == ticket_id]

    # V2 records use the V1 writer; their stable reference fixes identity across date files.
    def _append_event(self, kind: str, record: Dict[str, Any]) -> bool:
        from ticket_store.v2 import build_record
        if build_record(kind, **record) != record:
            raise TicketStoreError("append takes an unmodified sealed V2 builder record")
        path = os.path.join(self.root, kind, f"{record['recorded_at_utc'][:10]}.jsonl")
        with _lock(os.path.join(self.root, kind)):
            scan = sorted(set(self.files(kind) + [path]))
            for _ in self.iter_records(kind):
                pass  # Validate existing seals before V1 idempotency checks.
            return self._append(path, record, "record_id", scan)

    def append_delivery(self, record):
        return self._append_event('deliveries', record)

    def append_owner_decision(self, record):
        return self._append_event('owner_decisions', record)

    def append_order_event(self, record):
        return self._append_event('order_events', record)

    def append_position_close(self, record):
        return self._append_event('position_closes', record)

    def lifecycle_records(self, kind: str, ticket_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return [r for _, _, r in self.iter_records(kind) if ticket_id is None or r['ticket_id'] == ticket_id]
