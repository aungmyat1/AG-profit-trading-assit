"""LastClosedBarStore: the minimal "have we already evaluated this closed bar" tracker
AG_DAYTRADING_RUNTIME_V1 needs (spec EVENT MODEL: "Each closed bar processed at most
once ... persist/track the latest evaluated closed-bar identity per symbol so restart/
replay never reprocesses the same bar into a duplicate proposal").

Audited before adding: no existing "last processed bar timestamp per symbol" mechanism
exists anywhere in this repo (runtime_state/, journal/, src/assistant/status.py were all
checked) -- strategy_engine.sweep_retest.state_store.SweepRetestStateStore tracks a
setup_id's STATE-MACHINE progress, not "which raw closed bar have we already looked at",
a genuinely different question a runtime loop needs answered BEFORE it even builds a
setup_id/evaluates. This is therefore a new, deliberately minimal piece, built on
runtime_state.store.JsonKeyValueStore -- the repo's one established persistence
convention -- same idiom as execution/position_guard.py / daily_loss_guard.py /
close_ledger.py.

Keyed by "{symbol}:{timeframe}" so a restart or a second process instance never
re-evaluates the same closed bar into a duplicate proposal for that symbol/timeframe pair.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from runtime_state.store import JsonKeyValueStore

DEFAULT_PATH = "journal/ag_daytrading_last_closed_bar.json"


@dataclass(frozen=True)
class LastClosedBarStore:
    store: JsonKeyValueStore

    @classmethod
    def default(cls, path: str = DEFAULT_PATH) -> "LastClosedBarStore":
        return cls(JsonKeyValueStore(path))

    @staticmethod
    def _key(symbol: str, timeframe: str) -> str:
        return f"{symbol}:{timeframe}"

    def last_closed_bar_time(self, symbol: str, timeframe: str) -> "datetime | None":
        record = self.store.get(self._key(symbol, timeframe))
        if record is None:
            return None
        return datetime.fromisoformat(record["closed_bar_time"])

    def is_new_bar(self, symbol: str, timeframe: str, bar_time: datetime) -> bool:
        """True iff `bar_time` is strictly newer than the last bar already marked
        processed for this symbol/timeframe (or none has been processed yet)."""
        last = self.last_closed_bar_time(symbol, timeframe)
        return last is None or bar_time > last

    def mark_processed(self, symbol: str, timeframe: str, bar_time: datetime) -> None:
        self.store.put(self._key(symbol, timeframe), {"closed_bar_time": bar_time.isoformat()})
