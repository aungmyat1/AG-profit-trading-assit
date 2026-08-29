"""Compact vs detailed surveillance output (spec section 50). COMPACT is one line per
symbol for polling loops / multi-symbol dashboards; DETAILED is the full per-E/M state
breakdown, generated only on request or on a meaningful transition -- never dumped on
every poll. Both are pure string formatting over an already-persisted record (see
engine.py's `_snapshot_state`); neither re-derives anything.
"""
from __future__ import annotations

from typing import Dict


def compact_line(record: Dict[str, object]) -> str:
    symbol = record.get("symbol", "?")
    ready = record.get("ready_combinations") or []
    if ready:
        combo = ready[0]
        e_name, m_name = combo[:2], combo[2:]
        direction = (record.get("e_states", {}).get(e_name, {}) or {}).get("direction") or "?"
        extra = f" (+{len(ready) - 1} more)" if len(ready) > 1 else ""
        return f"{symbol} | {combo} {direction} READY{extra}"

    active_e = None
    for name in ("E1", "E2", "E3"):
        e = record.get("e_states", {}).get(name)
        if e and e.get("eligible_for_confirmation"):
            active_e = (name, e)
            break
    if active_e is None:
        return f"{symbol} | NO ACTIVE E CONDITION"

    name, e = active_e
    direction = e.get("direction") or "?"
    developing = _most_developed_waiting_maneuver(record.get("m_states", {}))
    if developing is None:
        return f"{symbol} | {name} {direction}"
    maneuver, state = developing
    return f"{symbol} | {name} {direction} | {maneuver.split(':')[0]} {state}"


_WAITING_ORDER = ("WAITING_M5_ENTRY", "WAITING_M5_CONFIRMATION", "SCANNING_CONTEXT")


def _most_developed_waiting_maneuver(m_states: Dict[str, str]):
    for wanted in _WAITING_ORDER:
        for key, state in m_states.items():
            if state == wanted:
                return key, state
    return None


def detailed_report(record: Dict[str, object]) -> str:
    lines = [f"{record.get('symbol', '?')}", "SMC SURVEILLANCE"]
    if record.get("snapshot_time"):
        lines[0] = f"{record.get('symbol', '?')}  {record['snapshot_time']}"

    for name in ("E1", "E2", "E3"):
        e = record.get("e_states", {}).get(name)
        lines.append("")
        lines.append(name)
        if not e or not e.get("direction"):
            lines.append("NOT_APPLICABLE")
            continue
        lines.append(f"{'QUALIFIED' if e.get('eligible_for_confirmation') else 'DEVELOPING'} {e.get('direction')}")
        lines.append(f"touch = {e.get('touch_status')}")
        lines.append(f"reaction = {e.get('reaction_status')}")

    for maneuver in ("M1", "M2", "M3"):
        lines.append("")
        lines.append(maneuver)
        states = {k.split(":", 1)[1]: v for k, v in record.get("m_states", {}).items() if k.startswith(f"{maneuver}:")}
        if not states or set(states.values()) == {"NOT_APPLICABLE"}:
            lines.append("NOT_APPLICABLE")
        else:
            for direction, state in states.items():
                if state != "NOT_APPLICABLE":
                    lines.append(f"{direction}: {state}")

    lines.append("")
    ready = record.get("ready_combinations") or []
    lines.append("READY COMBINATIONS")
    lines.append(", ".join(ready) if ready else "NONE")

    return "\n".join(lines)
