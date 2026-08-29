"""Tests for surveillance: state progression, duplicate-poll suppression, multi-symbol
independence. Builds SMCConditionalEntryAnalysis snapshots directly (not through
daytrading_runtime/conditional_entry_snapshot.py's MT5-fetching wrapper) -- surveillance
only ever consumes the already-frozen contract, so these fixtures exercise exactly that
boundary.
"""
from __future__ import annotations

import datetime as dt

import pytest

from entry_confirmation.entry_models_v1 import EConditionResult, SMCConditionalEntryAnalysis, SMCEntryCombinationResult
from entry_confirmation.m1_character_change_inducement import M1Result
from entry_confirmation.m2_supply_demand_shift import M2Result
from entry_confirmation.m3_sweep_drop_pump import M3Result
from surveillance import compact_line, detailed_report, poll_symbols, update_surveillance
from surveillance.models import (
    EVENT_CONTEXT_QUALIFIED,
    EVENT_ENTRY_READY,
    EVENT_H1_REACTION_CONFIRMED,
    EVENT_M_CONFIRMATION_DEVELOPING,
    EVENT_REFERENCE_TOUCHED,
    EVENT_SETUP_INVALIDATED,
)

UTC = dt.timezone.utc


class FakeStore:
    """Minimal in-memory stand-in for runtime_state.store.JsonKeyValueStore -- same
    get/put interface, no filesystem."""

    def __init__(self):
        self._data = {}

    def get(self, key):
        return self._data.get(key)

    def put(self, key, value):
        self._data[key] = value


def _empty_e(name):
    return EConditionResult(entry_condition=name, symbol="EURUSD")


def _no_context_analysis(snapshot_time):
    return SMCConditionalEntryAnalysis(
        symbol="EURUSD", snapshot_time=snapshot_time,
        e_conditions={"E1": _empty_e("E1"), "E2": _empty_e("E2"), "E3": _empty_e("E3")},
        m_maneuvers={"M1": (), "M2": (), "M3": ()}, combinations=(),
    )


def _developing_analysis(snapshot_time, touch_status="WAITING_H1_REACTION", reaction_status="WAITING_H1_REACTION",
                          eligible=False, m1_state="NOT_APPLICABLE"):
    e2 = EConditionResult(entry_condition="E2", symbol="EURUSD", direction="SHORT",
                           touch_status=touch_status, reaction_status=reaction_status,
                           eligible_for_confirmation=eligible)
    m1 = M1Result(symbol="EURUSD", entry_condition="E2", direction="SHORT", state=m1_state)
    return SMCConditionalEntryAnalysis(
        symbol="EURUSD", snapshot_time=snapshot_time,
        e_conditions={"E1": _empty_e("E1"), "E2": e2, "E3": _empty_e("E3")},
        m_maneuvers={"M1": (m1,), "M2": (), "M3": ()}, combinations=(),
    )


def _ready_analysis(snapshot_time):
    e2 = EConditionResult(entry_condition="E2", symbol="EURUSD", direction="SHORT",
                           touch_status="WAITING_H1_REACTION", reaction_status="HTF_QUALIFIED",
                           eligible_for_confirmation=True)
    m1 = M1Result(symbol="EURUSD", entry_condition="E2", direction="SHORT", state="READY")
    combo = SMCEntryCombinationResult(combination="E2M1", entry_condition="E2", maneuver="M1",
                                       symbol="EURUSD", direction="SHORT", state="READY")
    return SMCConditionalEntryAnalysis(
        symbol="EURUSD", snapshot_time=snapshot_time,
        e_conditions={"E1": _empty_e("E1"), "E2": e2, "E3": _empty_e("E3")},
        m_maneuvers={"M1": (m1,), "M2": (), "M3": ()}, combinations=(combo,),
    )


def _invalidated_analysis(snapshot_time):
    e2 = EConditionResult(entry_condition="E2", symbol="EURUSD", direction="SHORT",
                           touch_status="WAITING_H1_REACTION", reaction_status="HTF_QUALIFIED",
                           eligible_for_confirmation=True)
    m1 = M1Result(symbol="EURUSD", entry_condition="E2", direction="SHORT", state="INVALIDATED")
    combo = SMCEntryCombinationResult(combination="E2M1", entry_condition="E2", maneuver="M1",
                                       symbol="EURUSD", direction="SHORT", state="INVALIDATED")
    return SMCConditionalEntryAnalysis(
        symbol="EURUSD", snapshot_time=snapshot_time,
        e_conditions={"E1": _empty_e("E1"), "E2": e2, "E3": _empty_e("E3")},
        m_maneuvers={"M1": (m1,), "M2": (), "M3": ()}, combinations=(combo,),
    )


# --------------------------------------------------------------------------- state progression

