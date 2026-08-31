"""Daily governor: portfolio/risk gates applied to a READY strategy decision before it
becomes actionable. Reuses execution.position_guard.OpenPositionGuard (max_open_positions
== 1, already matches the pilot's own policy exactly) and execution.daily_loss_guard.
DailyLossGuard (the existing, unmodified, project-wide -2R circuit breaker) as-is --
neither is touched or re-parametrized. Adds two genuinely new pieces the project has no
equivalent of: a max-one-new-trade-per-day slot (DailyTradeSlot) and a pilot-specific -1R
strategy loss lock, which reads the SAME realized-R data DailyLossGuard already tracks
(via its own public realized_r()) rather than writing a second, divergent ledger --
"use the stricter effective gate: strategy-specific -1R OR project-wide -2R guard,
whichever blocks first" (spec section 21) -- the project's -2R guard is never weakened.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from execution.daily_loss_guard import DailyLossGuard
from execution.position_guard import OpenPositionGuard
from runtime_state.store import JsonKeyValueStore

DEFAULT_TRADE_SLOT_PATH = "journal/post_asian_pilot/daily_trade_slot.json"

PORTFOLIO_ELIGIBLE = "ELIGIBLE"
PORTFOLIO_BLOCKED = "BLOCKED"

REASON_MAX_OPEN_POSITIONS = "BLOCKED_MAX_OPEN_POSITIONS"
REASON_PROJECT_DAILY_LOSS_GUARD = "BLOCKED_PROJECT_DAILY_LOSS_GUARD"
REASON_STRATEGY_DAILY_LOSS_LOCK = "BLOCKED_STRATEGY_DAILY_LOSS_LOCK"
REASON_DAILY_TRADE_LIMIT = "BLOCKED_DAILY_TRADE_LIMIT"


@dataclass(frozen=True)
class DailyTradeSlot:
    """One new-trade-per-day slot, shared across the pilot's whole universe (not
    per-symbol) -- claiming it for one symbol blocks every other symbol for the rest of
    that trading day. Same JsonKeyValueStore/atomic-write convention as every other
    journal/* store in this repo."""

    store: JsonKeyValueStore

    @classmethod
    def default(cls, path: str = DEFAULT_TRADE_SLOT_PATH) -> "DailyTradeSlot":
        return cls(JsonKeyValueStore(path))

    @staticmethod
    def _key(strategy_id: str, trading_date: date) -> str:
        return f"{strategy_id}:{trading_date.isoformat()}"

    def claimed_by(self, strategy_id: str, trading_date: date) -> Optional[dict]:
        return self.store.get(self._key(strategy_id, trading_date))

    def claim(self, strategy_id: str, trading_date: date, symbol: str, setup_id: str,
              evaluation_time: datetime) -> None:
        self.store.put(self._key(strategy_id, trading_date), {
            "symbol": symbol, "setup_id": setup_id, "claimed_at": evaluation_time.isoformat(),
        })


@dataclass(frozen=True)
class DailyGovernorResult:
    portfolio_state: str  # PORTFOLIO_ELIGIBLE or PORTFOLIO_BLOCKED
    reason_code: Optional[str]


def evaluate_daily_governor(
    strategy_id: str, trading_date: date, symbol: str,
    open_position_guard: OpenPositionGuard, daily_loss_guard: DailyLossGuard,
    trade_slot: DailyTradeSlot, strategy_daily_loss_limit_r: float,
) -> DailyGovernorResult:
    if open_position_guard.is_blocked():
        return DailyGovernorResult(PORTFOLIO_BLOCKED, REASON_MAX_OPEN_POSITIONS)
    if daily_loss_guard.is_blocked(trading_date):
        return DailyGovernorResult(PORTFOLIO_BLOCKED, REASON_PROJECT_DAILY_LOSS_GUARD)
    if daily_loss_guard.realized_r(trading_date) <= strategy_daily_loss_limit_r:
        return DailyGovernorResult(PORTFOLIO_BLOCKED, REASON_STRATEGY_DAILY_LOSS_LOCK)
    claimed = trade_slot.claimed_by(strategy_id, trading_date)
    if claimed is not None and claimed.get("symbol") != symbol:
        return DailyGovernorResult(PORTFOLIO_BLOCKED, REASON_DAILY_TRADE_LIMIT)
    return DailyGovernorResult(PORTFOLIO_ELIGIBLE, None)
