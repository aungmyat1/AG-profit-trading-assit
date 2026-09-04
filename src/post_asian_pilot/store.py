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

from strategy_engine.models import TradeSignal

from .decision import PostAsianDecision
from .governor import DailyTradeLedger
from .monitor import MonitoringCounters
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
    counters: MonitoringCounters

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
            counters=MonitoringCounters.default(f"{state_dir}/monitoring_counters.json"),
        )


def _session_event_key(strategy_id: str, symbol: str, trading_date, reference_session: str) -> str:
    return f"{strategy_id}|{symbol}|{trading_date.isoformat()}|{reference_session}"


def _signature(record: Dict[str, Any], fields: tuple) -> tuple:
    def _norm(v: Any) -> Any:
        return tuple(v) if isinstance(v, (list, tuple)) else v
    return tuple(_norm(record.get(f)) for f in fields)


class SnapshotImmutabilityViolation(RuntimeError):
    """Raised when a second write for the same (strategy_id, symbol, trading_date,
    session) identity carries different OHLC/bar_count/fingerprint than the frozen
    snapshot already on disk. A snapshot, once frozen, is immutable -- this is never
    silently overwritten, only ever confirmed-identical (idempotent no-op) or rejected."""


_SNAPSHOT_IDENTITY_FIELDS = ("open", "high", "low", "close", "bar_count", "source_fingerprint", "data_quality")


def save_snapshot(store: JsonKeyValueStore, snapshot: AsianSessionSnapshot) -> bool:
    key = _session_event_key(snapshot.strategy_id, snapshot.symbol, snapshot.trading_date, snapshot.session_name)
    existing = store.get(key)
    record = dataclasses.asdict(snapshot)
    if existing is not None:
        if _signature(existing, _SNAPSHOT_IDENTITY_FIELDS) == _signature(record, _SNAPSHOT_IDENTITY_FIELDS):
            return False  # identical re-freeze -- idempotent no-op, not a re-write
        raise SnapshotImmutabilityViolation(
            f"SNAPSHOT_IMMUTABILITY_VIOLATION: {key} already frozen with different "
            f"OHLC/bar_count/fingerprint -- refusing to overwrite")
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


def _signal_from_record(raw: Optional[Dict[str, Any]]) -> Optional[TradeSignal]:
    """TradeSignal IS the normalized, authoritative strategy evidence the spec asks for
    (setup/direction/entry/stop_loss/risk_distance/signal_timestamp/box_high/box_low/
    box_mid/reason_code, all already the exact fields build_entry_proposal() needs) --
    dataclasses.asdict(decision) already recursively serializes it into the persisted
    decision record (save_decision()), so restart recovery only ever needs to re-parse
    it, never re-run the strategy or invent evidence. Returns None only when the
    persisted decision genuinely never carried a signal (WATCH/DATA_ERROR states)."""
    if raw is None:
        return None
    return TradeSignal(
        signal_id=raw["signal_id"], strategy_id=raw["strategy_id"], strategy_version=raw["strategy_version"],
        symbol=raw["symbol"], pair_id=raw["pair_id"], reference_session=raw["reference_session"],
        session_date=date.fromisoformat(raw["session_date"]), box_high=raw["box_high"], box_low=raw["box_low"],
        box_mid=raw["box_mid"], regime=raw["regime"], setup=raw["setup"], status=raw["status"],
        reason_code=raw["reason_code"], direction=raw.get("direction"), entry=raw.get("entry"),
        stop_loss=raw.get("stop_loss"), risk_distance=raw.get("risk_distance"),
        signal_timestamp=datetime.fromisoformat(raw["signal_timestamp"]) if raw.get("signal_timestamp") else None,
    )


def decision_from_record(record: Dict[str, Any]) -> PostAsianDecision:
    """Reconstructs a PostAsianDecision from a JsonKeyValueStore record -- dates/
    datetimes round-tripped through JSON (default=str) come back as plain strings, so
    this re-parses them rather than passing the raw dict straight into the dataclass.
    `signal` is reconstructed from the persisted nested TradeSignal record (see
    _signal_from_record) -- restart/crash recovery needs this to rebuild the SAME
    proposal identity without re-evaluating the strategy against later data."""
    return PostAsianDecision(
        decision_id=record["decision_id"], strategy_id=record["strategy_id"],
        strategy_version=record["strategy_version"], symbol=record["symbol"],
        trading_date=date.fromisoformat(record["trading_date"]),
        reference_session=record["reference_session"], status=record["status"],
        reason_codes=tuple(record.get("reason_codes") or ()),
        evaluation_time=datetime.fromisoformat(record["evaluation_time"]),
        session_snapshot_id=record.get("session_snapshot_id"), signal=_signal_from_record(record.get("signal")),
        ready_at=datetime.fromisoformat(record["ready_at"]) if record.get("ready_at") else None,
        missing_condition=record.get("missing_condition"), trigger_type=record.get("trigger_type"),
        trigger_level=record.get("trigger_level"), trigger_timeframe=record.get("trigger_timeframe"),
        valid_until=datetime.fromisoformat(record["valid_until"]) if record.get("valid_until") else None,
    )


def find_decision(
    store: JsonKeyValueStore, strategy_id: str, symbol: str, trading_date: date,
    reference_session_name: Optional[str] = None,
) -> Optional[PostAsianDecision]:
    """Read-only lookup tolerant of the reference_session display-name mismatch between
    the pilot config (config/canonical_sessions.yaml-sourced, e.g. "asian"/"london_am")
    and the strategy YAML (session_pairs[].reference_session.name, e.g. "Asian"/
    "London", copied verbatim onto TradeSignal.reference_session by strategy_engine and
    therefore onto any decision derived from a real evaluation -- see
    map_trade_signal_to_decision). These are not always a simple casing difference --
    "London" vs "london_am" differ by more than case -- so a case-insensitive string
    match alone is not sufficient; this does not persist, rewrite, or invent a new
    record, it only changes how an existing one is found.

    Matches on the (strategy_id, symbol, trading_date) identity alone, ignoring
    reference_session entirely: each pilot cycle (ASIAN_LONDON, LONDON_NEWYORK) already
    persists to its own isolated state_dir/decision store (see PilotConfig.state_dir /
    PilotStores.default), so within one store this triple is already the real identity
    -- reference_session was never needed to disambiguate across cycles, only within a
    single cycle's own file, where at most one genuinely distinct real-world decision
    exists per (symbol, date). If more than one record happens to match (e.g. a stale
    pre-close WATCH saved under the pilot-config-cased key alongside a later real
    evaluation saved under the strategy-YAML-cased key), the one with the latest
    evaluation_time wins -- the terminal, most-recently-recorded decision, matching
    render_pilot_end_report's own "report actual recorded state" contract. Any single
    caller-supplied reference_session_name is accepted for backward-compatible call
    signatures but no longer affects the result -- kept optional rather than required."""
    del reference_session_name  # no longer used for matching -- see docstring
    prefix = f"{strategy_id}|{symbol}|{trading_date.isoformat()}|"
    candidates = [decision_from_record(record) for key, record in store.all().items()
                 if key.startswith(prefix)]
    if not candidates:
        return None
    return max(candidates, key=lambda d: d.evaluation_time)
