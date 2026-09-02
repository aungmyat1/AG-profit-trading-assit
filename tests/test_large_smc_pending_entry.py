"""ST_LARGE_SMC_V1 post-READY pending-entry lifecycle (large_smc_research/pending_entry.py).

Exercises the thin adapter over the already-existing, already-tested
`historical_replay.fill_simulator.simulate_fill` -- no new fill/invalidation logic here,
only occurrence-identity preservation across the call. See `tests/test_fill_simulator.py`
for the underlying state-machine's own coverage.
"""
from __future__ import annotations

import datetime as dt

from large_smc_research.decision import LargeSMCResearchDecision
from large_smc_research.pending_entry import (
    STATUS_FILLED,
    STATUS_INTRABAR_AMBIGUOUS,
    STATUS_INVALIDATED_BEFORE_FILL,
    STATUS_NO_ENTRY_CONTRACT,
    STATUS_UNFILLED_AS_OF_DATA_END,
    simulate_pending_entry,
)
from strategy_engine.session import Candle

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 1, 5, 5, 0, tzinfo=UTC)


def _candle(t, o, h, l, c):
    return Candle(time=t, open=o, high=h, low=l, close=c, volume=1.0)


def _blocked_decision(direction="LONG", entry_low=1.1000, entry_high=1.1010, entry_price=1.1005,
                       invalidation_price=1.0990, occurrence_id="OCCURRENCE-abc"):
    return LargeSMCResearchDecision(
        symbol="EURUSD", evaluation_timestamp=T0, combination="E1M2", direction=direction,
        candidate_occurrence_id=occurrence_id, setup_family_id="SETUP-EURUSD-E1M2-xyz",
        eligibility_interval_id="INTERVAL-xyz", entry_array="FVG", entry_price=entry_price,
        entry_low=entry_low, entry_high=entry_high, structural_invalidation_price=invalidation_price,
        state="BLOCKED",
    )


def test_fill_before_invalidation():
    decision = _blocked_decision()
    candles = [_candle(T0 + dt.timedelta(minutes=5 * i), 1.1030, 1.1030, 1.0995, 1.1005) for i in range(1, 3)]
    outcome = simulate_pending_entry(decision, candles)
    assert outcome.status == STATUS_FILLED
    assert outcome.candidate_occurrence_id == "OCCURRENCE-abc"
    assert outcome.setup_family_id == "SETUP-EURUSD-E1M2-xyz"


def test_invalidated_before_fill():
    decision = _blocked_decision()
    candles = [_candle(T0 + dt.timedelta(minutes=5), 1.0995, 1.0996, 1.0985, 1.0990)]  # dips through invalidation, stays below the entry zone (1.1000-1.1010) entirely
    outcome = simulate_pending_entry(decision, candles)
    assert outcome.status == STATUS_INVALIDATED_BEFORE_FILL


def test_unfilled_as_of_data_end_is_not_a_fabricated_expiry():
    decision = _blocked_decision()
    candles = [_candle(T0 + dt.timedelta(minutes=5), 1.1030, 1.1035, 1.1025, 1.1030)]  # never reaches entry or invalidation
    outcome = simulate_pending_entry(decision, candles)
    assert outcome.status == STATUS_UNFILLED_AS_OF_DATA_END


def test_same_bar_entry_and_invalidation_is_ambiguous_not_assumed_win():
    decision = _blocked_decision()
    candles = [_candle(T0 + dt.timedelta(minutes=5), 1.1020, 1.1020, 1.0985, 1.0990)]  # touches both entry zone and invalidation in one bar
    outcome = simulate_pending_entry(decision, candles)
    assert outcome.status == STATUS_INTRABAR_AMBIGUOUS


def test_missing_entry_geometry_fails_closed():
    decision = _blocked_decision(entry_low=None, entry_high=None, entry_price=None)
    outcome = simulate_pending_entry(decision, [])
    assert outcome.status == STATUS_NO_ENTRY_CONTRACT


def test_occurrence_identity_preserved_end_to_end():
    decision = _blocked_decision(occurrence_id="OCCURRENCE-unique-1")
    candles = [_candle(T0 + dt.timedelta(minutes=5), 1.1030, 1.1030, 1.1000, 1.1005)]
    outcome = simulate_pending_entry(decision, candles)
    assert outcome.candidate_occurrence_id == "OCCURRENCE-unique-1"
    assert outcome.combination == "E1M2"
    assert outcome.ready_time == T0


def test_two_independent_occurrences_never_collapse():
    d1 = _blocked_decision(occurrence_id="OCCURRENCE-1")
    d2 = _blocked_decision(occurrence_id="OCCURRENCE-2")
    candles = [_candle(T0 + dt.timedelta(minutes=5), 1.1030, 1.1030, 1.1000, 1.1005)]
    o1 = simulate_pending_entry(d1, candles)
    o2 = simulate_pending_entry(d2, candles)
    assert o1.candidate_occurrence_id != o2.candidate_occurrence_id


def test_short_direction_mirrors_correctly():
    decision = _blocked_decision(direction="SHORT", entry_low=1.0990, entry_high=1.1000,
                                  entry_price=1.0995, invalidation_price=1.1010)
    candles = [_candle(T0 + dt.timedelta(minutes=5), 1.0985, 1.0995, 1.0980, 1.0990)]
    outcome = simulate_pending_entry(decision, candles)
    assert outcome.status == STATUS_FILLED
