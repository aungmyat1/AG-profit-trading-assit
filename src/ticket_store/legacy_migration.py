"""Migrate existing journal records into TICKET_STORE_V1 with source=LEGACY. Read-only on the journal.

Legacy record kinds (paths relative to the journal root):
  canonical  ticket_delivery/daily_evaluator/*.jsonl            (AG_CANONICAL_TICKET_V1 archive)
  manual     ticket_delivery/manual/tickets/*.jsonl             (manual trade tickets)
  scan       ticket_delivery/manual/scan_records/*.jsonl        (one per strategy x symbol x session run)
  fx         ticket_delivery/archive/fx_ticket_archive/**/*.json (legacy V1 informational tickets)
  decisions  ticket_delivery/manual/owner_decisions.jsonl       (linked as owner_decision_ref only)
  outcomes   ticket_delivery/manual/outcomes/*.jsonl            (-> OUTCOME records)

The kinds are different views of the same evaluation, so they are grouped by the natural key
(strategy@version, symbol, session, evaluated_at) into ONE EVALUATION record. Each field takes
the first non-null value in precedence canonical > manual > scan > fx. A field none of them
carries stays null -- nothing is inferred (spec_sha256 and input_bar_hashes are always null:
the contract bytes and bars at the time were not recorded). Symbols are not normalized.
Every source line is listed in `provenance.legacy_sources`. Re-running is idempotent.
"""
from __future__ import annotations

import glob
import json
import os
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from ticket_store.store import LEGACY, TicketStore, build_evaluation, build_outcome, read_jsonl

PRECEDENCE = ("canonical", "manual", "scan", "fx")
_FIELDS = ("ticket_id", "code_sha", "signal_close_utc", "state", "block_reasons", "warnings", "direction", "entry",
           "sl", "tp1", "tp2", "spread_at_signal", "spread_measured_at_utc", "delivery_status")


def _first(*vals):
    return next((v for v in vals if v is not None), None)


def _target(targets, leg) -> Optional[float]:
    return next((t.get("price") for t in targets or [] if t.get("leg") == leg), None)


def _canonical(r) -> Tuple[tuple, Dict[str, Any]]:
    p, state = r.get("prices") or {}, r.get("decision")
    key = (f"{r.get('strategy_id')}@{r.get('strategy_version')}", r.get("instrument"), r.get("session"), r.get("created_at"))
    return key, {"ticket_id": r.get("ticket_id"), "state": state, "block_reasons": r.get("reason_codes"),
                 "signal_close_utc": (r.get("trigger") or {}).get("trigger_bar_close_utc"), "direction": r.get("direction"),
                 "entry": p.get("entry_reference_raw"), "sl": p.get("sl_raw"), "tp1": p.get("tp1_raw"), "tp2": p.get("tp2_raw")}


def _manual(r):
    key = (r.get("strategy"), r.get("symbol"), r.get("session") or r.get("cycle"), r.get("evaluated_at"))
    spread = r.get("spread")
    return key, {"ticket_id": r.get("ticket_id"), "code_sha": r.get("code_sha"), "state": r.get("state"),
                 "block_reasons": r.get("block_reasons"), "warnings": r.get("warnings"),
                 "signal_close_utc": r.get("signal_close_utc"), "direction": r.get("direction"),
                 "entry": r.get("entry"), "sl": _first(r.get("sl"), r.get("stop_loss")),
                 "tp1": _first(r.get("tp1"), _target(r.get("targets"), 1)),
                 "tp2": _first(r.get("tp2"), _target(r.get("targets"), 2)),
                 "spread_at_signal": spread, "spread_measured_at_utc": r.get("evaluated_at") if spread is not None else None,
                 "delivery_status": r.get("delivery_mode")}


def _scan(r):
    key = (r.get("strategy"), r.get("symbol"), r.get("session"), r.get("created_at"))
    return key, {"ticket_id": r.get("ticket_id"), "code_sha": r.get("code_sha"), "state": r.get("state"),
                 "block_reasons": r.get("block_reasons"), "warnings": r.get("warnings")}


