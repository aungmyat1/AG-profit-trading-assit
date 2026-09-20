"""Isolated deterministic VirtualExchange core for OHLC_M1 engineering fixtures.

This module deliberately has no account, cost, broker, strategy, or MT5 dependency.
The fixture open price is an explicitly labeled engineering fill observation; it is not
a broker-realistic quote or an SSC research reference price.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Iterable, Optional, Tuple


class ExchangeError(ValueError):
    pass


class OrderState(str, Enum):
    CREATED = "CREATED"
    PENDING = "PENDING"
    ELIGIBLE = "ELIGIBLE"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class ObservationKind(str, Enum):
    ADVERSE = "ADVERSE"
    FAVORABLE = "FAVORABLE"
    AMBIGUOUS_SEQUENCE = "AMBIGUOUS_SEQUENCE"


def _utc(v: datetime) -> datetime:
    if v.tzinfo is None or v.utcoffset() is None:
        raise ExchangeError("timestamps must be timezone-aware")
    return v.astimezone(timezone.utc)


def _id(payload: object) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@dataclass(frozen=True)
class ResearchReferenceEntry:
    decision_id: str
    symbol: str
    decision_cutoff: datetime
    reference_price: float
    source_event_id: str
    semantics: str = "SSC_RESEARCH_REFERENCE"

    def __post_init__(self):
        object.__setattr__(self, "decision_cutoff", _utc(self.decision_cutoff))
        if not self.decision_id or not self.source_event_id or self.reference_price <= 0:
            raise ExchangeError("invalid research reference entry")


@dataclass(frozen=True)
class ProposalFixture:
    proposal_id: str
    symbol: str
    side: str
    decision_cutoff: datetime
    dataset_id: str
    decision_event_id: str
    reference_entry: ResearchReferenceEntry
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    expires_at: Optional[datetime] = None

    def __post_init__(self):
        object.__setattr__(self, "decision_cutoff", _utc(self.decision_cutoff))
        if self.expires_at is not None:
            object.__setattr__(self, "expires_at", _utc(self.expires_at))
        if self.side not in {"LONG", "SHORT"} or self.symbol != self.reference_entry.symbol:
            raise ExchangeError("proposal symbol/side mismatch")
        if self.reference_entry.decision_cutoff != self.decision_cutoff:
            raise ExchangeError("reference and proposal cutoff mismatch")


@dataclass(frozen=True)
class OHLCM1:
    event_id: str
    dataset_id: str
    symbol: str
    time: datetime
    open: float
    high: float
    low: float
    close: float

    def __post_init__(self):
        object.__setattr__(self, "time", _utc(self.time))
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close) or self.low > self.high:
            raise ExchangeError("INVALID_OHLC")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ExchangeError("INVALID_OHLC")

    @property
    def close_time(self) -> datetime:
        return self.time + timedelta(minutes=1)


@dataclass(frozen=True)
class ExchangeRecord:
    record_type: str
    record_id: str
    order_id: str
    at: datetime
    state: OrderState
    reason: str
    dataset_id: str
    event_id: str
    decision_id: str
    proposal_id: str
    reference_price: Optional[float] = None
    executable_price: Optional[float] = None
    observation_kind: Optional[str] = None
    evidence_event_id: Optional[str] = None


@dataclass
class VirtualOrder:
    order_id: str
    proposal: ProposalFixture
    state: OrderState
    records: list[ExchangeRecord] = field(default_factory=list)
    fill: Optional[ExchangeRecord] = None
    exit: Optional[ExchangeRecord] = None


class VirtualExchange:
    """Single-order deterministic exchange fixture runner."""

    QUALITY = "OHLC_M1"

    def __init__(self, *, execution_quality: str = QUALITY):
        if execution_quality != self.QUALITY:
            raise ExchangeError("UNSUPPORTED_EXECUTION_DATA_QUALITY")
        self.execution_quality = execution_quality
        self._order: Optional[VirtualOrder] = None

    @property
    def order(self) -> Optional[VirtualOrder]:
        return self._order

    def submit(self, proposal: ProposalFixture, *, order_id: Optional[str] = None) -> VirtualOrder:
        if self._order is not None:
            raise ExchangeError("MAX_OPEN_ORDERS")
        if proposal.dataset_id != proposal.reference_entry.source_event_id.split("|", 1)[0] and not proposal.dataset_id:
            raise ExchangeError("MISSING_DATASET_ID")
        oid = order_id or _id({"proposal": proposal.proposal_id, "decision": proposal.decision_event_id})
        order = VirtualOrder(oid, proposal, OrderState.CREATED)
        self._transition(order, OrderState.PENDING, proposal.decision_cutoff,
                         "ORDER_ACCEPTED", proposal.dataset_id, proposal.decision_event_id)
        self._order = order
        return order

    def process(self, bars: Iterable[OHLCM1], *, end_time: Optional[datetime] = None,
                mode: str = "maximum") -> VirtualOrder:
        if mode not in {"step", "accelerated", "maximum"}:
            raise ExchangeError("unsupported playback mode")
        if self._order is None:
            raise ExchangeError("NO_ORDER")
        order = self._order
        ordered = tuple(sorted(bars, key=lambda b: (b.time, b.event_id)))
        if not ordered:
            raise ExchangeError("MISSING_EXECUTION_EVIDENCE")
        p = order.proposal
        for bar in ordered:
            if bar.symbol != p.symbol or bar.dataset_id != p.dataset_id:
                raise ExchangeError("MISMATCHED_SYMBOL_OR_DATASET")
            if not bar.event_id:
                raise ExchangeError("MISSING_EVENT_LINEAGE")
            if bar.time <= p.decision_cutoff:
                continue
            if p.expires_at is not None and bar.time >= p.expires_at:
                self._terminal(order, OrderState.EXPIRED, bar, "ORDER_EXPIRED")
                return order
            if order.state == OrderState.PENDING:
                self._transition(order, OrderState.ELIGIBLE, bar.time, "FIRST_ELIGIBLE_EVENT", bar.dataset_id, bar.event_id)
                # Engineering fixture convention: first eligible bar open only.
                self._transition(order, OrderState.FILLED, bar.time, "OHLC_M1_ENGINEERING_OPEN", bar.dataset_id, bar.event_id,
                                 executable_price=bar.open)
                order.fill = order.records[-1]
                break
        if order.state != OrderState.FILLED:
            end = _utc(end_time) if end_time else ordered[-1].close_time
            self._terminal(order, OrderState.EXPIRED, ordered[-1], "NO_ELIGIBLE_EXECUTION")
            return order
        fill_bar_time = order.fill.at
        for bar in ordered:
            if bar.time <= fill_bar_time:
                continue
            kind = self._exit_kind(p, bar)
            if kind is None:
                continue
            self._terminal(order, OrderState.FILLED, bar, kind.value, observation_kind=kind.value)
            order.exit = order.records[-1]
            break
        return order

    @staticmethod
    def _exit_kind(p: ProposalFixture, bar: OHLCM1) -> Optional[ObservationKind]:
        if p.stop_price is None and p.target_price is None:
            return None
        adverse = (bar.low <= p.stop_price) if p.side == "LONG" and p.stop_price is not None else ((bar.high >= p.stop_price) if p.stop_price is not None else False)
        favorable = (bar.high >= p.target_price) if p.side == "LONG" and p.target_price is not None else ((bar.low <= p.target_price) if p.target_price is not None else False)
        if adverse and favorable:
            return ObservationKind.AMBIGUOUS_SEQUENCE
        if adverse:
            return ObservationKind.ADVERSE
        if favorable:
            return ObservationKind.FAVORABLE
        return None

    def _transition(self, order, state, at, reason, dataset_id, event_id, executable_price=None, observation_kind=None):
        record_type = "FILL" if state == OrderState.FILLED and executable_price is not None else "ORDER_TRANSITION"
        payload = [order.order_id, record_type, state.value, str(at), reason, dataset_id, event_id, order.proposal.proposal_id]
        record = ExchangeRecord(record_type, _id(payload), order.order_id, _utc(at), state, reason, dataset_id, event_id,
                                order.proposal.reference_entry.decision_id, order.proposal.proposal_id,
                                order.proposal.reference_entry.reference_price, executable_price, observation_kind, event_id)
        order.records.append(record)
        order.state = state

    def _terminal(self, order, state, bar, reason, *, observation_kind=None):
        self._transition(order, state, bar.time, reason, bar.dataset_id, bar.event_id, observation_kind=observation_kind)