def test_no_context_to_context_qualified_to_ready_to_invalidated():
    store = FakeStore()
    t0 = dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC)

    u0 = update_surveillance(_no_context_analysis(t0), store)
    assert u0.events == ()  # first poll ever: no "prior state" to diff against, nothing changed FROM

    t1 = t0 + dt.timedelta(minutes=15)
    u1 = update_surveillance(_developing_analysis(t1, touch_status="WAITING_H1_REACTION",
                                                    reaction_status="WAITING_H1_REACTION", eligible=False), store)
    types1 = {e.event_type for e in u1.events}
    assert EVENT_REFERENCE_TOUCHED in types1

    t2 = t1 + dt.timedelta(minutes=15)
    u2 = update_surveillance(_developing_analysis(t2, touch_status="WAITING_H1_REACTION",
                                                    reaction_status="HTF_QUALIFIED", eligible=True), store)
    types2 = {e.event_type for e in u2.events}
    assert EVENT_H1_REACTION_CONFIRMED in types2
    assert EVENT_CONTEXT_QUALIFIED in types2

    t3 = t2 + dt.timedelta(minutes=15)
    u3 = update_surveillance(_developing_analysis(t3, touch_status="WAITING_H1_REACTION",
                                                    reaction_status="HTF_QUALIFIED", eligible=True,
                                                    m1_state="WAITING_M5_ENTRY"), store)
    types3 = {e.event_type for e in u3.events}
    assert EVENT_M_CONFIRMATION_DEVELOPING in types3

    t4 = t3 + dt.timedelta(minutes=15)
    u4 = update_surveillance(_ready_analysis(t4), store)
    types4 = {e.event_type for e in u4.events}
    assert EVENT_ENTRY_READY in types4
    assert u4.record["ready_combinations"] == ["E2M1"]

    t5 = t4 + dt.timedelta(minutes=15)
    u5 = update_surveillance(_invalidated_analysis(t5), store)
    types5 = {e.event_type for e in u5.events}
    assert EVENT_SETUP_INVALIDATED in types5
    assert u5.record["ready_combinations"] == []


# --------------------------------------------------------------------------- duplicate-poll suppression

def test_identical_repeated_poll_emits_no_events():
    store = FakeStore()
    t0 = dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
    analysis = _ready_analysis(t0)

    first = update_surveillance(analysis, store)
    assert first.events != ()  # first-ever poll: transitions from the implicit empty prior state

    second = update_surveillance(analysis, store)
    assert second.events == ()  # identical state -- nothing changed, nothing emitted

    third = update_surveillance(analysis, store)
    assert third.events == ()


# --------------------------------------------------------------------------- multi-symbol independence

def test_multi_symbol_polling_keeps_separate_state():
    store = FakeStore()
    t0 = dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC)

    eurusd_ready = _ready_analysis(t0)
    gbpusd_none = SMCConditionalEntryAnalysis(
        symbol="GBPUSD", snapshot_time=t0,
        e_conditions={"E1": EConditionResult(entry_condition="E1", symbol="GBPUSD"),
                      "E2": EConditionResult(entry_condition="E2", symbol="GBPUSD"),
                      "E3": EConditionResult(entry_condition="E3", symbol="GBPUSD")},
        m_maneuvers={"M1": (), "M2": (), "M3": ()}, combinations=(),
    )

    results = poll_symbols({"EURUSD": eurusd_ready, "GBPUSD": gbpusd_none}, store)
    assert results["EURUSD"].record["ready_combinations"] == ["E2M1"]
    assert results["GBPUSD"].record["ready_combinations"] == []
    assert store.get("EURUSD")["symbol"] == "EURUSD"
    assert store.get("GBPUSD")["symbol"] == "GBPUSD"


# --------------------------------------------------------------------------- reporting

def test_compact_line_no_context():
    store = FakeStore()
    update = update_surveillance(_no_context_analysis(dt.datetime(2026, 1, 5, tzinfo=UTC)), store)
    assert compact_line(update.record) == "EURUSD | NO ACTIVE E CONDITION"


def test_compact_line_ready():
    store = FakeStore()
    update = update_surveillance(_ready_analysis(dt.datetime(2026, 1, 5, tzinfo=UTC)), store)
    line = compact_line(update.record)
    assert line.startswith("EURUSD | E2M1 SHORT READY")


def test_detailed_report_lists_ready_combination():
    store = FakeStore()
    update = update_surveillance(_ready_analysis(dt.datetime(2026, 1, 5, tzinfo=UTC)), store)
    report = detailed_report(update.record)
    assert "READY COMBINATIONS" in report
    assert "E2M1" in report


def test_history_is_bounded():
    from surveillance.models import MAX_HISTORY_ENTRIES

    store = FakeStore()
    t = dt.datetime(2026, 1, 5, tzinfo=UTC)
    for i in range(MAX_HISTORY_ENTRIES + 10):
        state = "WAITING_M5_ENTRY" if i % 2 == 0 else "WAITING_M5_CONFIRMATION"
        update_surveillance(_developing_analysis(t + dt.timedelta(minutes=i), eligible=True,
                                                   reaction_status="HTF_QUALIFIED", m1_state=state), store)
    record = store.get("EURUSD")
    assert len(record["history"]) <= MAX_HISTORY_ENTRIES