def _fx(r):
    p = r.get("payload") or {}
    key = (f"{r.get('strategy_id')}@{r.get('strategy_version')}", r.get("symbol"), r.get("cycle"),
           r.get("evaluation_time_utc"))
    spread = p.get("spread")
    return key, {"ticket_id": r.get("logical_ticket_id"), "state": p.get("decision"),
                 "block_reasons": r.get("reason_codes"), "direction": p.get("direction"), "entry": p.get("entry"),
                 "sl": p.get("stop_loss"), "tp1": _target(p.get("targets"), 1), "tp2": _target(p.get("targets"), 2),
                 "spread_at_signal": spread, "spread_measured_at_utc": p.get("evaluated_at") if spread is not None else None,
                 "delivery_status": p.get("delivery_mode")}


def _jsonl_rows(pattern: str, journal: str):
    for path in sorted(glob.glob(os.path.join(journal, pattern))):
        for n, rec in read_jsonl(path):
            yield f"{os.path.relpath(path, journal).replace(os.sep, '/')}#L{n}", rec


def _sources(journal: str):
    yield from (("canonical", ref, r) for ref, r in _jsonl_rows("ticket_delivery/daily_evaluator/*.jsonl", journal))
    yield from (("manual", ref, r) for ref, r in _jsonl_rows("ticket_delivery/manual/tickets/*.jsonl", journal))
    yield from (("scan", ref, r) for ref, r in _jsonl_rows("ticket_delivery/manual/scan_records/*.jsonl", journal))
    for path in sorted(glob.glob(os.path.join(journal, "ticket_delivery/archive/fx_ticket_archive/**/*.json"),
                                 recursive=True)):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for i, rec in enumerate(data if isinstance(data, list) else [data], 1):
            yield "fx", f"{os.path.relpath(path, journal).replace(os.sep, '/')}#{i}", rec


_EXTRACT = {"canonical": _canonical, "manual": _manual, "scan": _scan, "fx": _fx}


def migrate(journal: str, store: TicketStore) -> Dict[str, Any]:
    counts: Dict[str, Any] = {"read": Counter(), "skipped_no_key": Counter(), "evaluations_written": 0,
                              "evaluations_already_present": 0, "outcomes_written": 0, "outcomes_already_present": 0,
                              "owner_decision_refs": 0}
    groups: Dict[tuple, List[Tuple[str, str, Dict[str, Any]]]] = {}
    for kind, ref, rec in _sources(journal):
        counts["read"][kind] += 1
        key, fields = _EXTRACT[kind](rec)
        if not all(key) or "None@None" in str(key[0]):
            counts["skipped_no_key"][kind] += 1
            continue
        groups.setdefault(key, []).append((kind, ref, fields))

    decisions: Dict[str, str] = {r["ticket_id"]: ref
                                 for ref, r in _jsonl_rows("ticket_delivery/manual/owner_decisions.jsonl", journal)
                                 if r.get("ticket_id")}

    for key in sorted(groups):
        views = sorted(groups[key], key=lambda v: (PRECEDENCE.index(v[0]), v[1]))
        merged = {f: _first(*(v[2].get(f) for v in views)) for f in _FIELDS}
        ref = decisions.get(merged["ticket_id"]) if merged["ticket_id"] else None
        counts["owner_decision_refs"] += ref is not None
        rec = build_evaluation(
            strategy=key[0], symbol=key[1], session=key[2], evaluated_at_utc=key[3], source=LEGACY,
            spec_sha256=None, input_bar_hashes=None, owner_decision_ref=ref,
            provenance={"writer": "ticket_store.legacy_migration",
                        "legacy_sources": [{"kind": k, "ref": r} for k, r, _ in views]},
            **merged)
        written = store.append_evaluation(rec)
        counts["evaluations_written" if written else "evaluations_already_present"] += 1

    for ref, r in _jsonl_rows("ticket_delivery/manual/outcomes/*.jsonl", journal):
        counts["read"]["outcomes"] += 1
        if not r.get("ticket_id"):
            counts["skipped_no_key"]["outcomes"] += 1
            continue
        rec = build_outcome(ticket_id=r["ticket_id"], source=LEGACY, outcome_kind=r.get("tag") or "UNTAGGED",
                            recorded_at_utc=r.get("resolved_at"),
                            result=(r.get("virtual_outcome") or {}).get("result"), payload=r,
                            provenance={"writer": "ticket_store.legacy_migration", "legacy_source": ref})
        written = store.append_outcome(rec)
        counts["outcomes_written" if written else "outcomes_already_present"] += 1
    counts["evaluation_groups"] = len(groups)
    counts["read"], counts["skipped_no_key"] = dict(counts["read"]), dict(counts["skipped_no_key"])
    return counts
