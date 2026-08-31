"""Persistence: AsianSessionSnapshot / PostAsianDecision / PostAsianEntryProposal, each
in its own runtime_state.store.JsonKeyValueStore-backed file under journal/post_asian_pilot/
(same atomic-write convention as every other journal/* store in this repo) -- plus the
existing execution.bar_tracker.LastClosedBarStore (reused as-is, not reimplemented) for
new-closed-M15-only gating, and the daily governor's own guards/slot store (governor.py).

Idempotency: each save_* function compares a signature of the new record's semantic
fields against whatever is already stored under that identity key (same pattern as
execution.lifecycle's signature-diff duplicate suppression) -- an unchanged re-detection
returns written=False rather than re-persisting/duplicating, so a restart or a repeated
poll on the same closed bar never produces a duplicate decision/proposal or resets state.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Optional

from execution.bar_tracker import LastClosedBarStore
from execution.daily_loss_guard import DailyLossGuard
from execution.position_guard import OpenPositionGuard
from runtime_state.store import JsonKeyValueStore

from .decision import PostAsianDecision
from .governor import DailyTradeLedger
from .proposal import PostAsianEntryProposal
from .snapshot import AsianSessionSnapshot

DEFAULT_STATE_DIR = "journal/post_asian_pilot"


@dataclass(frozen=True)
class PilotStores:
    snapshot_store: JsonKeyValueStore
    decision_store: JsonKeyValueStore
    proposal_store: JsonKeyValueStore
    bar_tracker: LastClosedBarStore
    open_position_guard: OpenPositionGuard  # execution-time only, see governor.py docstring
    daily_loss_guard: DailyLossGuard
    ledger: DailyTradeLedger

    @classmethod
    def default(cls, strategy_id: str, state_dir: str = DEFAULT_STATE_DIR) -> "PilotStores":
        return cls(
            snapshot_store=JsonKeyValueStore(f"{state_dir}/session_snapshot.json"),
            decision_store=JsonKeyValueStore(f"{state_dir}/decision.json"),
            proposal_store=JsonKeyValueStore(f"{state_dir}/proposal.json"),
            bar_tracker=LastClosedBarStore.default(f"{state_dir}/last_closed_bar.json"),
            open_position_guard=OpenPositionGuard.default(),
            daily_loss_guard=DailyLossGuard.default(strategy_id),
            ledger=DailyTradeLedger.default(f"{state_dir}/daily_trade_ledger.json"),
        )


def _session_event_key(strategy_id: str, symbol: str, trading_date, reference_session: str) -> str:
    return f"{strategy_id}|{symbol}|{trading_date.isoformat()}|{reference_session}"


def _signature(record: Dict[str, Any], fields: tuple) -> tuple:
    def _norm(v: Any) -> Any:
        return tuple(v) if isinstance(v, (list, tuple)) else v
    return tuple(_norm(record.get(f)) for f in fields)


def save_snapshot(store: JsonKeyValueStore, snapshot: AsianSessionSnapshot) -> bool:
    key = _session_event_key(snapshot.strategy_id, snapshot.symbol, snapshot.trading_date, snapshot.session_name)
    existing = store.get(key)
    record = dataclasses.asdict(snapshot)
    sig_fields = ("open", "high", "low", "close", "bar_count", "source_fingerprint", "data_quality")
    if existing is not None and _signature(existing, sig_fields) == _signature(record, sig_fields):
        return False
    store.put(key, record)
    return True


def save_decision(store: JsonKeyValueStore, decision: PostAsianDecision) -> bool:
    key = _session_event_key(decision.strategy_id, decision.symbol, decision.trading_date, decision.reference_session)
    existing = store.get(key)
    record = dataclasses.asdict(decision)
    sig_fields = ("status", "reason_codes", "missing_condition")
    if existing is not None and _signature(existing, sig_fields) == _signature(record, sig_fields):
        return False
    store.put(key, record)
    return True


def save_proposal(store: JsonKeyValueStore, proposal: PostAsianEntryProposal) -> bool:
    key = proposal.setup_id
    existing = store.get(key)
    record = dataclasses.asdict(proposal)
    sig_fields = ("trade_proposal",)
    if existing is not None and _signature(existing, sig_fields) == _signature(record, sig_fields):
        return False
    store.put(key, record)
    return True


def get_proposal_record(store: JsonKeyValueStore, setup_id: str) -> Optional[Dict[str, Any]]:
    return store.get(setup_id)


def decision_from_record(record: Dict[str, Any]) -> PostAsianDecision:
    """Reconstructs a PostAsianDecision from a JsonKeyValueStore record -- dates/
    datetimes round-tripped through JSON (default=str) come back as plain strings, so
    this re-parses them rather than passing the raw dict straight into the dataclass.
    `signal` (a TradeSignal) is never persisted in reconstructible form -- always None
    on reload, matching the cached-decision-only use case (no re-evaluation happens)."""
    return PostAsianDecision(
        decision_id=record["decision_id"], strategy_id=record["strategy_id"],
        strategy_version=record["strategy_version"], symbol=record["symbol"],
        trading_date=date.fromisoformat(record["trading_date"]),
        reference_session=record["reference_session"], status=record["status"],
        reason_codes=tuple(record.get("reason_codes") or ()),
        evaluation_time=datetime.fromisoformat(record["evaluation_time"]),
        session_snapshot_id=record.get("session_snapshot_id"), signal=None,
        ready_at=datetime.fromisoformat(record["ready_at"]) if record.get("ready_at") else None,
        missing_condition=record.get("missing_condition"), trigger_type=record.get("trigger_type"),
        trigger_level=record.get("trigger_level"), trigger_timeframe=record.get("trigger_timeframe"),
        valid_until=datetime.fromisoformat(record["valid_until"]) if record.get("valid_until") else None,
    )
