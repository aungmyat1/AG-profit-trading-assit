"""Deterministic engineering-only VirtualPosition and VirtualAccount.

No broker volume, money, margin, conversion, or friction semantics are inferred.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional, Tuple

from .virtual_exchange import ExchangeRecord, ObservationKind


class AccountError(ValueError):
    pass


class PositionState(str, Enum):
    OPEN = "OPEN"
    PARTIAL = "PARTIAL"
    CLOSED = "CLOSED"
    UNRESOLVED = "UNRESOLVED"


def _utc(v):
    if v.tzinfo is None or v.utcoffset() is None:
        raise AccountError("timestamp must be timezone-aware")
    return v.astimezone(timezone.utc)


def _id(v):
    return "sha256:" + hashlib.sha256(json.dumps(v, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@dataclass(frozen=True)
class PositionTransition:
    event_id: str
    at: datetime
    from_state: Optional[PositionState]
    to_state: PositionState
    reason: str
    evidence_event_id: str
    price: Optional[float]
    normalized_delta: Optional[float]


@dataclass
class VirtualPosition:
    position_id: str
    strategy_id: str
    strategy_version: str
    symbol: str
    side: str
    dataset_id: str
    decision_id: str
    proposal_id: str
    order_id: str
    fill_record: ExchangeRecord
    reference_price: float
    executable_entry_price: float
    stop_price: Optional[float]
    target_price: Optional[float]
    quantity_basis: str = "ENGINEERING_NORMALIZED_1"
    normalized_quantity: float = 1.0
    broker_volume_authority: bool = False
    state: PositionState = PositionState.OPEN
    transitions: list[PositionTransition] = field(default_factory=list)
    normalized_pnl: float = 0.0


@dataclass(frozen=True)
class AccountSnapshot:
    snapshot_id: str
    at: datetime
    open_position_ids: Tuple[str, ...]
    closed_position_ids: Tuple[str, ...]
    balance_engineering: float
    realized_price_pnl: float
    economic_pnl_status: str
    previous_snapshot_id: Optional[str]


class VirtualAccount:
    """Idempotent reducer for Cycle 3B exchange records."""

    def __init__(self, *, starting_engineering_balance: float = 0.0,
                 max_open_positions: int = 1):
        if max_open_positions < 1 or starting_engineering_balance < 0:
            raise AccountError("invalid engineering account profile")
        self.starting_engineering_balance = float(starting_engineering_balance)
        self.max_open_positions = max_open_positions
        self.open_positions: Dict[str, VirtualPosition] = {}
        self.closed_positions: Dict[str, VirtualPosition] = {}
        self._processed: Dict[str, str] = {}
        self.snapshots: list[AccountSnapshot] = []

    def apply_fill(self, fill: ExchangeRecord, *, strategy_id: str, strategy_version: str,
                   symbol: str, side: str, stop_price=None, target_price=None) -> VirtualPosition:
        if fill.record_type != "FILL" or fill.executable_price is None:
            raise AccountError("UNKNOWN_OR_NON_EXECUTABLE_FILL")
        self._check_lineage(fill, symbol)
        payload_hash = _id(fill)
        prior = self._processed.get(fill.record_id)
        if prior is not None:
            if prior != payload_hash:
                raise AccountError("DUPLICATE_CONFLICTING_FILL")
            return next(p for p in self.open_positions.values() if p.fill_record.record_id == fill.record_id)
        if len(self.open_positions) >= self.max_open_positions:
            raise AccountError("MAX_OPEN_POSITIONS")
        pid = _id({"fill": fill.record_id, "proposal": fill.proposal_id})
        position = VirtualPosition(pid, strategy_id, strategy_version, symbol, side,
                                   fill.dataset_id, fill.decision_id, fill.proposal_id,
                                   fill.order_id, fill, fill.reference_price,
                                   fill.executable_price, stop_price, target_price)
        position.transitions.append(PositionTransition(_id([pid, "OPEN", fill.event_id]), fill.at, None,
                                                        PositionState.OPEN, "VALID_FILL", fill.event_id,
                                                        fill.executable_price, 0.0))
        self.open_positions[pid] = position
        self._processed[fill.record_id] = payload_hash
        self._snapshot(fill.at)
        return position

    def apply_exit(self, exit_record: ExchangeRecord) -> Optional[VirtualPosition]:
        self._check_lineage(exit_record, None)
        prior = self._processed.get(exit_record.record_id)
        if prior is not None:
            if prior != _id(exit_record):
                raise AccountError("DUPLICATE_CONFLICTING_EXIT")
            return next((p for p in self.closed_positions.values()
                         if p.order_id == exit_record.order_id), None)
        if exit_record.observation_kind == ObservationKind.AMBIGUOUS_SEQUENCE.value:
            self._processed.setdefault(exit_record.record_id, _id(exit_record))
            self._snapshot(exit_record.at)
            return None
        candidates = [p for p in self.open_positions.values() if p.order_id == exit_record.order_id]
        if not candidates:
            if exit_record.record_id in self._processed:
                return None
            raise AccountError("EXIT_WITHOUT_OPEN_POSITION")
        position = candidates[0]
        if _utc(exit_record.at) < _utc(position.fill_record.at):
            raise AccountError("EXIT_PRECEDES_FILL")
        price = exit_record.executable_price
        if price is None:
            raise AccountError("EXIT_PRICE_UNAVAILABLE")
        sign = 1.0 if position.side == "LONG" else -1.0
        delta = (price - position.executable_entry_price) * sign * position.normalized_quantity
        position.normalized_pnl += delta
        old = position.state
        position.state = PositionState.CLOSED
        position.transitions.append(PositionTransition(_id([position.position_id, "CLOSED", exit_record.event_id]),
                                                       exit_record.at, old, PositionState.CLOSED,
                                                       exit_record.reason, exit_record.event_id, price, delta))
        self.open_positions.pop(position.position_id)
        self.closed_positions[position.position_id] = position
        self._processed[exit_record.record_id] = _id(exit_record)
        self._snapshot(exit_record.at)
        return position

    def mark_unresolved(self, *, order_id: str, at: datetime, reason: str,
                        evidence_event_id: str) -> VirtualPosition:
        position = next((p for p in self.open_positions.values() if p.order_id == order_id), None)
        if position is None:
            raise AccountError("UNRESOLVED_WITHOUT_OPEN_POSITION")
        if position.state is PositionState.UNRESOLVED:
            return position
        position.transitions.append(PositionTransition(
            _id([position.position_id, "UNRESOLVED", evidence_event_id]), _utc(at),
            position.state, PositionState.UNRESOLVED, reason, evidence_event_id,
            None, None))
        position.state = PositionState.UNRESOLVED
        self._snapshot(at)
        return position

    def _check_lineage(self, record, symbol):
        if not record.dataset_id or not record.event_id or not record.decision_id or not record.proposal_id:
            raise AccountError("MISSING_LINEAGE")
        if symbol is not None and getattr(record, "_symbol", symbol) != symbol:
            raise AccountError("SYMBOL_MISMATCH")

    def _snapshot(self, at):
        previous = self.snapshots[-1].snapshot_id if self.snapshots else None
        realized = sum(p.normalized_pnl for p in self.closed_positions.values())
        payload = [str(_utc(at)), sorted(self.open_positions), sorted(self.closed_positions), realized, previous]
        self.snapshots.append(AccountSnapshot(_id(payload), _utc(at), tuple(sorted(self.open_positions)),
                                              tuple(sorted(self.closed_positions)),
                                              self.starting_engineering_balance + realized,
                                              realized, "NOT_MODELED", previous))

    @property
    def latest_snapshot(self):
        return self.snapshots[-1] if self.snapshots else None
