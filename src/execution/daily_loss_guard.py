"""Shared, strategy-agnostic daily realized-R circuit breaker -- a genuinely NEW minimal
piece (added 2026-08-30 for ST_SESSION_SWEEP_RETEST_V1). No existing module tracked
realized R per strategy per trading day, so this is not a reuse of prior logic. Built on
runtime_state.store.JsonKeyValueStore, same convention as execution/position_guard.py
(see that module's docstring for why both live in execution/, not strategy-local).

Keyed by "{strategy_id}:{trading_day.isoformat()}" so the breaker resets automatically at
the next UTC trading day -- no separate reset job is needed; a new day is simply a key
that has never been written and therefore reads back as 0.0 realized R.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from runtime_state.store import JsonKeyValueStore

DEFAULT_PATH = "journal/ag_strategy_daily_realized_r.json"
DAILY_LOSS_CIRCUIT_R = -2.0


@dataclass(frozen=True)
class DailyLossGuard:
    store: JsonKeyValueStore
    strategy_id: str

    @classmethod
    def default(cls, strategy_id: str, path: str = DEFAULT_PATH) -> "DailyLossGuard":
        return cls(JsonKeyValueStore(path), strategy_id)

    def _key(self, trading_day: date) -> str:
        return f"{self.strategy_id}:{trading_day.isoformat()}"

    def realized_r(self, trading_day: date) -> float:
        record = self.store.get(self._key(trading_day))
        return float(record["realized_r"]) if record else 0.0

    def is_blocked(self, trading_day: date) -> bool:
        return self.realized_r(trading_day) <= DAILY_LOSS_CIRCUIT_R

    def record_trade_result(self, trading_day: date, r_multiple: float) -> float:
        key = self._key(trading_day)
        total = self.realized_r(trading_day) + r_multiple
        self.store.put(key, {"realized_r": total})
        return total
