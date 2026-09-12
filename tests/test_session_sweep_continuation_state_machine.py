import pytest

from session_sweep_continuation.state_machine import (
    Event,
    IllegalTransition,
    State,
    entries_permitted,
    is_terminal,
    transition,
)


def test_happy_path_sequence_deterministic():
    s = State.REFERENCE_BUILDING
    s = transition(s, Event.REFERENCE_SESSION_CLOSED)
    assert s == State.REFERENCE_FROZEN
    s = transition(s, Event.REGIME_CLASSIFIED_KNOWN)
    assert s == State.REGIME_CLASSIFIED
    s = transition(s, Event.SETUP_QUALIFIED)
    assert s == State.AWAITING_SETUP
    s = transition(s, Event.ENTRY_ACCEPTED)
    assert s == State.SETUP_TRIGGERED
    s = transition(s, Event.ENTRY_ACCEPTED)
    assert s == State.CAMPAIGN_ACTIVE
    s = transition(s, Event.CAMPAIGN_CLOSED)
    assert s == State.COMPLETE
    assert is_terminal(s)


def test_unknown_regime_routes_to_no_trade_terminal():
    s = transition(State.REFERENCE_FROZEN, Event.REGIME_CLASSIFIED_UNKNOWN)
    assert s == State.NO_TRADE
    assert is_terminal(s)


def test_terminal_state_rejects_further_events_no_new_entries():
    s = transition(State.CAMPAIGN_ACTIVE, Event.STRUCTURE_INVALIDATED)
    assert s == State.CAMPAIGN_INVALIDATED
    with pytest.raises(IllegalTransition):
        transition(s, Event.ADDITIONAL_ENTRY_ACCEPTED)
    assert entries_permitted(s) is False


def test_session_expiry_blocks_entries_state_level():
    s = transition(State.CAMPAIGN_ACTIVE, Event.SESSION_WINDOW_EXPIRED)
    assert s == State.SESSION_EXPIRED
    assert entries_permitted(s) is False


def test_undefined_transition_raises():
    with pytest.raises(IllegalTransition):
        transition(State.REFERENCE_BUILDING, Event.ENTRY_ACCEPTED)
