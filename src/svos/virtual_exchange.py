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


SAME_BAR_POLICY = "AMBIGUOUS_SEQUENCE_NO_ASSUMED_INTRABAR_ORDER"
OHLC_AMBIGUITY_VERSION = "VD_OHLC_AMBIGUITY_V1"
OHLC_AMBIGUITY_CONTRACT = {
    "schema_version": OHLC_AMBIGUITY_VERSION,
    "purpose": "STRATEGY_CAPACITY_VALIDATION",
    "simulator_version": "SVOS_VIRTUAL_DEMO_ENGINE_V1_CYCLE3B",
    "strategy_semantics_boundary": "SSC v1.0.1 strategy rules are frozen and unchanged; simulator execution/accounting only",
    "policy": SAME_BAR_POLICY,
    "supported_classes": [
        "entry_plus_sl",
        "entry_plus_target",
        "sl_plus_target",
        "multiple_targets",
        "gap_cross",
        "unknown_chronology",
    ],
    "rules": {
        "entry_plus_sl": "If the fill bar also touches the stop, treat as AMBIGUOUS_SEQUENCE; never assume the stop was reached before the fill.",
        "entry_plus_target": "If the fill bar also touches the target, treat as AMBIGUOUS_SEQUENCE; never assume the target was reached after the fill.",
        "sl_plus_target": "If a later bar touches both stop and target, treat as AMBIGUOUS_SEQUENCE; no favorable-order inference.",
        "multiple_targets": "When multiple equivalent target levels are touched in one bar, the bar remains AMBIGUOUS_SEQUENCE unless a stricter project model proves sequence order.",
        "gap_cross": "A bar whose range crosses a stop/target without a later proven order remains AMBIGUOUS_SEQUENCE; no future-bar inspection is allowed.",
        "unknown_chronology": "If the bar chronology is not provable from the admitted OHLC evidence, fail closed to AMBIGUOUS_SEQUENCE.",
    },
    "fail_closed": True,
    "no_favorable_order_inference": True,
    "no_future_bar_inspection": True,
    "no_random_ordering": True,
    "strategy_boundary": "same as SSC v1.0.1 semantics; this contract governs simulator accounting only",
}


def _canonical_contract_payload() -> dict:
    payload = dict(OHLC_AMBIGUITY_CONTRACT)
    payload.pop("sha256", None)
    return json.loads(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _contract_body_for_hash(contract: Optional[dict]) -> dict:
    payload = dict(contract) if contract is not None else _canonical_contract_payload()
    payload.pop("sha256", None)
    return json.loads(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str))


def compute_ambiguity_contract_hash(*, contract: Optional[dict] = None) -> str:
    payload = _contract_body_for_hash(contract)
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "sha256:" + hashlib.sha256(body).hexdigest()


OHLC_AMBIGUITY_HASH = compute_ambiguity_contract_hash()
OHLC_AMBIGUITY_CONTRACT["sha256"] = OHLC_AMBIGUITY_HASH


