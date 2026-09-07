"""Tests for large_smc_research.live_ledger.LargeSMCSetupLedger
(AG_PROPOSAL_RUNTIME_LARGE_SMC_WATCH_AND_PERFORMANCE_HISTORY_V1, hardened in
AG_LARGE_SMC_VERSION_HARDENING_PERFORMANCE_AND_POST_CHECKPOINT_ACTIVATION_V1):
strategy-identity binding, version-mismatch fail-closed behavior, idempotency, and
incremental-rerun occurrence stability.

Uses lightweight, hand-built SetupLedgerRow fixtures for the fast, numerous hardening
tests (this logic only depends on SetupLedgerRow's shape, not on where the rows came
from) rather than a real multi-day run_replay call -- a genuine replay long enough to
reliably produce non-empty setup_ledger rows takes on the order of tens of minutes to
hours (see scripts/run_large_smc_outcome_lifecycle_check.py's own "~90-minute
full-month replay" note), far too slow for a unit-test suite. A single short (6-hour,
matching tests/test_replay_orchestrator.py's own fast window) real-replay smoke test
below proves the ledger correctly consumes genuine `ReplayResult.setup_ledger` output
end-to-end, without asserting on its (possibly zero) row count.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import os

import pytest

from historical_replay import HistoricalCandleStore, load_mt5_export_csv, resample, resample_broker_aligned
from historical_replay.orchestrator import SetupLedgerRow, run_replay
from large_smc_research.decision import STRATEGY_ID
from large_smc_research.engine import STRATEGY_VERSION
from large_smc_research.live_ledger import LargeSMCSetupLedger, StrategyIdentityMismatch

_T0 = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


def _row(setup_id, final_state="WATCH_TEST_STATE", terminal=False, last_seen_time=_T0):
    return SetupLedgerRow(
        setup_id=setup_id, symbol="EURUSD", combination="E1xM1", entry_condition="E1", maneuver="M1",
        direction="LONG", reference_key="ref", first_seen_time=_T0, last_seen_time=last_seen_time,
        final_state=final_state, terminal=terminal,
    )


def _rows(n, terminal_ids=()):
    return tuple(_row(f"s{i}", terminal=(f"s{i}" in terminal_ids)) for i in range(n))


def _rows_named(names, terminal_ids=()):
    return tuple(_row(name, terminal=(name in terminal_ids)) for name in names)


def test_fresh_ledger_records_every_row_as_new(tmp_path):
    rows = _rows(5)
    ledger = LargeSMCSetupLedger(path=str(tmp_path / "setup_ledger.json"))
    counts = ledger.upsert_many(rows)
    assert counts["new"] == 5
    assert counts["updated"] == 0
    assert ledger.count() == 5


def test_reobserving_identical_rows_is_a_noop(tmp_path):
    rows = _rows(5)
    ledger = LargeSMCSetupLedger(path=str(tmp_path / "setup_ledger.json"))
    ledger.upsert_many(rows)
    counts_second_pass = ledger.upsert_many(rows)
    assert counts_second_pass["new"] == 0
    assert counts_second_pass["updated"] == 0
    assert ledger.count() == 5  # no duplicates


def test_repeated_runs_do_not_duplicate_across_three_passes(tmp_path):
    rows = _rows(5)
    ledger = LargeSMCSetupLedger(path=str(tmp_path / "setup_ledger.json"))
    for _ in range(3):
        ledger.upsert_many(rows)
    assert ledger.count() == 5  # never N -> 2N -> 3N


def test_terminal_rows_are_never_overwritten(tmp_path):
    rows = _rows(3, terminal_ids=("s0",))
    ledger = LargeSMCSetupLedger(path=str(tmp_path / "setup_ledger.json"))
    ledger.upsert_many(rows)

    tampered = dataclasses.replace(rows[0], final_state="TAMPERED_SHOULD_NOT_STICK")
    counts = ledger.upsert_many((tampered,))
    assert counts["skipped_terminal_frozen"] == 1
    stored = ledger.get("s0")
    assert stored["final_state"] != "TAMPERED_SHOULD_NOT_STICK"


def test_nonterminal_state_can_progress(tmp_path):
    """A row that has NOT reached a terminal state must be free to update -- this store
    is an upsert state store, not a fully immutable ledger."""
    rows = _rows(3)  # none terminal
    ledger = LargeSMCSetupLedger(path=str(tmp_path / "setup_ledger.json"))
    ledger.upsert_many(rows)

    progressed = dataclasses.replace(rows[0], last_seen_time=rows[0].last_seen_time + dt.timedelta(minutes=5))
    counts = ledger.upsert_many((progressed,))
    assert counts["updated"] == 1
    stored = ledger.get("s0")
    assert stored["last_seen_time"] == progressed.last_seen_time.isoformat()


def test_no_row_is_ever_dropped_regardless_of_final_state(tmp_path):
    rows = _rows(4, terminal_ids=("s1", "s3"))
    ledger = LargeSMCSetupLedger(path=str(tmp_path / "setup_ledger.json"))
    ledger.upsert_many(rows)
    stored = ledger.all()
    assert len(stored) == 4
    stored_setup_ids = {record["setup_id"] for record in stored.values()}
    assert stored_setup_ids == {row.setup_id for row in rows}


def test_persisted_row_has_strategy_identity(tmp_path):
    ledger = LargeSMCSetupLedger(path=str(tmp_path / "setup_ledger.json"))
    ledger.upsert_many(_rows(1))
    row = next(iter(ledger.all().values()))
    assert row["strategy_id"] == STRATEGY_ID
    assert row["strategy_version"] == STRATEGY_VERSION


def test_persisted_row_has_application_release(tmp_path):
    ledger = LargeSMCSetupLedger(path=str(tmp_path / "setup_ledger.json"))
    ledger.upsert_many(_rows(1))
    row = next(iter(ledger.all().values()))
    assert row["application_release"] == "AG_TRADE_ASSISTANT_V1_0_3"


def test_persisted_row_has_evidence_basis(tmp_path):
    ledger = LargeSMCSetupLedger(path=str(tmp_path / "setup_ledger.json"))
    ledger.upsert_many(_rows(1))
    row = next(iter(ledger.all().values()))
    assert row["evidence_basis"] == "FORWARD_RESEARCH_DAILY_BATCH"


def test_version_mismatch_fails_closed(tmp_path):
    path = str(tmp_path / "setup_ledger.json")
    v107_ledger = LargeSMCSetupLedger(path=path, strategy_version="1.0.7")
    v107_ledger.upsert_many(_rows(3))

    v108_ledger = LargeSMCSetupLedger(path=path, strategy_version="1.0.8")
    rows_before = v108_ledger.count()
    with pytest.raises(StrategyIdentityMismatch):
        v108_ledger.upsert_many(_rows(3))
    # Fail closed, all-or-nothing: nothing written by the rejected call.
    assert v108_ledger.count() == rows_before


def test_incremental_rerun_preserves_existing_occurrences(tmp_path):
    """Simulates what a real daily batch does: run #2 covers everything run #1 saw plus
    more (some newly discovered, some historical rows now further progressed)."""
    ledger = LargeSMCSetupLedger(path=str(tmp_path / "setup_ledger.json"))

    day1_rows = _rows_named(("s0", "s1", "s2"), terminal_ids=("s0",))  # s0 goes terminal on day 1
    ledger.upsert_many(day1_rows)
    ids_after_day1 = set(ledger.all().keys())
    terminal_snapshot_after_day1 = ledger.get("s0")

    # day 2 re-observes s0-s2 (unchanged) and newly discovers s3, s4
    day2_rows = day1_rows + _rows_named(("s3", "s4"))
    counts = ledger.upsert_many(day2_rows)

    ids_after_day2 = set(ledger.all().keys())
    assert ids_after_day1.issubset(ids_after_day2), "no historical occurrence may disappear on a later rerun"
    assert {"s3", "s4"}.issubset({k.rsplit(":", 1)[-1] for k in ids_after_day2})
    assert counts["new"] == 2  # only s3, s4
    assert ledger.get("s0") == terminal_snapshot_after_day1, "a terminal row must never change on a later rerun"


REAL_CSV = r"D:\EURUSD_M5_202504211715_202607310000.csv"


@pytest.mark.skipif(not os.path.exists(REAL_CSV), reason="real historical dataset not present on this machine")
def test_ledger_consumes_genuine_replay_result_without_error(tmp_path):
    """Smoke test only: proves upsert_many works against real ReplayResult.setup_ledger
    shape end-to-end. Uses the same fast 6-hour window
    tests/test_replay_orchestrator.py::test_no_identity_collisions_on_real_replay_window
    already uses -- does NOT assert on row count (a 6-hour window may legitimately
    produce zero setup rows)."""
    candles, report = load_mt5_export_csv(REAL_CSV, "EURUSD", "M5")
    store = HistoricalCandleStore()
    store.load_series("EURUSD", "M5", candles)
    for tf in ("M15", "H1"):
        store.load_series("EURUSD", tf, resample(candles, "M5", tf))
    for tf in ("H4", "D1"):
        store.load_series("EURUSD", tf, resample_broker_aligned(candles, report.broker_times, "M5", tf))
    start = candles[0].time + dt.timedelta(days=120)
    end = start + dt.timedelta(hours=6)
    result = run_replay(store, "EURUSD", candles, start, end)

    ledger = LargeSMCSetupLedger(path=str(tmp_path / "setup_ledger.json"))
    counts = ledger.upsert_many(result.setup_ledger)
    assert counts["new"] == len(result.setup_ledger)
    assert ledger.count() == len(result.setup_ledger)
