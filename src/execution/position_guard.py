"""Shared, strategy-agnostic open-position guard persisted through
runtime_state.store.JsonKeyValueStore. No-symbol calls preserve the original GLOBAL
cross-strategy cap. A caller may explicitly pass ``symbol=`` to count/apply the separate
per-symbol cap; ST_LIQUIDITY_SWEEP_RETEST_V1 opts into that scope in its engine, while
all existing no-symbol callers remain global.

The guard stays in execution/ (not inside strategy_engine/sweep_retest/, which is
strategy-local) so any AG strategy can register/release positions through the shared
store. Open-position registration remains keyed by position_id and includes symbol
metadata for optional symbol-scoped reads.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from runtime_state.store import JsonKeyValueStore

DEFAULT_PATH = "journal/ag_open_strategy_positions.json"
MAX_OPEN_STRATEGY_POSITIONS = 1
MAX_OPEN_POSITIONS_PER_SYMBOL = 1


@dataclass(frozen=True)
class OpenPositionGuard:
    store: JsonKeyValueStore

    @classmethod
    def default(cls, path: str = DEFAULT_PATH) -> "OpenPositionGuard":
        return cls(JsonKeyValueStore(path))

    def open_count(self, symbol: Optional[str] = None) -> int:
        records = self.store.all()
        if symbol is None:
            return len(records)
        return sum(
            1
            for record in records.values()
            if isinstance(record, dict) and record.get("symbol") == symbol
        )

    def is_blocked(self, symbol: Optional[str] = None) -> bool:
        if symbol is None:
            return self.open_count() >= MAX_OPEN_STRATEGY_POSITIONS
        return self.open_count(symbol=symbol) >= MAX_OPEN_POSITIONS_PER_SYMBOL

    def register_open(self, position_id: str, strategy_id: str, symbol: str, *,
                       setup_id: Optional[str] = None, risk_amount: Optional[float] = None,
                       volume: Optional[float] = None) -> None:
        """position_id is the compound-identity key -- AG_GLOBAL_EXECUTION_LIFECYCLE_V1
        callers key it by the broker ticket (the one truly stable, restart-safe identity;
        see execution/lifecycle.py), never by symbol alone. setup_id/risk_amount/volume
        are optional so existing callers that only ever cared about "is a slot occupied"
        (e.g. tests that register a synthetic position_id string with no broker ticket)
        keep working unchanged -- the extra fields exist only so a later close/reconcile
        (lifecycle.py) can recover the ORIGINAL risk_amount for realized-R math without a
        second parallel store."""
        record = {"strategy_id": strategy_id, "symbol": symbol}
        if setup_id is not None:
            record["setup_id"] = setup_id
        if risk_amount is not None:
            record["risk_amount"] = risk_amount
        if volume is not None:
            record["volume"] = volume
        self.store.put(position_id, record)

    def register_closed(self, position_id: str) -> None:
        self.store.remove(position_id)
