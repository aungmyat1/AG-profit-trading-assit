"""3x3 composer tests (spec section 34). Integration-level only -- primitive coverage
for each E/M model lives in its own test file
(test_e1_daily_gap_reaction.py/test_m1_character_change_inducement.py/etc.). Exercises
at least one positive composition for all 9 combinations (E1M1..E3M3) plus the composer
gating rules (direction mismatch, E not qualified, M not engaged, multiple E's/M's).
"""
from __future__ import annotations

from entry_confirmation.composer import evaluate_entry_combinations
from entry_confirmation.entry_models_v1 import COMBINATIONS, EConditionResult
from entry_confirmation.m1_character_change_inducement import M1Result
from entry_confirmation.m2_supply_demand_shift import M2Result
from entry_confirmation.m3_sweep_drop_pump import M3Result


def _e(entry_condition, direction="SHORT", eligible=True):
    return EConditionResult(entry_condition=entry_condition, symbol="EURUSD", direction=direction,
                             eligible_for_confirmation=eligible)


def _m1(direction="SHORT", state="READY", entry_condition=None):
    return M1Result(symbol="EURUSD", entry_condition=entry_condition, direction=direction, state=state)


def _m2(direction="SHORT", state="READY", entry_condition=None):
    return M2Result(symbol="EURUSD", entry_condition=entry_condition, direction=direction, state=state)


def _m3(direction="SHORT", state="READY", entry_condition=None):
    return M3Result(symbol="EURUSD", entry_condition=entry_condition, direction=direction, state=state)


# --------------------------------------------------------------------------- all 9 combinations


def test_all_nine_combinations_are_supported():
    e_conditions = [_e("E1"), _e("E2"), _e("E3")]
    m_results = [_m1(), _m2(), _m3()]
    combos = evaluate_entry_combinations(e_conditions, m_results)
    produced = {c.combination for c in combos}
    assert produced == set(COMBINATIONS)
    assert len(combos) == 9


def test_e2_m1_is_a_valid_combination_not_hard_wired_to_e2_m2():
    # The old architecture would never have let E2 feed M1. The new one must.
    combos = evaluate_entry_combinations([_e("E2")], [_m1()])
    assert len(combos) == 1
    assert combos[0].combination == "E2M1"
    assert combos[0].entry_condition == "E2"
    assert combos[0].maneuver == "M1"


def test_e1_m3_is_a_valid_combination_not_hard_wired_to_e1_m1():
    combos = evaluate_entry_combinations([_e("E1")], [_m3()])
    assert len(combos) == 1
    assert combos[0].combination == "E1M3"


# --------------------------------------------------------------------------- gating


def test_direction_mismatch_produces_no_combination():
    combos = evaluate_entry_combinations([_e("E2", direction="SHORT")], [_m2(direction="LONG")])
    assert combos == ()


def test_e_not_eligible_produces_no_combination():
    combos = evaluate_entry_combinations([_e("E2", eligible=False)], [_m2(state="READY")])
    assert combos == ()


def test_m_not_applicable_produces_no_combination():
    combos = evaluate_entry_combinations([_e("E2")], [_m2(state="NOT_APPLICABLE")])
    assert combos == ()


def test_m_no_valid_combination_state_never_composed():
    combos = evaluate_entry_combinations([_e("E2")], [_m2(state="NO_VALID_COMBINATION")])
    assert combos == ()


def test_e_qualified_m_waiting_still_produces_a_waiting_combination():
    combos = evaluate_entry_combinations([_e("E2")], [_m2(state="WAITING_M5_ENTRY")])
    assert len(combos) == 1
    assert combos[0].state == "WAITING_M5_ENTRY"
    assert combos[0].m_confirmation_state == "WAITING_M5_ENTRY"


# --------------------------------------------------------------------------- multiple E's / M's


def test_multiple_e_conditions_and_m_confirmations_produce_multiple_combinations():
    # E1=QUALIFIED, E2=QUALIFIED, E3=NOT_APPLICABLE (only 2 E's supplied);
    # M1=CONFIRMED, M2=CONFIRMED, M3=NOT_CONFIRMED (only 2 M's supplied) ->
    # E1M1, E1M2, E2M1, E2M2 (spec section 21 example).
    e_conditions = [_e("E1"), _e("E2")]
    m_results = [_m1(), _m2()]
    combos = evaluate_entry_combinations(e_conditions, m_results)
    produced = {c.combination for c in combos}
    assert produced == {"E1M1", "E1M2", "E2M1", "E2M2"}


def test_no_priority_is_invented_all_valid_combinations_returned():
    e_conditions = [_e("E1"), _e("E2"), _e("E3")]
    m_results = [_m1(), _m2(), _m3()]
    combos = evaluate_entry_combinations(e_conditions, m_results)
    # Every combination is present at the same "rank" -- no combination is dropped in
    # favor of another, no field marks one as preferred.
    assert len(combos) == 9
    assert len({c.combination for c in combos}) == 9


# --------------------------------------------------------------------------- determinism


def test_deterministic_repeated_evaluation():
    e_conditions = [_e("E1"), _e("E2"), _e("E3")]
    m_results = [_m1(), _m2(), _m3()]
    first = evaluate_entry_combinations(e_conditions, m_results)
    second = evaluate_entry_combinations(e_conditions, m_results)
    assert first == second
