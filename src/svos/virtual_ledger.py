"""Append-only, deterministic evidence ledger and account replay."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional, Tuple

from .virtual_account import VirtualAccount
from .virtual_exchange import ExchangeRecord, OrderState


class LedgerError(ValueError):
    pass


SCHEMA_VERSION = "VD_LEDGER_V1"


def _utc(v):
    if v.tzinfo is None or v.utcoffset() is None:
        raise LedgerError("ledger timestamps must be timezone-aware")
    return v.astimezone(timezone.utc)


def _hash(v):
    return "sha256:" + hashlib.sha256(json.dumps(v, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@dataclass(frozen=True)
class VirtualLedgerEvent:
    event_id: str
    sequence: int
    event_type: str
    at: datetime
    dataset_id: str
    source_event_id: str
    strategy_id: Optional[str]
    strategy_version: Optional[str]
    decision_id: Optional[str]
    proposal_id: Optional[str]
    order_id: Optional[str]
    fill_id: Optional[str]
    position_id: Optional[str]
    account_snapshot_id: Optional[str]
    parent_event_ids: Tuple[str, ...]
    payload: dict
    payload_hash: str
    previous_hash: Optional[str]
    record_hash: str
    economic_authority: bool = False


class VirtualLedger:
    def __init__(self):
        self.events: list[VirtualLedgerEvent] = []
        self._by_id: dict[str, VirtualLedgerEvent] = {}
        self._by_source: dict[tuple[str, str], VirtualLedgerEvent] = {}

    @property
    def terminal_hash(self) -> Optional[str]:
        return self.events[-1].record_hash if self.events else None

    def append(self, *, event_type: str, at: datetime, dataset_id: str,
               source_event_id: str, payload: dict, parent_event_ids: Iterable[str] = (),
               strategy_id=None, strategy_version=None, decision_id=None,
               proposal_id=None, order_id=None, fill_id=None, position_id=None,
               account_snapshot_id=None, economic_authority=False) -> VirtualLedgerEvent:
        at = _utc(at)
        parents = tuple(parent_event_ids)
        if not event_type or not dataset_id or not source_event_id:
            raise LedgerError("missing ledger identity")
        if any(p not in self._by_id for p in parents):
            raise LedgerError("MISSING_CAUSAL_PARENT")
        payload_hash = _hash(payload)
        source_key = (event_type, source_event_id)
        source_existing = self._by_source.get(source_key)
        if source_existing is not None:
            if source_existing.payload_hash != payload_hash:
                raise LedgerError("CONFLICTING_DUPLICATE_EVENT")
            return source_existing
        semantic = [SCHEMA_VERSION, event_type, str(at), dataset_id, source_event_id,
                    strategy_id, strategy_version, decision_id, proposal_id, order_id,
                    fill_id, position_id, account_snapshot_id, parents, payload_hash,
                    bool(economic_authority)]
        event_id = _hash(semantic)
        existing = self._by_id.get(event_id)
        if existing:
            return existing
        sequence = len(self.events)
        previous = self.terminal_hash
        record_hash = _hash([SCHEMA_VERSION, sequence, event_id, previous])
        event = VirtualLedgerEvent(event_id, sequence, event_type, at, dataset_id,
                                   source_event_id, strategy_id, strategy_version,
                                   decision_id, proposal_id, order_id, fill_id,
                                   position_id, account_snapshot_id, parents,
                                   dict(payload), payload_hash, previous, record_hash,
                                   bool(economic_authority))
        self.events.append(event)
        self._by_id[event_id] = event
        self._by_source[source_key] = event
        return event

    def verify(self) -> None:
        prior = None
        for i, event in enumerate(self.events):
            if event.sequence != i or event.previous_hash != prior:
                raise LedgerError("HASH_CHAIN_MISMATCH")
            if event.payload_hash != _hash(event.payload):
                raise LedgerError("PAYLOAD_HASH_MISMATCH")
            if any(parent not in self._by_id for parent in event.parent_event_ids):
                raise LedgerError("MISSING_CAUSAL_PARENT")
            if event.record_hash != _hash([SCHEMA_VERSION, i, event.event_id, prior]):
                raise LedgerError("HASH_CHAIN_MISMATCH")
            prior = event.record_hash

    def append_exchange_record(self, record: ExchangeRecord, *, strategy_id: str,
                               strategy_version: str, side: Optional[str] = None,
                               stop_price=None, target_price=None,
                               parent_event_ids: Iterable[str] = ()) -> VirtualLedgerEvent:
        payload = {
            "record_type": record.record_type, "state": record.state.value,
            "reason": record.reason, "event_id": record.event_id,
            "reference_price": record.reference_price,
            "executable_price": record.executable_price,
            "observation_kind": record.observation_kind,
            "evidence_event_id": record.evidence_event_id,
            "symbol": side and "EURUSD" or None, "side": side,
            "stop_price": stop_price, "target_price": target_price,
        }
        return self.append(event_type="VirtualFill" if record.record_type == "FILL" else "VirtualOutcome",
                           at=record.at, dataset_id=record.dataset_id, source_event_id=record.event_id,
                           payload=payload, parent_event_ids=parent_event_ids,
                           strategy_id=strategy_id, strategy_version=strategy_version,
                           decision_id=record.decision_id, proposal_id=record.proposal_id,
                           order_id=record.order_id, fill_id=record.record_id if record.record_type == "FILL" else None,
                           economic_authority=False)

    def replay_account(self, *, starting_engineering_balance=0.0, max_open_positions=1) -> VirtualAccount:
        self.verify()
        account = VirtualAccount(starting_engineering_balance=starting_engineering_balance,
                                 max_open_positions=max_open_positions)
        fills = {}
        for event in self.events:
            if event.event_type not in {"VirtualFill", "VirtualOutcome"}:
                continue
            p = event.payload
            record = ExchangeRecord(
                p["record_type"], event.fill_id or event.event_id, event.order_id,
                event.at, OrderState.FILLED, p["reason"], event.dataset_id,
                p["event_id"], event.decision_id, event.proposal_id,
                p.get("reference_price"), p.get("executable_price"),
                p.get("observation_kind"), p.get("evidence_event_id"))
            if event.event_type == "VirtualFill":
                fills[event.order_id] = record
                account.apply_fill(record, strategy_id=event.strategy_id or "UNRESOLVED",
                                   strategy_version=event.strategy_version or "UNRESOLVED",
                                   symbol=p.get("symbol") or "EURUSD", side=p.get("side") or "LONG",
                                   stop_price=p.get("stop_price"), target_price=p.get("target_price"))
            elif event.event_type == "VirtualOutcome":
                account.apply_exit(record)
        return account
