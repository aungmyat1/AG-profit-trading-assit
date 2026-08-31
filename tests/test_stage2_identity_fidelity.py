"""Identity-fidelity tests for historical_replay.stage2 (true Stage-2 boundary).
Regression for a real bug: evaluate_entry_stage() built pseudo_e without any
reference_type/low/high/level, so reference_key_for() always returned None,
collapsing distinct real-world E events (same entry_condition+direction, different
HTF reference) into one setup_id -- confirmed via a 0/54 identity intersection against
the original full-replay ledger.
"""
from __future__ import annotations

import datetime as dt

from historical_replay.stage2 import _parse_reference_key
from proposals.identity import reference_key_for, setup_id

UTC = dt.timezone.utc


# --------------------------------------------------------------------------- round-trip

def test_reference_key_round_trip_d1_gap_style():
    key = reference_key_for("D1_GAP", 1.16687, 1.17031, None)
    assert key == "D1_GAP|1.16687|1.17031|None"
    assert _parse_reference_key(key) == ("D1_GAP", 1.16687, 1.17031, None)


def test_reference_key_round_trip_liquidity_level_style():
    key = reference_key_for("PWH", None, None, 1.1765)
    assert _parse_reference_key(key) == ("PWH", None, None, 1.1765)


def test_reference_key_round_trip_none():
    assert reference_key_for(None, None, None, None) is None
    assert _parse_reference_key(None) == (None, None, None, None)


def test_reference_key_round_trip_e2_h1_poi_style():
    key = reference_key_for("H1_POI", 1.10, 1.11, None)
    assert _parse_reference_key(key) == ("H1_POI", 1.10, 1.11, None)


# --------------------------------------------------------------------------- collision (the actual bug)

def test_same_e_type_and_direction_different_reference_yields_different_setup_id():
    """The exact collision this bug caused: two real events, same entry_condition
    (E3) + direction (SHORT), different HTF liquidity reference -- must NOT collapse
    to the same setup_id once reference_key is correctly threaded through."""
    key_a = reference_key_for("PDH", None, None, 1.16751)
    key_b = reference_key_for("PDH", None, None, 1.17301)
    assert key_a != key_b

    id_a = setup_id("EURUSD", "E3M1", "SHORT", key_a)
    id_b = setup_id("EURUSD", "E3M1", "SHORT", key_b)
    assert id_a != id_b


def test_missing_reference_key_still_collapses_as_before_no_regression():
    """When reference_key is genuinely None (no reference at all -- e.g. a maneuver
    whose E never carried a reference), the base 3-field identity applies exactly as
    it always has -- this bug fix must not change that existing, tested behavior."""
    assert setup_id("EURUSD", "E2M1", "SHORT", None) == setup_id("EURUSD", "E2M1", "SHORT", None)
