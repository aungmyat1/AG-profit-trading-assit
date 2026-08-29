"""Tests for historical_replay.orchestrator (historical-validation continuation spec
sections 13-26, 54-58): chronological replay, warmup distinction, determinism, and
setup-ledger/funnel structural correctness. Uses a short real slice of the actual
EURUSD M5 export this phase ingested (not a full-history run -- that is a separate,
long-running batch job; see scripts/run_historical_replay.py) so these tests run in a
few seconds, not hours.
"""
from __future__ import annotations

import datetime as dt
import os

import pytest

from entry_confirmation.entry_models_v1 import COMBINATIONS, ENTRY_CONDITIONS, MANEUVERS
from historical_replay import HistoricalCandleStore, load_mt5_export_csv, resample, resample_broker_aligned
from historical_replay.orchestrator import run_replay

REAL_CSV = r"D:\EURUSD_M5_202504211715_202607310000.csv"

pytestmark = pytest.mark.skipif(not os.path.exists(REAL_CSV), reason="real historical dataset not present on this machine")


@pytest.fixture(scope="module")
def loaded_store():
    candles, report = load_mt5_export_csv(REAL_CSV, "EURUSD", "M5")
    store = HistoricalCandleStore()
    store.load_series("EURUSD", "M5", candles)
    for tf in ("M15", "H1"):
        store.load_series("EURUSD", tf, resample(candles, "M5", tf))
    for tf in ("H4", "D1"):
        # Broker-day-anchored -- see historical_replay.resampler module docstring.
        store.load_series("EURUSD", tf, resample_broker_aligned(candles, report.broker_times, "M5", tf))
    return store, candles


def test_replay_distinguishes_warmup_from_valid_steps(loaded_store):
    store, candles = loaded_store
    start = candles[0].time  # right at the start of the file -- no D1/H1/M5 warmup satisfied yet
    end = start + dt.timedelta(hours=2)
    result = run_replay(store, "EURUSD", candles, start, end)
    assert result.steps > 0
    assert result.warmup_steps == result.steps  # far too little history this early for any valid step
    assert result.valid_steps == 0


def test_replay_produces_valid_steps_after_warmup(loaded_store):
    store, candles = loaded_store
    start = candles[0].time + dt.timedelta(days=120)  # well past D1/H1/M5 warmup requirements
    end = start + dt.timedelta(hours=2)  # ~24 M5 steps
    result = run_replay(store, "EURUSD", candles, start, end)
    assert result.steps == 24
    assert result.warmup_steps == 0
    assert result.valid_steps == 24


def test_replay_is_deterministic(loaded_store):
    store, candles = loaded_store
    start = candles[0].time + dt.timedelta(days=120)
    end = start + dt.timedelta(hours=1)  # ~12 steps, keep it fast

    r1 = run_replay(store, "EURUSD", candles, start, end)
    r2 = run_replay(store, "EURUSD", candles, start, end)

    assert r1.steps == r2.steps
    assert r1.valid_steps == r2.valid_steps
    assert r1.per_combination == r2.per_combination
    assert r1.per_e == r2.per_e
    assert r1.per_m == r2.per_m
    assert len(r1.setup_ledger) == len(r2.setup_ledger)
    assert {r.setup_id for r in r1.setup_ledger} == {r.setup_id for r in r2.setup_ledger}


def test_funnel_reports_all_nine_combinations_even_at_zero(loaded_store):
    """Spec section 23/35: do not omit zero-occurrence combinations."""
    store, candles = loaded_store
    start = candles[0].time + dt.timedelta(days=120)
    end = start + dt.timedelta(minutes=30)  # tiny window, likely zero setups
    result = run_replay(store, "EURUSD", candles, start, end)
    assert set(result.per_combination.keys()) == set(COMBINATIONS)
    assert set(result.per_e.keys()) == set(ENTRY_CONDITIONS)
    assert set(result.per_m.keys()) == set(MANEUVERS)


def test_no_identity_collisions_on_real_replay_window(loaded_store):
    """Spec section 21: the setup-identity fix must hold under real replay data, not
    just fixtures."""
    store, candles = loaded_store
    start = candles[0].time + dt.timedelta(days=120)
    end = start + dt.timedelta(hours=6)
    result = run_replay(store, "EURUSD", candles, start, end)
    assert result.identity_collisions == 0
