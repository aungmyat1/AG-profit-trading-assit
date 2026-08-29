"""update_surveillance() -- the single entry point. Diffs the current
SMCConditionalEntryAnalysis snapshot against the last-persisted state for that symbol
(runtime_state.store.JsonKeyValueStore, the repo's existing persistence primitive --
see daytrading_runtime/smc_runtime.py for the precedent this generalizes) and emits
transition events only for what actually changed (spec section 28: never emit on an
identical repeated poll).
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

from entry_confirmation.entry_models_v1 import EntryModelState, SMCConditionalEntryAnalysis

from .models import (
    EVENT_CONTEXT_QUALIFIED,
    EVENT_ENTRY_READY,
    EVENT_H1_REACTION_CONFIRMED,
    EVENT_M_CONFIRMATION_DEVELOPING,
    EVENT_REFERENCE_TOUCHED,
    EVENT_SETUP_EXPIRED,
    EVENT_SETUP_INVALIDATED,
    MAX_HISTORY_ENTRIES,
    SurveillanceEvent,
    SurveillanceUpdate,
)

_TOUCHED_TOUCH_STATUSES = {
    EntryModelState.WAITING_H1_REACTION.value, EntryModelState.HTF_QUALIFIED.value,
}


def _iso(t: Optional[datetime]) -> Optional[str]:
    return t.isoformat() if t is not None else None


def _snapshot_state(analysis: SMCConditionalEntryAnalysis) -> Dict[str, object]:
    """Plain-JSON-serializable summary of the pieces this module tracks. Every value
    copied here already exists on the frozen SMC_CONDITIONAL_ENTRY_V2 contracts -- this
    is a projection, not a new computation."""
    e_states = {}
    for name, e in analysis.e_conditions.items():
        e_states[name] = {
            "direction": e.direction,
            "touch_status": e.touch_status,
            "reaction_status": e.reaction_status,
            "eligible_for_confirmation": e.eligible_for_confirmation,
        }

    m_states: Dict[str, str] = {}
    for maneuver, results in analysis.m_maneuvers.items():
        for r in results:
            key = f"{maneuver}:{r.direction or 'NONE'}"
            m_states[key] = r.state

    combination_states: Dict[str, str] = {c.combination: c.state for c in analysis.combinations}
    ready_combinations = tuple(sorted(c.combination for c in analysis.combinations if c.state == EntryModelState.READY.value))

    return {
        "symbol": analysis.symbol,
        "snapshot_time": _iso(analysis.snapshot_time),
        "e_states": e_states,
        "m_states": m_states,
        "combination_states": combination_states,
        "ready_combinations": list(ready_combinations),
        "data_quality": analysis.data_quality,
    }


def _diff_e_states(symbol: str, snapshot_time: Optional[str], prev: dict, current: dict) -> Iterable[SurveillanceEvent]:
    for name, cur in current.items():
        old = prev.get(name, {})
        if old.get("touch_status") == EntryModelState.WAITING_HTF_TOUCH.value and \
                cur.get("touch_status") in _TOUCHED_TOUCH_STATUSES:
            yield SurveillanceEvent(EVENT_REFERENCE_TOUCHED, symbol, snapshot_time,
                                     {"entry_condition": name, "direction": cur.get("direction")})
        if old.get("reaction_status") != EntryModelState.HTF_QUALIFIED.value and \
                cur.get("reaction_status") == EntryModelState.HTF_QUALIFIED.value:
            yield SurveillanceEvent(EVENT_H1_REACTION_CONFIRMED, symbol, snapshot_time,
                                     {"entry_condition": name, "direction": cur.get("direction")})
        if not old.get("eligible_for_confirmation") and cur.get("eligible_for_confirmation"):
            yield SurveillanceEvent(EVENT_CONTEXT_QUALIFIED, symbol, snapshot_time,
                                     {"entry_condition": name, "direction": cur.get("direction")})


def _diff_state_map(symbol: str, snapshot_time: Optional[str], prev: dict, current: dict,
                     key_field: str) -> Iterable[SurveillanceEvent]:
    for key, cur_state in current.items():
        old_state = prev.get(key)
        if old_state == cur_state:
            continue
        if cur_state == EntryModelState.WAITING_M5_ENTRY.value:
            yield SurveillanceEvent(EVENT_M_CONFIRMATION_DEVELOPING, symbol, snapshot_time, {key_field: key})
        elif cur_state == EntryModelState.READY.value:
            yield SurveillanceEvent(EVENT_ENTRY_READY, symbol, snapshot_time, {key_field: key})
        elif cur_state == EntryModelState.INVALIDATED.value:
            yield SurveillanceEvent(EVENT_SETUP_INVALIDATED, symbol, snapshot_time, {key_field: key})
        elif cur_state == EntryModelState.EXPIRED.value:
            yield SurveillanceEvent(EVENT_SETUP_EXPIRED, symbol, snapshot_time, {key_field: key})


def _diff(symbol: str, snapshot_time: Optional[str], prev: dict, current: dict) -> Tuple[SurveillanceEvent, ...]:
    events: List[SurveillanceEvent] = []
    events += list(_diff_e_states(symbol, snapshot_time, prev.get("e_states", {}), current["e_states"]))
    events += list(_diff_state_map(symbol, snapshot_time, prev.get("m_states", {}), current["m_states"], "maneuver"))
    events += list(_diff_state_map(symbol, snapshot_time, prev.get("combination_states", {}),
                                    current["combination_states"], "combination"))
    return tuple(events)


def update_surveillance(analysis: SMCConditionalEntryAnalysis, store) -> SurveillanceUpdate:
    """`store` is a runtime_state.store.JsonKeyValueStore (or any object with the same
    get/put interface) -- injected, not constructed here, so callers control where
    surveillance state lives and tests never touch the filesystem."""
    symbol = analysis.symbol
    prev_record = store.get(symbol) or {}
    current_state = _snapshot_state(analysis)

    events = _diff(symbol, current_state["snapshot_time"], prev_record, current_state)

    history = list(prev_record.get("history", []))
    for ev in events:
        history.append({"time": ev.snapshot_time, "event_type": ev.event_type, "detail": ev.detail})
    history = history[-MAX_HISTORY_ENTRIES:]

    record = dict(current_state)
    record["history"] = history
    store.put(symbol, record)

    return SurveillanceUpdate(symbol=symbol, record=record, events=events)
