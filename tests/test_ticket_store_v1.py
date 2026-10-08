"""TICKET_STORE_V1: append-only evaluation/outcome store, rebuildable index, canonical adapter, legacy migration."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest

from ticket_store import (
    EVALUATION_FIELDS, LEGACY, OUTCOME_FIELDS, REPLAY, TicketStore, TicketStoreConflict, TicketStoreCorrupt,
    TicketStoreError, build_evaluation, build_outcome,
)
from ticket_store import adapter, index
from ticket_store.legacy_migration import migrate
from v1_tickets import daily_evaluator as de

UTC = dt.timezone.utc
REPO = Path(__file__).resolve().parents[1]
EVIDENCE_JOURNAL = REPO / "docs/status/evidence/pass_b_replay_b92f529_0740Z/journal"
NOW = dt.datetime(2026, 10, 7, 7, 20, tzinfo=UTC)


def _eval(**over):
    base = dict(strategy="S@1", symbol="EURUSD", session="ASIAN_LONDON", evaluated_at_utc="2026-10-07T07:20:00+00:00",
                source=REPLAY, state="NO_TRADE", ticket_id="S|1|EURUSD|ASIAN_LONDON|2026-10-07")
    base.update(over)
    return build_evaluation(**base)


# ------------------------------------------------------------------ schema and append semantics

def test_evaluation_schema_has_every_field_and_nulls_absent_facts():
    rec = _eval()
    assert tuple(rec) == EVALUATION_FIELDS
    assert rec["schema"] == "TICKET_STORE_V1_EVALUATION" and rec["block_reasons"] == [] and rec["warnings"] == []
    assert all(rec[k] is None for k in ("spec_sha256", "code_sha", "entry", "sl", "tp1", "tp2", "spread_at_signal",
                                        "input_bar_hashes", "owner_decision_ref"))
    with pytest.raises(TicketStoreError):
        _eval(source="SIMULATED")
    with pytest.raises(TicketStoreError):
        _eval(state=None)
    with pytest.raises(TicketStoreError):
        build_evaluation(strategy="S@1", made_up_field=1)


def test_duplicate_write_and_restart_are_idempotent(tmp_path):
    rec = _eval()
    assert TicketStore(str(tmp_path)).append_evaluation(rec) is True
    assert TicketStore(str(tmp_path)).append_evaluation(rec) is False           # new instance = process restart
    assert TicketStore(str(tmp_path)).append_evaluation(_eval()) is False        # rebuilt identical record
    lines = (tmp_path / "evaluations" / "2026-10-07.jsonl").read_text().splitlines()
    assert len(lines) == 1 and json.loads(lines[0]) == rec


def test_same_identity_with_different_content_is_refused_never_mutated(tmp_path):
    store = TicketStore(str(tmp_path))
    store.append_evaluation(_eval())
    before = (tmp_path / "evaluations" / "2026-10-07.jsonl").read_bytes()
    with pytest.raises(TicketStoreConflict):
        store.append_evaluation(_eval(state="WATCH_READY"))
    assert (tmp_path / "evaluations" / "2026-10-07.jsonl").read_bytes() == before
    # a different evaluation time is a new evaluation, not a mutation
    assert store.append_evaluation(_eval(evaluated_at_utc="2026-10-07T07:35:00+00:00")) is True
    assert len(store.evaluations()) == 2


def test_truncated_tail_fails_closed_and_is_not_repaired(tmp_path):
    store = TicketStore(str(tmp_path))
    store.append_evaluation(_eval())
    path = tmp_path / "evaluations" / "2026-10-07.jsonl"
    path.write_bytes(path.read_bytes() + b'{"schema": "TICKET_STORE_V1_EVAL')        # crash mid-write
    before = path.read_bytes()
    with pytest.raises(TicketStoreCorrupt):
        store.append_evaluation(_eval(evaluated_at_utc="2026-10-07T07:35:00+00:00"))
    with pytest.raises(TicketStoreCorrupt):
        store.evaluations()
    assert path.read_bytes() == before


def test_outcomes_are_separate_records_keyed_by_ticket_id(tmp_path):
    store = TicketStore(str(tmp_path))
    rec = _eval()
    store.append_evaluation(rec)
    out = build_outcome(ticket_id=rec["ticket_id"], source=REPLAY, outcome_kind="VIRTUAL_FORWARD",
                        recorded_at_utc="2026-10-07T16:00:00+00:00", result="SL", payload={"gross_R": -1.0})
    assert tuple(out) == OUTCOME_FIELDS
    assert store.append_outcome(out) is True and store.append_outcome(out) is False
    assert [o["result"] for o in store.outcomes(rec["ticket_id"])] == ["SL"]
    assert store.evaluations() == [rec]                                          # ticket untouched
    with pytest.raises(TicketStoreError):
        build_outcome(ticket_id=None, source=REPLAY, outcome_kind="X")


# ------------------------------------------------------------------ index

def test_index_rebuild_and_integrity_check(tmp_path):
    store = TicketStore(str(tmp_path))
    for minute in (20, 35, 50):
        store.append_evaluation(_eval(evaluated_at_utc=f"2026-10-07T07:{minute}:00+00:00"))
    assert index.rebuild(str(tmp_path)) == {"evaluations": 3, "outcomes": 0}
    assert index.check(str(tmp_path))["ok"] is True
    store.append_evaluation(_eval(evaluated_at_utc="2026-10-07T08:05:00+00:00"))   # index now stale
    report = index.check(str(tmp_path))
    assert report["ok"] is False and report["tables"]["evaluations"]["jsonl"] == 4
    assert report["tables"]["evaluations"]["index"] == 3
    index.rebuild(str(tmp_path))                                                    # rebuildable at any time
    assert index.check(str(tmp_path))["ok"] is True


def test_reindex_script_exit_codes(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("reindex", REPO / "scripts" / "ticket_store_reindex.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    TicketStore(str(tmp_path)).append_evaluation(_eval())
    assert mod.main(["--store", str(tmp_path), "--check-only"]) == 1             # no index yet
    assert mod.main(["--store", str(tmp_path)]) == 0
    assert mod.main(["--store", str(tmp_path), "--check-only"]) == 0


# ------------------------------------------------------------------ canonical adapter (daily evaluator)

def test_every_terminal_state_is_stored_and_decisions_are_unchanged(tmp_path):
    results = de.run_daily_evaluation(now=NOW, archive_root=str(tmp_path), include_crypto=False)
    store = TicketStore(str(tmp_path / "ticket_store"))
    recs = {(r["symbol"], r["session"]): r for r in store.evaluations()}
    assert len(recs) == len(results) == len(de.FX_PAIRS)
    for res in results:
        rec = recs[(res.instrument, res.session)]
        assert res.ticket_store_written is True and res.ticket_store_error is None
        assert rec["state"] == res.decision == res.canonical["decision"]          # not only READY
        assert rec["ticket_id"] == res.ticket_id and rec["source"] == REPLAY
        assert rec["strategy"] == "ST_ASIAN_SWEEP_5R_V1@1.1.1"
        assert rec["provenance"]["canonical_hash"] is not None
    # restart: the same run again writes nothing new
    again = de.run_daily_evaluation(now=NOW, archive_root=str(tmp_path), include_crypto=False)
    assert [r.decision for r in again] == [r.decision for r in results]
    assert all(r.ticket_store_written is False for r in again)
    assert len(store.evaluations()) == len(de.FX_PAIRS)


def test_signal_record_carries_levels_spread_bar_hashes_and_spec_hash(tmp_path):
    import sys
    sys.path.insert(0, str(REPO / "tests"))
    from test_actionability_and_canonical_ticket import _build_asian_london_sweep
    ref, n, post = _build_asian_london_sweep(NOW, age_minutes=5)
    provider = de.fixture_candle_provider(ref, n, post, spread=0.0001, current_price=1.1636,
                                          data_close=post[-1].time + dt.timedelta(minutes=15))
    res = de.evaluate_fx_pair("EURUSD", "ASIAN_LONDON", now=NOW, day=NOW.date(), candle_provider=provider,
                              archive_root=str(tmp_path))
    rec = TicketStore(str(tmp_path / "ticket_store")).evaluations()[0]
    prices = res.canonical["prices"]
    assert rec["state"] == res.decision
    assert (rec["direction"], rec["entry"], rec["sl"], rec["tp1"], rec["tp2"]) == (
        res.canonical["direction"], prices["entry_reference_raw"], prices["sl_raw"], prices["tp1_raw"], prices["tp2_raw"])
    assert rec["signal_close_utc"] == res.canonical["trigger"]["trigger_bar_close_utc"] is not None
    assert rec["spread_at_signal"] == 0.0001 and rec["spread_measured_at_utc"] == rec["evaluated_at_utc"]
    assert rec["input_bar_hashes"]["reference_count"] == n and rec["input_bar_hashes"]["trade_count"] == len(post)
    assert rec["input_bar_hashes"]["reference"] == adapter.bar_hash(ref)
    want = hashlib.sha256((REPO / "strategies/ST_ASIAN_SWEEP_5R_V1.yaml").read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert rec["spec_sha256"] == want
    assert adapter.spec_sha256("ST_ASIAN_SWEEP_5R_V1", "9.9.9") is None             # no matching contract -> null


def test_store_failure_is_reported_and_never_changes_the_decision(tmp_path, monkeypatch):
    baseline = de.run_daily_evaluation(now=NOW, archive_root=str(tmp_path / "a"), include_crypto=False)

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(adapter, "write_canonical", boom)
    failed = de.run_daily_evaluation(now=NOW, archive_root=str(tmp_path / "b"), include_crypto=False)
    assert [r.decision for r in failed] == [r.decision for r in baseline]
    assert all(r.ticket_store_error == "OSError: disk full" for r in failed)


def test_live_label_only_on_the_real_mt5_path():
    src = (REPO / "scripts" / "host" / "live_eval_smoke.py").read_text()
    assert 'ticket_source="REPLAY"' in src and src.count('ticket_source="LIVE"') == 1
    assert de.run_daily_evaluation.__kwdefaults__["ticket_source"] == REPLAY
    with pytest.raises(ValueError):
        adapter.evaluation_from_canonical({"decision": "NO_TRADE"}, source=LEGACY)


# ------------------------------------------------------------------ legacy migration

def test_migrates_committed_evidence_journal_once(tmp_path):
    store = TicketStore(str(tmp_path / "store"))
    counts = migrate(str(EVIDENCE_JOURNAL), store)
    assert counts["read"] == {"manual": 8, "scan": 12, "fx": 8}
    assert counts["evaluations_written"] == counts["evaluation_groups"] == 12
    again = migrate(str(EVIDENCE_JOURNAL), store)
    assert again["evaluations_written"] == 0 and again["evaluations_already_present"] == 12
    recs = store.evaluations()
    assert {r["source"] for r in recs} == {LEGACY}
    assert all(r["spec_sha256"] is None and r["input_bar_hashes"] is None for r in recs)
    eur = next(r for r in recs if r["ticket_id"] == "ST_ASIAN_SWEEP_5R_V1|1.1.1|EURUSD|ASIAN_LONDON|2026-10-06")
    assert (eur["state"], eur["direction"], eur["entry"], eur["sl"]) == ("TICKET_BLOCKED", "LONG", 1.12097, 1.12024)
    assert [s["kind"] for s in eur["provenance"]["legacy_sources"]] == ["manual", "scan", "fx"]
    st = [r for r in recs if r["strategy"] == "SESSION_TRADE_V1@1"]
    assert len(st) == 4 and all(r["entry"] is None and r["ticket_id"] is None for r in st)   # null, not inferred
    index.rebuild(str(tmp_path / "store"))
    assert index.check(str(tmp_path / "store"))["ok"] is True


def test_migration_links_owner_decisions_and_moves_outcomes(tmp_path):
    journal = tmp_path / "journal"
    shutil.copytree(EVIDENCE_JOURNAL, journal)
    tid = "ST_ASIAN_SWEEP_5R_V1|1.1.1|EURUSD|ASIAN_LONDON|2026-10-06"
    manual = journal / "ticket_delivery" / "manual"
    (manual / "owner_decisions.jsonl").write_text(json.dumps({"ticket_id": tid, "decision": "SKIPPED"}) + "\n")
    (manual / "outcomes").mkdir()
    (manual / "outcomes" / "2026-10-06.jsonl").write_text(json.dumps(
        {"tag": "VIRTUAL_FORWARD", "ticket_id": tid, "resolved_at": "2026-10-06T16:00:00+00:00",
         "virtual_outcome": {"result": "SL"}}) + "\n")
    store = TicketStore(str(tmp_path / "store"))
    counts = migrate(str(journal), store)
    assert counts["owner_decision_refs"] == 1 and counts["outcomes_written"] == 1
    eur = next(r for r in store.evaluations() if r["ticket_id"] == tid)
    assert eur["owner_decision_ref"] == "ticket_delivery/manual/owner_decisions.jsonl#L1"
    (out,) = store.outcomes(tid)
    assert (out["source"], out["outcome_kind"], out["result"]) == (LEGACY, "VIRTUAL_FORWARD", "SL")
    assert migrate(str(journal), store)["outcomes_written"] == 0
    assert os.listdir(manual / "outcomes") == ["2026-10-06.jsonl"]                # journal read-only
