"""Explicit, replay-safe strategy state machine for one campaign candidate
(symbol x session_pair x trading_date x direction). Pure function transitions --
`transition()` takes only the current state and an event and returns the next state;
no hidden globals, no wall-clock reads, so replaying the same event sequence twice
always produces the same state sequence (replay determinism requirement).
"""
from __future__ import annotations

from enum import Enum
from typing import Optional


class State(str, Enum):
    REFERENCE_BUILDING = "REFERENCE_BUILDING"
    REFERENCE_FROZEN = "REFERENCE_FROZEN"
    REGIME_CLASSIFIED = "REGIME_CLASSIFIED"
    NO_TRADE = "NO_TRADE"                    # terminal -- regime UNKNOWN
    AWAITING_SETUP = "AWAITING_SETUP"
    SETUP_TRIGGERED = "SETUP_TRIGGERED"
    CAMPAIGN_ACTIVE = "CAMPAIGN_ACTIVE"
    CAMPAIGN_INVALIDATED = "CAMPAIGN_INVALIDATED"   # terminal
    SESSION_EXPIRED = "SESSION_EXPIRED"             # terminal
    RISK_EXHAUSTED = "RISK_EXHAUSTED"               # terminal
    COMPLETE = "COMPLETE"                           # terminal


TERMINAL_STATES = frozenset({
    State.NO_TRADE, State.CAMPAIGN_INVALIDATED, State.SESSION_EXPIRED,
    State.RISK_EXHAUSTED, State.COMPLETE,
})


class Event(str, Enum):
    REFERENCE_SESSION_CLOSED = "REFERENCE_SESSION_CLOSED"
    REGIME_CLASSIFIED_KNOWN = "REGIME_CLASSIFIED_KNOWN"
    REGIME_CLASSIFIED_UNKNOWN = "REGIME_CLASSIFIED_UNKNOWN"
    SETUP_QUALIFIED = "SETUP_QUALIFIED"
    ENTRY_ACCEPTED = "ENTRY_ACCEPTED"
    ENTRY_REJECTED = "ENTRY_REJECTED"
    ADDITIONAL_ENTRY_ACCEPTED = "ADDITIONAL_ENTRY_ACCEPTED"
    STRUCTURE_INVALIDATED = "STRUCTURE_INVALIDATED"
    SESSION_WINDOW_EXPIRED = "SESSION_WINDOW_EXPIRED"
    RISK_BUDGET_EXHAUSTED = "RISK_BUDGET_EXHAUSTED"
    HARD_LOSS_STOP = "HARD_LOSS_STOP"
    BAD_DATA = "BAD_DATA"
    CAMPAIGN_CLOSED = "CAMPAIGN_CLOSED"


class IllegalTransition(Exception):
    pass


# (current_state, event) -> next_state. Deliberately explicit and exhaustive rather
# than a generic "any event moves forward" rule -- an event not listed for the current
# state is a bug to surface (IllegalTransition), never silently ignored or coerced.
_TRANSITIONS = {
    (State.REFERENCE_BUILDING, Event.REFERENCE_SESSION_CLOSED): State.REFERENCE_FROZEN,
    (State.REFERENCE_BUILDING, Event.BAD_DATA): State.CAMPAIGN_INVALIDATED,

    (State.REFERENCE_FROZEN, Event.REGIME_CLASSIFIED_KNOWN): State.REGIME_CLASSIFIED,
    (State.REFERENCE_FROZEN, Event.REGIME_CLASSIFIED_UNKNOWN): State.NO_TRADE,
    (State.REFERENCE_FROZEN, Event.BAD_DATA): State.CAMPAIGN_INVALIDATED,

    (State.REGIME_CLASSIFIED, Event.SETUP_QUALIFIED): State.AWAITING_SETUP,
    (State.REGIME_CLASSIFIED, Event.SESSION_WINDOW_EXPIRED): State.SESSION_EXPIRED,

    (State.AWAITING_SETUP, Event.ENTRY_ACCEPTED): State.SETUP_TRIGGERED,
    (State.AWAITING_SETUP, Event.ENTRY_REJECTED): State.REGIME_CLASSIFIED,
    (State.AWAITING_SETUP, Event.SESSION_WINDOW_EXPIRED): State.SESSION_EXPIRED,
    (State.AWAITING_SETUP, Event.STRUCTURE_INVALIDATED): State.CAMPAIGN_INVALIDATED,

    (State.SETUP_TRIGGERED, Event.ENTRY_ACCEPTED): State.CAMPAIGN_ACTIVE,

    (State.CAMPAIGN_ACTIVE, Event.ADDITIONAL_ENTRY_ACCEPTED): State.CAMPAIGN_ACTIVE,
    (State.CAMPAIGN_ACTIVE, Event.STRUCTURE_INVALIDATED): State.CAMPAIGN_INVALIDATED,
    (State.CAMPAIGN_ACTIVE, Event.SESSION_WINDOW_EXPIRED): State.SESSION_EXPIRED,
    (State.CAMPAIGN_ACTIVE, Event.RISK_BUDGET_EXHAUSTED): State.RISK_EXHAUSTED,
    (State.CAMPAIGN_ACTIVE, Event.HARD_LOSS_STOP): State.CAMPAIGN_INVALIDATED,
    (State.CAMPAIGN_ACTIVE, Event.BAD_DATA): State.CAMPAIGN_INVALIDATED,
    (State.CAMPAIGN_ACTIVE, Event.CAMPAIGN_CLOSED): State.COMPLETE,

    # Terminal states may only self-loop-free (attempting further events raises) --
    # deliberately no transitions registered out of RISK_EXHAUSTED/SESSION_EXPIRED/
    # CAMPAIGN_INVALIDATED/NO_TRADE/COMPLETE: "no new entries after invalidation or
    # session expiry" is enforced structurally, not by a runtime if-check the caller
    # could forget.
}


def transition(current: State, event: Event) -> State:
    key = (current, event)
    if key in _TRANSITIONS:
        return _TRANSITIONS[key]
    if current in TERMINAL_STATES:
        raise IllegalTransition(
            f"state {current.value} is terminal -- no new entries/events permitted "
            f"(attempted event {event.value})"
        )
    raise IllegalTransition(f"no transition defined for state={current.value} event={event.value}")


def is_terminal(state: State) -> bool:
    return state in TERMINAL_STATES


def entries_permitted(state: State) -> bool:
    """Single authoritative check for 'can a new entry be accepted right now' --
    setups.py / campaign.py must call this rather than re-deriving the rule."""
    return state in (State.AWAITING_SETUP, State.SETUP_TRIGGERED, State.CAMPAIGN_ACTIVE)