def validate_ambiguity_contract(*, contract: Optional[dict] = None) -> str:
    payload = dict(contract) if contract is not None else dict(OHLC_AMBIGUITY_CONTRACT)
    expected = payload.get("sha256")
    if expected is None:
        raise ExchangeError("OHLC_AMBIGUITY_CONTRACT_MISSING_HASH")
    digest = compute_ambiguity_contract_hash(contract=payload)
    if digest != expected:
        raise ExchangeError("OHLC_AMBIGUITY_CONTRACT_DRIFT")
    return digest


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

    def advance(self, bar: OHLCM1) -> VirtualOrder:
        """Consume one closed M1 observation without looking ahead to later bars.

        Same-bar fill/exit chronology is intentionally fail-closed: when the fill bar also
        touches a stop or target, the simulator treats the sequence as
        `AMBIGUOUS_SEQUENCE` rather than assuming favorable ordering from the OHLC range.
        """
        if self._order is None:
            raise ExchangeError("NO_ORDER")
        order = self._order
        p = order.proposal
        if bar.symbol != p.symbol or bar.dataset_id != p.dataset_id or not bar.event_id:
            raise ExchangeError("MISMATCHED_SYMBOL_OR_DATASET")
        if order.exit is not None or order.state in {OrderState.EXPIRED, OrderState.REJECTED, OrderState.CANCELLED}:
            return order
        if bar.time <= p.decision_cutoff:
            return order
        if p.expires_at is not None and bar.time >= p.expires_at and order.fill is None:
            self._terminal(order, OrderState.EXPIRED, bar, "ORDER_EXPIRED")
            return order
        if order.fill is None:
            self._transition(order, OrderState.ELIGIBLE, bar.time, "FIRST_ELIGIBLE_EVENT", bar.dataset_id, bar.event_id)
            self._transition(order, OrderState.FILLED, bar.time, "OHLC_M1_ENGINEERING_OPEN", bar.dataset_id, bar.event_id,
                             executable_price=bar.open)
            order.fill = order.records[-1]
            same_bar_kind = self._same_bar_exit_kind(p, bar)
            if same_bar_kind is not None:
                level = None if same_bar_kind is ObservationKind.AMBIGUOUS_SEQUENCE else (
                    p.stop_price if same_bar_kind is ObservationKind.ADVERSE else p.target_price
                )
                self._terminal(order, OrderState.FILLED, bar, same_bar_kind.value,
                               observation_kind=same_bar_kind.value, executable_price=level)
                order.exit = order.records[-1]
            return order
        if bar.time <= order.fill.at:
            return order
        kind = self._exit_kind(p, bar)
        if kind is not None:
            level = None if kind is ObservationKind.AMBIGUOUS_SEQUENCE else (p.stop_price if kind is ObservationKind.ADVERSE else p.target_price)
            self._terminal(order, OrderState.FILLED, bar, kind.value, observation_kind=kind.value,
                           executable_price=level)
            order.exit = order.records[-1]
        return order

    def end_of_data(self, *, at: datetime, event_id: str) -> VirtualOrder:
        if self._order is None:
            raise ExchangeError("NO_ORDER")
        order = self._order
        if order.fill is None and order.state == OrderState.PENDING:
            self._transition(order, OrderState.EXPIRED, at, "END_OF_DATA_PENDING",
                             order.proposal.dataset_id, event_id)
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
                same_bar_kind = self._same_bar_exit_kind(p, bar)
                if same_bar_kind is not None:
                    level = None if same_bar_kind is ObservationKind.AMBIGUOUS_SEQUENCE else (
                        p.stop_price if same_bar_kind is ObservationKind.ADVERSE else p.target_price
                    )
                    self._terminal(order, OrderState.FILLED, bar, same_bar_kind.value,
                                   observation_kind=same_bar_kind.value, executable_price=level)
                    order.exit = order.records[-1]
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
            level = None if kind is ObservationKind.AMBIGUOUS_SEQUENCE else (p.stop_price if kind is ObservationKind.ADVERSE else p.target_price)
            self._terminal(order, OrderState.FILLED, bar, kind.value, observation_kind=kind.value,
                           executable_price=level)
            order.exit = order.records[-1]
            break
        return order

    @staticmethod
    def _same_bar_exit_kind(p: ProposalFixture, bar: OHLCM1) -> Optional[ObservationKind]:
        """same-bar fill chronology is never proven by OHLC alone; fail closed.

        This preserves the repository's no-favorable-order-inference rule: if the fill bar
        also touches the stop or target, the simulator cannot infer whether the order or
        the risk level happened first, so it must record AMBIGUOUS_SEQUENCE.
        """
        if p.stop_price is None and p.target_price is None:
            return None
        adverse = (bar.low <= p.stop_price) if p.side == "LONG" and p.stop_price is not None else ((bar.high >= p.stop_price) if p.stop_price is not None else False)
        favorable = (bar.high >= p.target_price) if p.side == "LONG" and p.target_price is not None else ((bar.low <= p.target_price) if p.target_price is not None else False)
        if adverse or favorable:
            return ObservationKind.AMBIGUOUS_SEQUENCE
        return None

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
        record_type = "FILL" if state == OrderState.FILLED and executable_price is not None and order.fill is None else "ORDER_TRANSITION"
        payload = [order.order_id, record_type, state.value, str(at), reason, dataset_id, event_id, order.proposal.proposal_id]
        record = ExchangeRecord(record_type, _id(payload), order.order_id, _utc(at), state, reason, dataset_id, event_id,
                                order.proposal.reference_entry.decision_id, order.proposal.proposal_id,
                                order.proposal.reference_entry.reference_price, executable_price, observation_kind, event_id)
        order.records.append(record)
        order.state = state

    def _terminal(self, order, state, bar, reason, *, observation_kind=None, executable_price=None):
        self._transition(order, state, bar.time, reason, bar.dataset_id, bar.event_id,
                         executable_price=executable_price, observation_kind=observation_kind)
