"""Rebuildable SQLite index over the TICKET_STORE_V1 JSONL files.

The JSONL files are the source of truth; the index is derived and disposable. `rebuild()`
writes a fresh database beside the target and swaps it in with os.replace, so a failed
rebuild never leaves a half-built index. `check()` compares the JSONL records with the
index: counts and ids must match exactly.
"""
from __future__ import annotations

import os
import sqlite3
from typing import Any, Dict, Optional

from ticket_store.store import TicketStore

INDEX_FILE = "index.sqlite"
_DDL = (
    """CREATE TABLE evaluations (
        evaluation_id TEXT PRIMARY KEY, ticket_id TEXT, strategy TEXT NOT NULL, source TEXT NOT NULL,
        symbol TEXT NOT NULL, session TEXT NOT NULL, evaluated_at_utc TEXT NOT NULL, signal_close_utc TEXT,
        state TEXT NOT NULL, direction TEXT, record_sha256 TEXT NOT NULL, file TEXT NOT NULL, line INTEGER NOT NULL)""",
    "CREATE INDEX evaluations_ticket ON evaluations(ticket_id)",
    "CREATE INDEX evaluations_day ON evaluations(evaluated_at_utc)",
    """CREATE TABLE outcomes (
        outcome_id TEXT PRIMARY KEY, ticket_id TEXT NOT NULL, source TEXT NOT NULL, outcome_kind TEXT NOT NULL,
        recorded_at_utc TEXT, result TEXT, record_sha256 TEXT NOT NULL, file TEXT NOT NULL, line INTEGER NOT NULL)""",
    "CREATE INDEX outcomes_ticket ON outcomes(ticket_id)",
)


def index_path(root: str) -> str:
    return os.path.join(root, INDEX_FILE)


def rebuild(root: str, db_path: Optional[str] = None) -> Dict[str, int]:
    store, db_path = TicketStore(root), db_path or index_path(root)
    tmp = db_path + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    con = sqlite3.connect(tmp)
    try:
        for ddl in _DDL:
            con.execute(ddl)
        for path, n, r in store.iter_records("evaluations"):
            con.execute("INSERT INTO evaluations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (r["evaluation_id"], r.get("ticket_id"), r["strategy"], r["source"], r["symbol"], r["session"],
                         r["evaluated_at_utc"], r.get("signal_close_utc"), r["state"], r.get("direction"),
                         r["record_sha256"], os.path.relpath(path, root), n))
        for path, n, r in store.iter_records("outcomes"):
            result = r.get("result")
            con.execute("INSERT INTO outcomes VALUES (?,?,?,?,?,?,?,?,?)",
                        (r["outcome_id"], r["ticket_id"], r["source"], r["outcome_kind"], r.get("recorded_at_utc"),
                         None if result is None else str(result), r["record_sha256"], os.path.relpath(path, root), n))
        con.commit()
    finally:
        con.close()
    os.replace(tmp, db_path)
    return {k: v["index"] for k, v in check(root, db_path)["tables"].items()}


def check(root: str, db_path: Optional[str] = None) -> Dict[str, Any]:
    """{"ok": bool, "tables": {name: {"jsonl": n, "index": m, "missing": [...], "extra": [...]}}}."""
    store, db_path = TicketStore(root), db_path or index_path(root)
    report: Dict[str, Any] = {"ok": True, "tables": {}}
    con = sqlite3.connect(db_path) if os.path.exists(db_path) else None
    try:
        for kind, key in (("evaluations", "evaluation_id"), ("outcomes", "outcome_id")):
            jsonl = [r[key] for _, _, r in store.iter_records(kind)]
            indexed = [row[0] for row in con.execute(f"SELECT {key} FROM {kind}")] if con else []
            missing, extra = sorted(set(jsonl) - set(indexed)), sorted(set(indexed) - set(jsonl))
            ok = len(jsonl) == len(indexed) and not missing and not extra and len(set(jsonl)) == len(jsonl)
            report["tables"][kind] = {"jsonl": len(jsonl), "index": len(indexed), "missing": missing, "extra": extra,
                                      "duplicate_ids_in_jsonl": len(jsonl) - len(set(jsonl))}
            report["ok"] = report["ok"] and ok
    finally:
        if con:
            con.close()
    if con is None:
        report["ok"] = report["ok"] and all(t["jsonl"] == 0 for t in report["tables"].values())
        report["index_missing"] = True
    return report
