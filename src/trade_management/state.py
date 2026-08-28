"""Persisted per-ticket management state + restart-safe reconciliation (spec sections
21-23). Broker state is authoritative: reconcile() never trusts the journal blindly --
it compares the persisted record against a freshly-read NormalizedPosition (or its
absence) before letting the manager proceed.

Reconciliation is a pure function (no MT5 IO) so it's fully unit-testable; the caller
(scripts/manage_positions.py) is responsible for actually reading MT5 and passing in the
current position (or None if it no longer exists).
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

from .models import (
    STATE_BREAKEVEN_DONE,
    STATE_CLOSED,
    STATE_MANAGED_OPEN,
    STATE_MANAGEMENT_BLOCKED,
    STATE_RUNNER_ACTIVE,
    STATE_STATE_RECONCILIATION_REQUIRED,
    STATE_TP1_PARTIAL_DONE,
    STATE_TP1_PENDING,
    STATE_UNCLAIMED,
    Claim,
    NormalizedPosition,
)

_FLOAT_TOL = 1e-6

REASON_POSITION_CLOSED_EXTERNALLY = "POSITION_CLOSED_EXTERNALLY"
REASON_UNEXPECTED_VOLUME_REDUCTION = "UNEXPECTED_VOLUME_REDUCTION"
REASON_UNEXPECTED_SL_CHANGE = "UNEXPECTED_SL_CHANGE"
REASON_OK = "OK"


def _state_path(ticket: int, base_dir: str = "journal") -> str:
    return os.path.join(base_dir, f"state_{ticket}.json")


@dataclass(frozen=True)
class StateRecord:
    ticket: int
    state: str
    confirmed_partial_volume: Optional[float] = None  # volume closed at TP1, once confirmed
    breakeven_confirmed: bool = False
    last_completed_intent_id: Optional[str] = None
    updated_at: Optional[datetime] = None

    def with_update(self, **changes) -> "StateRecord":
        data = asdict(self)
        data.pop("updated_at", None)
        data.update(changes)
        return StateRecord(updated_at=datetime.now(timezone.utc), **data)


def load_state(ticket: int, base_dir: str = "journal") -> StateRecord:
    path = _state_path(ticket, base_dir)
    if not os.path.exists(path):
        return StateRecord(ticket=ticket, state=STATE_MANAGED_OPEN)
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if raw.get("updated_at"):
        raw["updated_at"] = datetime.fromisoformat(raw["updated_at"])
    return StateRecord(**raw)


def save_state(record: StateRecord, base_dir: str = "journal") -> None:
    path = _state_path(record.ticket, base_dir)
    os.makedirs(base_dir, exist_ok=True)
    payload = asdict(record)
    if payload.get("updated_at") is not None:
        payload["updated_at"] = record.updated_at.isoformat()
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    os.replace(tmp_path, path)


def reconcile(
    claim: Claim,
    record: StateRecord,
    position: Optional[NormalizedPosition],
) -> "tuple[StateRecord, str]":
    """Returns (possibly-updated StateRecord, reason_code). reason_code is REASON_OK
    when the record is consistent with live broker state and the manager may proceed;
    any other reason_code means the caller should treat this cycle as
    MANAGEMENT_BLOCKED / STATE_RECONCILIATION_REQUIRED and take no action."""

    if position is None:
        if record.state == STATE_CLOSED:
            return record, REASON_OK
        return (
            record.with_update(state=STATE_CLOSED),
            REASON_POSITION_CLOSED_EXTERNALLY,
        )

    if record.state == STATE_UNCLAIMED:
        # Claiming always writes MANAGED_OPEN; a state file existing here would be a
        # caller bug, not a broker-state question -- fail closed rather than guess.
        return record, REASON_UNEXPECTED_VOLUME_REDUCTION

    if record.state in (STATE_MANAGED_OPEN, STATE_TP1_PENDING):
        if position.volume_current < claim.initial_volume - _FLOAT_TOL:
            # Volume dropped but we never journaled/confirmed our own partial --
            # a manual partial close happened (spec section 23). Do not proceed.
            return record, REASON_UNEXPECTED_VOLUME_REDUCTION
        return record, REASON_OK

    if record.state == STATE_TP1_PARTIAL_DONE:
        expected_volume = record.confirmed_partial_volume
        if expected_volume is not None and abs(position.volume_current - expected_volume) > _FLOAT_TOL:
            return record, REASON_UNEXPECTED_VOLUME_REDUCTION
        return record, REASON_OK

    if record.state in (STATE_BREAKEVEN_DONE, STATE_RUNNER_ACTIVE):
        if record.breakeven_confirmed and position.sl is not None:
            if not math.isfinite(position.sl) or abs(position.sl - claim.entry_price) > _FLOAT_TOL:
                # SL no longer at breakeven and we didn't request that change --
                # manual modification (spec section 23).
                return record, REASON_UNEXPECTED_SL_CHANGE
        return record, REASON_OK

    if record.state in (STATE_MANAGEMENT_BLOCKED, STATE_STATE_RECONCILIATION_REQUIRED):
        return record, REASON_OK

    return record, REASON_OK
