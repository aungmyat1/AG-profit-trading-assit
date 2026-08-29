"""Cross-layer consistency (spec section 61's critical invariant): given ONE
SMCConditionalEntryAnalysis snapshot, surveillance's READY combination, proposals'
generated proposal, and visual explanation's highlighted combination must all agree --
same combination, same direction, same evidence. All three consume the identical
analysis object; none re-derives anything independently.
"""
from __future__ import annotations

import datetime as dt

import pytest

from entry_confirmation.entry_models_v1 import EConditionResult, SMCConditionalEntryAnalysis, SMCEntryCombinationResult
from entry_confirmation.m1_character_change_inducement import M1Result
from proposals import generate_proposals
from surveillance import update_surveillance
from visual_explanation import build_visual_explanation

UTC = dt.timezone.utc


class FakeStore:
    def __init__(self):
        self._data = {}

    def get(self, key):
        return self._data.get(key)

    def put(self, key, value):
        self._data[key] = value


def _snapshot():
    e2 = EConditionResult(entry_condition="E2", symbol="EURUSD", direction="SHORT",
                           reference_timeframe="H1", reference_type="BEARISH_OB",
                           reference_low=1.0990, reference_high=1.1010,
                           touch_status="WAITING_H1_REACTION", reaction_status="HTF_QUALIFIED",
                           eligible_for_confirmation=True)
    e3 = EConditionResult(entry_condition="E3", symbol="EURUSD")  # not applicable this snapshot
    e1 = EConditionResult(entry_condition="E1", symbol="EURUSD")

    m1 = M1Result(symbol="EURUSD", entry_condition="E2", direction="SHORT", state="READY",
                   entry_array_low=1.0980, entry_array_high=1.0995, entry_array_type="FVG")
    combo = SMCEntryCombinationResult(combination="E2M1", entry_condition="E2", maneuver="M1", symbol="EURUSD",
                                       direction="SHORT", confirmation_timeframe="M5",
                                       entry_array="FVG", entry_price=1.09875, state="READY")

    return SMCConditionalEntryAnalysis(
        symbol="EURUSD", snapshot_time=dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
        e_conditions={"E1": e1, "E2": e2, "E3": e3},
        m_maneuvers={"M1": (m1,), "M2": (), "M3": ()},
        combinations=(combo,),
    )


def test_surveillance_proposal_and_visual_explanation_agree_on_the_ready_combination():
    analysis = _snapshot()

    store = FakeStore()
    surveillance_update = update_surveillance(analysis, store)
    proposals = generate_proposals(analysis)

    assert surveillance_update.record["ready_combinations"] == ["E2M1"]
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.combination == "E2M1"
    assert proposal.direction == "SHORT"

    visual = build_visual_explanation(analysis, proposal.combination)
    assert visual.combination == "E2M1"
    assert visual.direction == "SHORT" == proposal.direction

    entry_annotation = next(a for a in visual.annotations if a.semantic_role == "ENTRY_ARRAY")
    assert entry_annotation.low == proposal.entry_low
    assert entry_annotation.high == proposal.entry_high

    poi_annotation = next(a for a in visual.annotations if a.semantic_role == "POI")
    assert poi_annotation.low == 1.0990 and poi_annotation.high == 1.1010


def test_no_ready_combination_means_no_proposal_and_surveillance_reports_it():
    e2 = EConditionResult(entry_condition="E2", symbol="EURUSD", direction="SHORT",
                           touch_status="WAITING_H1_REACTION", reaction_status="WAITING_H1_REACTION",
                           eligible_for_confirmation=False)
    analysis = SMCConditionalEntryAnalysis(
        symbol="EURUSD", snapshot_time=dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
        e_conditions={"E1": EConditionResult(entry_condition="E1", symbol="EURUSD"), "E2": e2,
                      "E3": EConditionResult(entry_condition="E3", symbol="EURUSD")},
        m_maneuvers={"M1": (), "M2": (), "M3": ()}, combinations=(),
    )

    store = FakeStore()
    surveillance_update = update_surveillance(analysis, store)
    proposals = generate_proposals(analysis)

    assert surveillance_update.record["ready_combinations"] == []
    assert proposals == ()
