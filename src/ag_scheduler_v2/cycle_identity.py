"""Exactly-once M15 cycle identity and observation-mode classification (spec sections
9-11). Every M15 evaluation has a deterministic identity of
(strategy_id, symbol, session_pair, bar_close_utc); completed identities are persisted
so a restart never re-processes the same live bar as a second live observation.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Optional

from runtime_state.store import JsonKeyValueStore

LIVE_WINDOW = "LIVE_WINDOW"
CATCH_UP = "CATCH_UP"
DUPLICATE_SKIP = "DUPLICATE_SKIP"

_DEFAULT_STORE_PATH = "journal/ag_scheduler_v2/completed_cycles.json"


def cycle_id(*, strategy_id: str, symbol: str, session_pair: str, bar_close_utc: dt.datetime) -> str:
    if bar_close_utc.tzinfo is None:
        raise ValueError("TIMEZONE_NAIVE_TIMESTAMP: bar_close_utc must be tz-aware UTC")
    ts = bar_close_utc.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{strategy_id}|{symbol}|{session_pair}|{ts}"


@dataclass(frozen=True)
class CompletedCycleRecord:
    cycle_id: str
    strategy_id: str
    symbol: str
    session_pair: str
    bar_close_utc: str
    observation_mode: str  # LIVE_WINDOW | CATCH_UP -- never changed after being written
    completed_at_utc: str


class CompletedCycleStore:
    """Persists completed cycle identities so restart recovery does not depend on
    process memory (spec section 4). Backed by the project's existing atomic
    JsonKeyValueStore -- not a new persistence primitive."""

    def __init__(self, path: str = _DEFAULT_STORE_PATH):
        self._store = JsonKeyValueStore(path)

    def classify(
        self,
        *,
        strategy_id: str,
        symbol: str,
        session_pair: str,
        bar_close_utc: dt.datetime,
        is_recovered: bool,
    ) -> str:
        """Returns LIVE_WINDOW, CATCH_UP, or DUPLICATE_SKIP without mutating state.
        `is_recovered=True` means the caller is reconstructing a bar it did not see at
        its natural close time (i.e. running through recovery.py), never a live path."""
        cid = cycle_id(strategy_id=strategy_id, symbol=symbol, session_pair=session_pair, bar_close_utc=bar_close_utc)
        if self._store.get(cid) is not None:
            return DUPLICATE_SKIP
        return CATCH_UP if is_recovered else LIVE_WINDOW

    def mark_completed(
        self,
        *,
        strategy_id: str,
        symbol: str,
        session_pair: str,
        bar_close_utc: dt.datetime,
        observation_mode: str,
        now_utc: dt.datetime,
    ) -> CompletedCycleRecord:
        if observation_mode not in (LIVE_WINDOW, CATCH_UP):
            raise ValueError(f"INVALID_OBSERVATION_MODE: {observation_mode!r} must be LIVE_WINDOW or CATCH_UP")
        cid = cycle_id(strategy_id=strategy_id, symbol=symbol, session_pair=session_pair, bar_close_utc=bar_close_utc)
        existing = self._store.get(cid)
        if existing is not None:
            # Immutable once written (spec section 11): never overwrite an existing
            # observation_mode, even with an identical one.
            return CompletedCycleRecord(**existing)
        record = CompletedCycleRecord(
            cycle_id=cid,
            strategy_id=strategy_id,
            symbol=symbol,
            session_pair=session_pair,
            bar_close_utc=bar_close_utc.astimezone(dt.timezone.utc).isoformat(),
            observation_mode=observation_mode,
            completed_at_utc=now_utc.astimezone(dt.timezone.utc).isoformat(),
        )
        self._store.put(cid, dataclasses_asdict(record))
        return record

    def is_completed(self, cid: str) -> bool:
        return self._store.get(cid) is not None

    def get(self, cid: str) -> Optional[CompletedCycleRecord]:
        raw = self._store.get(cid)
        return CompletedCycleRecord(**raw) if raw is not None else None

    def all_completed(self) -> dict:
        return self._store.all()


def dataclasses_asdict(record: CompletedCycleRecord) -> dict:
    return {
        "cycle_id": record.cycle_id,
        "strategy_id": record.strategy_id,
        "symbol": record.symbol,
        "session_pair": record.session_pair,
        "bar_close_utc": record.bar_close_utc,
        "observation_mode": record.observation_mode,
        "completed_at_utc": record.completed_at_utc,
    }
