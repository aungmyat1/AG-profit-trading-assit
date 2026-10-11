"""CloseLedger: a genuinely NEW minimal piece, added for AG_GLOBAL_EXECUTION_LIFECYCLE_V1.

Answers exactly one question, durably and restart-safe: "has a FULL close already been
recorded into the global realized-R ledger for this position_id?" Nothing in the repo
tracked this before -- OpenPositionGuard only ever tracked "is a slot occupied right now"
(and removing a record from it is not itself an audit trail), and DailyLossGuard only
ever tracked a running SUM, with no per-position idempotency memory of its own.

Deliberately decoupled from OpenPositionGuard: a position leaving the open guard
(register_closed) and a position's realized-R having been recorded are two separate
facts. Keeping them in two stores means a close whose realized-PnL could not yet be
obtained (see execution/lifecycle.py's DEALS_UNAVAILABLE case) can still safely leave the
open guard (the position is truly gone from the broker) while remaining un-recorded here,
so a LATER reconciliation pass can still record it once data is available -- without ever
double-counting once it succeeds. Built on runtime_state.store.JsonKeyValueStore, the same
convention as position_guard.py/daily_loss_guard.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from runtime_state.store import JsonKeyValueStore

DEFAULT_PATH = "journal/ag_closed_position_realized_r.json"


@dataclass(frozen=True)
class CloseLedger:
    store: JsonKeyValueStore

    @classmethod
    def default(cls, path: str = DEFAULT_PATH) -> "CloseLedger":
        return cls(JsonKeyValueStore(path))

    def is_recorded(self, position_id: str) -> bool:
        return self.store.get(position_id) is not None

    def mark_recorded(self, position_id: str, *, realized_pnl: Optional[float],
                       realized_r: Optional[float], strategy_id: Optional[str],
                       symbol: Optional[str]) -> None:
        self.store.put(position_id, {
            "realized_pnl": realized_pnl,
            "realized_r": realized_r,
            "strategy_id": strategy_id,
            "symbol": symbol,
        })
