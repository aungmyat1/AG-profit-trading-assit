"""Shared, strategy-agnostic global open-position guard -- a genuinely NEW minimal piece
(added 2026-08-30 for ST_SESSION_SWEEP_RETEST_V1). No existing module coordinated "how
many AG strategy positions may be open at once" across strategies, so this is not a reuse
of a prior guard. It is deliberately placed here in execution/ (not inside
strategy_engine/sweep_retest/, which is strategy-local) and built on
runtime_state.store.JsonKeyValueStore -- the repo's one established persistence
convention (see runtime_state/store.py and trade_management/claims.py) -- so any other
AG strategy can register/release positions through the same shared file later.

ST_ASIAN_SWEEP_5R_V1 does not call this yet; wiring existing strategies into this guard
is out of this change's scope (see status report GAPS).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from runtime_state.store import JsonKeyValueStore

DEFAULT_PATH = "journal/ag_open_strategy_positions.json"
MAX_OPEN_STRATEGY_POSITIONS = 1


@dataclass(frozen=True)
class OpenPositionGuard:
    store: JsonKeyValueStore

    @classmethod
    def default(cls, path: str = DEFAULT_PATH) -> "OpenPositionGuard":
        return cls(JsonKeyValueStore(path))

    def open_count(self) -> int:
        return len(self.store.all())

    def is_blocked(self) -> bool:
        return self.open_count() >= MAX_OPEN_STRATEGY_POSITIONS

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
