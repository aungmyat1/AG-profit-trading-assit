"""setup_id collision repair (historical-validation spec sections 17-19, 59).

Before this fix, `setup_id` was a pure function of (symbol, combination, direction)
only -- two independent setups sharing those three fields (e.g. Monday's EURUSD E2M1
SHORT from H1 POI A vs Wednesday's from H1 POI B) collided into the same identity,
which would corrupt historical setup-lifecycle statistics. `reference_key_for` derives
a stable structural identity from the qualifying E-condition's reference (type +
low/high/level), and gate.py/lifecycle.py now feed it into every real setup_id call.
"""
from __future__ import annotations

import datetime as dt

from entry_confirmation.entry_models_v1 import EConditionResult, SMCConditionalEntryAnalysis, SMCEntryCombinationResult
from proposals import generate_proposals, reference_key_for, setup_id, update_proposal_lifecycle

UTC = dt.timezone.utc


class FakeStore:
    def __init__(self):
        self._data = {}

    def get(self, key):
        return self._data.get(key)

    def put(self, key, value):
        self._data[key] = value


def _analysis(reference_level, entry_price, snapshot_time, direction="SHORT"):
    e2 = EConditionResult(entry_condition="E2", symbol="EURUSD", direction=direction,
                           eligible_for_confirmation=True, reference_type="H1_POI", reference_level=reference_level)
    combo = SMCEntryCombinationResult(combination="E2M1", entry_condition="E2", maneuver="M1", symbol="EURUSD",
                                       direction=direction, confirmation_timeframe="M5",
                                       entry_array="FVG", entry_price=entry_price, state="READY")
    return SMCConditionalEntryAnalysis(
        symbol="EURUSD", snapshot_time=snapshot_time,
        e_conditions={"E1": EConditionResult(entry_condition="E1", symbol="EURUSD"), "E2": e2,
                      "E3": EConditionResult(entry_condition="E3", symbol="EURUSD")},
        m_maneuvers={"M1": (), "M2": (), "M3": ()}, combinations=(combo,),
    )


def test_reference_key_for_none_when_no_reference_fields():
    assert reference_key_for(None, None, None, None) is None


def test_reference_key_for_differs_by_reference_level():
    a = reference_key_for("H1_POI", None, None, 1.1050)
    b = reference_key_for("H1_POI", None, None, 1.2000)
    assert a != b


def test_setup_id_same_reference_key_is_stable():
    a = setup_id("EURUSD", "E2M1", "SHORT", "H1_POI|None|None|1.105")
    b = setup_id("EURUSD", "E2M1", "SHORT", "H1_POI|None|None|1.105")
    assert a == b


def test_setup_id_different_reference_key_produces_different_identity():
    base = setup_id("EURUSD", "E2M1", "SHORT", "H1_POI|None|None|1.105")
    other_poi = setup_id("EURUSD", "E2M1", "SHORT", "H1_POI|None|None|1.205")
    assert base != other_poi


def test_generate_proposals_different_poi_gets_different_setup_id():
    """The exact scenario from spec section 17: same symbol/combination/direction,
    different underlying HTF POI, on different days -- must NOT collide."""
    monday = _analysis(reference_level=1.1050, entry_price=1.1040,
                        snapshot_time=dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC))
    wednesday = _analysis(reference_level=1.2000, entry_price=1.1990,
                           snapshot_time=dt.datetime(2026, 1, 7, 10, 0, tzinfo=UTC))

    p_monday = generate_proposals(monday)[0]
    p_wednesday = generate_proposals(wednesday)[0]

    assert p_monday.setup_id != p_wednesday.setup_id
    assert p_monday.proposal_id != p_wednesday.proposal_id


def test_generate_proposals_same_poi_same_setup_id_across_polls():
    poll1 = _analysis(reference_level=1.1050, entry_price=1.1040,
                       snapshot_time=dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC))
    poll2 = _analysis(reference_level=1.1050, entry_price=1.1040,
                       snapshot_time=dt.datetime(2026, 1, 5, 10, 15, tzinfo=UTC))

    p1 = generate_proposals(poll1)[0]
    p2 = generate_proposals(poll2)[0]

    assert p1.setup_id == p2.setup_id


def test_lifecycle_two_concurrent_pois_tracked_as_independent_setups():
    """A second, independent POI appearing on the same symbol/combination/direction
    while the first setup is still active must be reported CREATED (a new setup), not
    UPDATED (which would silently overwrite the first setup's identity/history)."""
    store = FakeStore()
    t0 = dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
    first = update_proposal_lifecycle(
        _analysis(reference_level=1.1050, entry_price=1.1040, snapshot_time=t0), store)
    assert first[0].lifecycle == "CREATED"

    t1 = t0 + dt.timedelta(minutes=15)
    second_poi = update_proposal_lifecycle(
        _analysis(reference_level=1.2000, entry_price=1.1990, snapshot_time=t1), store)
    assert second_poi[0].lifecycle == "CREATED"
    assert second_poi[0].setup_id != first[0].setup_id
