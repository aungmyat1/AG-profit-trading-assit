"""Tests for large_smc_research.live_ledger.LargeSMCSetupLedger
(AG_PROPOSAL_RUNTIME_LARGE_SMC_WATCH_AND_PERFORMANCE_HISTORY_V1): cross-run persistence
of historical_replay.orchestrator's SetupLedgerRow output. Reuses the same short real
EURUSD M5 slice tests/test_replay_orchestrator.py already uses, so no live MT5
connection is required to test the fold/upsert/terminal-freeze logic.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import os

import pytest

from historical_replay import HistoricalCandleStore, load_mt5_export_csv, resample, resample_broker_aligned
from historical_replay.orchestrator import run_replay
from large_smc_research.live_ledger import LargeSMCSetupLedger

REAL_CSV = r"D:\EURUSD_M5_202504211715_202607310000.csv"

pytestmark = pytest.mark.skipif(not os.path.exists(REAL_CSV), reason="real historical dataset not present on this machine")


@pytest.fixture(scope="module")
def replay_result():
    candles, report = load_mt5_export_csv(REAL_CSV, "EURUSD", "M5")
    store = HistoricalCandleStore()
    store.load_series("EURUSD", "M5", candles)
    for tf in ("M15", "H1"):
        store.load_series("EURUSD", tf, resample(candles, "M5", tf))
    for tf in ("H4", "D1"):
        store.load_series("EURUSD", tf, resample_broker_aligned(candles, report.broker_times, "M5", tf))
    start = candles[0].time + dt.timedelta(days=65)  # clear D1/H1/M5 warmup
    end = start + dt.timedelta(days=10)
    return run_replay(store, "EURUSD", candles, start, end)


def test_fresh_ledger_records_every_row_as_new(tmp_path, replay_result):
    ledger = LargeSMCSetupLedger(path=str(tmp_path / "setup_ledger.json"))
    counts = ledger.upsert_many(replay_result.setup_ledger)
    assert counts["new"] == len(replay_result.setup_ledger)
    assert counts["updated"] == 0
    assert ledger.count() == len(replay_result.setup_ledger)


def test_reobserving_identical_rows_is_a_noop(tmp_path, replay_result):
    ledger = LargeSMCSetupLedger(path=str(tmp_path / "setup_ledger.json"))
    ledger.upsert_many(replay_result.setup_ledger)
    counts_second_pass = ledger.upsert_many(replay_result.setup_ledger)
    assert counts_second_pass["new"] == 0
    assert counts_second_pass["updated"] == 0
    assert ledger.count() == len(replay_result.setup_ledger)  # no duplicates


def test_terminal_rows_are_never_overwritten(tmp_path, replay_result):
    terminal_rows = [r for r in replay_result.setup_ledger if r.terminal]
    if not terminal_rows:
        pytest.skip("this replay window produced no terminal setup rows to test against")
    ledger = LargeSMCSetupLedger(path=str(tmp_path / "setup_ledger.json"))
    ledger.upsert_many(replay_result.setup_ledger)

    tampered = dataclasses.replace(terminal_rows[0], final_state="TAMPERED_SHOULD_NOT_STICK")
    counts = ledger.upsert_many((tampered,))
    assert counts["skipped_terminal_frozen"] == 1
    stored = ledger.get(terminal_rows[0].setup_id)
    assert stored["final_state"] != "TAMPERED_SHOULD_NOT_STICK"


def test_no_row_is_ever_dropped_regardless_of_final_state(tmp_path, replay_result):
    """Failed/expired/invalidated setups must be preserved exactly like qualified
    ones -- required for honest performance research (task section 21)."""
    ledger = LargeSMCSetupLedger(path=str(tmp_path / "setup_ledger.json"))
    ledger.upsert_many(replay_result.setup_ledger)
    stored_ids = set(ledger.all().keys())
    assert stored_ids == {row.setup_id for row in replay_result.setup_ledger}
