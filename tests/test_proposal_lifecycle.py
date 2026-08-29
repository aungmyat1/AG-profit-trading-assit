"""Tests for proposals.lifecycle: CREATED/STILL_VALID/UPDATED/INVALIDATED, identity
stability (setup_id/proposal_id/snapshot_id per spec section 46), and deduplication
(repeated polling of the same setup must not re-emit CREATED).
"""
from __future__ import annotations

import datetime as dt

import pytest

from entry_confirmation.entry_models_v1 import EConditionResult, SMCConditionalEntryAnalysis, SMCEntryCombinationResult
from entry_confirmation.m1_character_change_inducement import M1Result
from proposals import (
    LIFECYCLE_CREATED,
    LIFECYCLE_INVALIDATED,
    LIFECYCLE_STILL_VALID,
    LIFECYCLE_UPDATED,
    generate_proposals,
    proposal_id_for,
    setup_id,
    snapshot_id,
    update_proposal_lifecycle,
)

UTC = dt.timezone.utc


class FakeStore:
    def __init__(self):
        self._data = {}

    def get(self, key):
        return self._data.get(key)

    def put(self, key, value):
        self._data[key] = value


def _analysis(state="READY", entry_price=1.1000, snapshot_time=None, invalidation_price=1.1060):
    e2 = EConditionResult(entry_condition="E2", symbol="EURUSD", direction="SHORT", eligible_for_confirmation=True)
    combo = SMCEntryCombinationResult(combination="E2M1", entry_condition="E2", maneuver="M1", symbol="EURUSD",
                                       direction="SHORT", confirmation_timeframe="M5",
                                       entry_array="FVG", entry_price=entry_price, state=state,
                                       invalidation="INVALIDATED" if state == "INVALIDATED" else None,
                                       invalidation_price=invalidation_price,
                                       invalidation_source_type="INDUCEMENT_LEVEL", invalidation_trigger="LIVE_PRICE")
    return SMCConditionalEntryAnalysis(
        symbol="EURUSD", snapshot_time=snapshot_time or dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
        e_conditions={"E1": EConditionResult(entry_condition="E1", symbol="EURUSD"), "E2": e2,
                      "E3": EConditionResult(entry_condition="E3", symbol="EURUSD")},
        m_maneuvers={"M1": (), "M2": (), "M3": ()}, combinations=(combo,),
    )


# --------------------------------------------------------------------------- identity

def test_setup_id_pure_function_of_symbol_combination_direction():
    a = setup_id("EURUSD", "E2M1", "SHORT")
    b = setup_id("EURUSD", "E2M1", "SHORT")
    assert a == b


def test_setup_id_differs_by_symbol_combination_direction():
    base = setup_id("EURUSD", "E2M1", "SHORT")
    assert setup_id("GBPUSD", "E2M1", "SHORT") != base
    assert setup_id("EURUSD", "E2M2", "SHORT") != base
    assert setup_id("EURUSD", "E2M1", "LONG") != base


def test_proposal_id_stable_for_same_setup_id():
    setup = setup_id("EURUSD", "E2M1", "SHORT")
    assert proposal_id_for(setup) == proposal_id_for(setup)


def test_snapshot_id_differs_across_polls():
    t0 = dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
    t1 = t0 + dt.timedelta(minutes=15)
    assert snapshot_id("EURUSD", t0) != snapshot_id("EURUSD", t1)


def test_generate_proposals_setup_id_stable_across_polls_even_as_price_moves():
    a1 = _analysis(entry_price=1.1000, snapshot_time=dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC))
    a2 = _analysis(entry_price=1.1005, snapshot_time=dt.datetime(2026, 1, 5, 10, 15, tzinfo=UTC))
    p1 = generate_proposals(a1)[0]
    p2 = generate_proposals(a2)[0]
    assert p1.setup_id == p2.setup_id
    assert p1.proposal_id == p2.proposal_id
    assert p1.snapshot_id != p2.snapshot_id


# --------------------------------------------------------------------------- lifecycle transitions

def test_created_then_still_valid_then_updated_then_invalidated():
    store = FakeStore()
    t0 = dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC)

    u1 = update_proposal_lifecycle(_analysis(entry_price=1.1000, snapshot_time=t0), store)
    assert len(u1) == 1
    assert u1[0].lifecycle == LIFECYCLE_CREATED
    setup = u1[0].setup_id

    t1 = t0 + dt.timedelta(minutes=15)
    u2 = update_proposal_lifecycle(_analysis(entry_price=1.1000, snapshot_time=t1), store)
    assert u2[0].lifecycle == LIFECYCLE_STILL_VALID
    assert u2[0].setup_id == setup

    t2 = t1 + dt.timedelta(minutes=15)
    u3 = update_proposal_lifecycle(_analysis(entry_price=1.1010, snapshot_time=t2), store)
    assert u3[0].lifecycle == LIFECYCLE_UPDATED
    assert "entry_reference" in u3[0].changed_fields

    t3 = t2 + dt.timedelta(minutes=15)
    u4 = update_proposal_lifecycle(_analysis(state="INVALIDATED", snapshot_time=t3), store)
    assert len(u4) == 1
    assert u4[0].lifecycle == LIFECYCLE_INVALIDATED
    assert u4[0].proposal.invalidation_price == pytest.approx(1.1060)
    assert u4[0].setup_id == setup


def test_no_duplicate_created_event_on_repeated_identical_poll():
    store = FakeStore()
    analysis = _analysis()
    first = update_proposal_lifecycle(analysis, store)
    assert first[0].lifecycle == LIFECYCLE_CREATED
    second = update_proposal_lifecycle(analysis, store)
    assert second[0].lifecycle == LIFECYCLE_STILL_VALID
    third = update_proposal_lifecycle(analysis, store)
    assert third[0].lifecycle == LIFECYCLE_STILL_VALID


def test_no_transition_reported_when_setup_never_tracked_before():
    """An INVALIDATED combination for a setup that was never previously seen as an
    active proposal produces no lifecycle event -- never fabricate a transition."""
    store = FakeStore()
    updates = update_proposal_lifecycle(_analysis(state="INVALIDATED"), store)
    assert updates == ()


def test_invalidated_proposal_becomes_terminal_further_polls_produce_no_repeat_event():
    store = FakeStore()
    t0 = dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
    update_proposal_lifecycle(_analysis(snapshot_time=t0), store)
    t1 = t0 + dt.timedelta(minutes=15)
    first_invalid = update_proposal_lifecycle(_analysis(state="INVALIDATED", snapshot_time=t1), store)
    assert len(first_invalid) == 1

    t2 = t1 + dt.timedelta(minutes=15)
    second_invalid = update_proposal_lifecycle(_analysis(state="INVALIDATED", snapshot_time=t2), store)
    assert second_invalid == ()  # already terminal -- no repeat event


def test_re_ready_after_terminal_is_a_fresh_created():
    store = FakeStore()
    t0 = dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
    update_proposal_lifecycle(_analysis(snapshot_time=t0), store)
    t1 = t0 + dt.timedelta(minutes=15)
    update_proposal_lifecycle(_analysis(state="INVALIDATED", snapshot_time=t1), store)

    t2 = t1 + dt.timedelta(minutes=15)
    reemerged = update_proposal_lifecycle(_analysis(snapshot_time=t2), store)
    assert reemerged[0].lifecycle == LIFECYCLE_CREATED
