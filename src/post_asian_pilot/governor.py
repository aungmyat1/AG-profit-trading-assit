"""Daily governor: portfolio/risk gates applied to a READY strategy decision before it
becomes actionable.

DailyTradeLedger (NOT a singleton slot): up to `max_slots` (2) distinct opportunities per
strategy_id+trading_date, at most `max_slots_per_symbol` (1) of them for any one symbol.
EURUSD and GBPUSD can BOTH be SELECTED the same day -- the exact-timestamp priority order
only decides slot INDEX (which one is slot #1 vs #2) when two candidates share the exact
same ready_at, never exclusion. A slot, once claimed, stays consumed for the trading date
regardless of its terminal outcome (EXECUTED/EXPIRED/DECLINED never free it back up) --
only an explicit administrative operation could ever release one, and this pilot does not
implement that.

Reuses execution.daily_loss_guard.DailyLossGuard (the existing, unmodified, project-wide
-2R circuit breaker) as-is -- never touched or re-parametrized. Adds a pilot-specific -1R
strategy loss lock that reads the SAME realized-R data via DailyLossGuard's own public
realized_r() rather than writing a second, divergent ledger.

execution.position_guard.OpenPositionGuard is deliberately NOT consulted at
selection/claim time -- daily trade capacity (how many opportunities may be SELECTED) and
concurrent-position capacity (how many may be OPEN at once) are separate concerns
(spec section 17): a second symbol may still claim a ledger slot while the first is
executed and open; only an actual EXECUTION attempt on the second is blocked
(evaluate_execution_eligibility(), for the later, separate explicit-execution workflow --
never called by this package's own selection pipeline).
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Dict, List, Optional

from execution.daily_loss_guard import DailyLossGuard
from execution.position_guard import OpenPositionGuard
from runtime_state.store import JsonKeyValueStore

DEFAULT_LEDGER_PATH = "journal/post_asian_pilot/daily_trade_ledger.json"
SCHEMA_VERSION = "AG_DAILY_TRADE_LEDGER_V1"

DEFAULT_MAX_SLOTS = 2
DEFAULT_MAX_SLOTS_PER_SYMBOL = 1

PORTFOLIO_ELIGIBLE = "ELIGIBLE"
PORTFOLIO_SELECTED = "SELECTED"
PORTFOLIO_BLOCKED = "BLOCKED"

REASON_PROJECT_DAILY_LOSS_GUARD = "BLOCKED_PROJECT_DAILY_LOSS_GUARD"
REASON_STRATEGY_DAILY_LOSS_LOCK = "BLOCKED_STRATEGY_DAILY_LOSS_LOCK"
REASON_STRATEGY_DAILY_LOSS_LIMIT_EXECUTION = "BLOCKED_STRATEGY_DAILY_LOSS_LIMIT"  # execution-time wording, spec section 19
REASON_DAILY_TRADE_LIMIT = "BLOCKED_DAILY_TRADE_LIMIT"          # ledger capacity (max_slots) exhausted
REASON_SYMBOL_DAILY_TRADE_LIMIT = "BLOCKED_SYMBOL_DAILY_TRADE_LIMIT"  # this symbol already owns a slot
REASON_OPEN_POSITION_LIMIT = "BLOCKED_OPEN_POSITION_LIMIT"       # execution-time only, see module docstring
REASON_AGGREGATE_OPEN_RISK = "BLOCKED_AGGREGATE_OPEN_RISK"       # execution-time only, see module docstring

SLOT_STATE_CLAIMED = "CLAIMED"
SLOT_STATE_EXECUTED = "EXECUTED"
SLOT_STATE_EXPIRED = "EXPIRED"
SLOT_STATE_DECLINED = "DECLINED"
_TERMINAL_STATES = (SLOT_STATE_EXECUTED, SLOT_STATE_EXPIRED, SLOT_STATE_DECLINED)


class DailySlotLockTimeout(RuntimeError):
    """Raised when the cross-process claim lock cannot be acquired within the timeout --
    treated as a hard failure by callers (fail closed, never assume capacity is free)."""


class _ExclusiveFileLock:
    """Real cross-process mutual exclusion via atomic exclusive file creation
    (os.O_CREAT | os.O_EXCL is atomic at the OS/filesystem level on both Windows and
    POSIX) -- NOT an in-process threading.Lock, which would do nothing to stop two
    separate OS processes from both winning a claim."""

    def __init__(self, path: str, timeout: float = 5.0, poll_interval: float = 0.02):
        self.lock_path = path + ".lock"
        self.timeout = timeout
        self.poll_interval = poll_interval

    def __enter__(self) -> "_ExclusiveFileLock":
        deadline = time.monotonic() + self.timeout
        directory = os.path.dirname(self.lock_path) or "."
        os.makedirs(directory, exist_ok=True)
        while True:
            try:
                fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                return self
            except FileExistsError:
                if time.monotonic() > deadline:
                    raise DailySlotLockTimeout(f"DAILY_SLOT_LOCK_TIMEOUT: {self.lock_path}")
                time.sleep(self.poll_interval)

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            os.remove(self.lock_path)
        except FileNotFoundError:
            pass


@dataclass(frozen=True)
class ClaimResult:
    success: bool
    reason_code: Optional[str]
    slot: Optional[dict]


@dataclass(frozen=True)
class DailyTradeLedger:
    store: JsonKeyValueStore
    max_slots: int = DEFAULT_MAX_SLOTS
    max_slots_per_symbol: int = DEFAULT_MAX_SLOTS_PER_SYMBOL

    @classmethod
    def default(cls, path: str = DEFAULT_LEDGER_PATH, max_slots: int = DEFAULT_MAX_SLOTS,
               max_slots_per_symbol: int = DEFAULT_MAX_SLOTS_PER_SYMBOL) -> "DailyTradeLedger":
        return cls(JsonKeyValueStore(path), max_slots, max_slots_per_symbol)

    @staticmethod
    def _key(strategy_id: str, trading_date: date) -> str:
        return f"{strategy_id}:{trading_date.isoformat()}"

    def _load(self, strategy_id: str, strategy_version: str, release_id: str, trading_date: date) -> Dict:
        record = self.store.get(self._key(strategy_id, trading_date))
        if record is not None:
            return record
        return {
            "schema_version": SCHEMA_VERSION, "strategy_id": strategy_id,
            "strategy_version": strategy_version, "release_id": release_id,
            "trading_date": trading_date.isoformat(), "max_slots": self.max_slots, "slots": [],
        }

    def slots(self, strategy_id: str, trading_date: date) -> List[dict]:
        record = self.store.get(self._key(strategy_id, trading_date))
        return list(record["slots"]) if record else []

    def consumed_count(self, strategy_id: str, trading_date: date) -> int:
        return len(self.slots(strategy_id, trading_date))

    def symbol_slot(self, strategy_id: str, trading_date: date, symbol: str) -> Optional[dict]:
        return next((s for s in self.slots(strategy_id, trading_date) if s["symbol"] == symbol), None)

    def try_claim(
        self, strategy_id: str, strategy_version: str, release_id: str, trading_date: date,
        symbol: str, setup_id: str, proposal_id: str, ready_at: datetime,
        now: Optional[datetime] = None,
    ) -> ClaimResult:
        """Atomic (cross-process, via _ExclusiveFileLock): rereads the ledger under
        lock, checks per-symbol and per-day capacity, and only then appends a new slot.
        Re-claiming the EXACT SAME identity (symbol/setup_id/proposal_id) already on the
        ledger is idempotent success -- this is what makes crash recovery safe: a
        process that crashed after claiming but before persisting its proposal can
        simply re-claim the identical identity on restart."""
        now = now or datetime.now(timezone.utc)
        key = self._key(strategy_id, trading_date)
        with _ExclusiveFileLock(self.store.path):
            ledger = self._load(strategy_id, strategy_version, release_id, trading_date)
            slots = ledger["slots"]

            existing_identity = next(
                (s for s in slots if s["symbol"] == symbol and s["setup_id"] == setup_id
                 and s["proposal_id"] == proposal_id), None)
            if existing_identity is not None:
                existing_identity["updated_at"] = now.isoformat()
                self.store.put(key, ledger)
                return ClaimResult(True, None, existing_identity)

            existing_symbol = next((s for s in slots if s["symbol"] == symbol), None)
            if existing_symbol is not None:
                return ClaimResult(False, REASON_SYMBOL_DAILY_TRADE_LIMIT, existing_symbol)

            if len(slots) >= ledger.get("max_slots", self.max_slots):
                return ClaimResult(False, REASON_DAILY_TRADE_LIMIT, None)

            slot = {
                "slot_index": len(slots) + 1, "symbol": symbol, "setup_id": setup_id,
                "proposal_id": proposal_id, "ready_at": ready_at.isoformat(),
                "claimed_at": now.isoformat(), "state": SLOT_STATE_CLAIMED,
                "terminal_reason": None, "created_at": now.isoformat(), "updated_at": now.isoformat(),
            }
            slots.append(slot)
            ledger["slots"] = slots
            self.store.put(key, ledger)
            return ClaimResult(True, None, slot)

    def transition(self, strategy_id: str, trading_date: date, symbol: str, new_state: str,
                   terminal_reason: Optional[str] = None, now: Optional[datetime] = None) -> None:
        """CLAIMED -> EXECUTED/EXPIRED/DECLINED only, for the slot already owned by
        `symbol`. Never called by this package's own selection/pipeline code (spec
        section 22: only the existing, separate, explicit execution workflow may ever
        set EXECUTED) -- provided as the durable-contract primitive that workflow will
        call. Terminal states are never recycled back to available capacity."""
        if new_state not in _TERMINAL_STATES:
            raise ValueError(f"transition() only accepts terminal states, got {new_state!r}")
        now = now or datetime.now(timezone.utc)
        key = self._key(strategy_id, trading_date)
        with _ExclusiveFileLock(self.store.path):
            record = self.store.get(key)
            if record is None:
                raise ValueError(f"no ledger for {strategy_id}/{trading_date} to transition")
            slots = record["slots"]
            slot = next((s for s in slots if s["symbol"] == symbol), None)
            if slot is None or slot["state"] != SLOT_STATE_CLAIMED:
                raise ValueError(f"cannot transition {symbol}: slot is not CLAIMED "
                                 f"(state={slot['state'] if slot else 'ABSENT'!r})")
            slot["state"] = new_state
            slot["terminal_reason"] = terminal_reason
            slot["updated_at"] = now.isoformat()
            self.store.put(key, record)


@dataclass(frozen=True)
class DailyGovernorResult:
    portfolio_state: str  # PORTFOLIO_ELIGIBLE or PORTFOLIO_BLOCKED
    reason_code: Optional[str]


def evaluate_daily_governor(
    strategy_id: str, trading_date: date, daily_loss_guard: DailyLossGuard,
    strategy_daily_loss_limit_r: float,
) -> DailyGovernorResult:
    """Loss-based selection-time gates only (open-position capacity is checked
    separately, at execution time -- see module docstring and
    evaluate_execution_eligibility())."""
    if daily_loss_guard.is_blocked(trading_date):
        return DailyGovernorResult(PORTFOLIO_BLOCKED, REASON_PROJECT_DAILY_LOSS_GUARD)
    if daily_loss_guard.realized_r(trading_date) <= strategy_daily_loss_limit_r:
        return DailyGovernorResult(PORTFOLIO_BLOCKED, REASON_STRATEGY_DAILY_LOSS_LOCK)
    return DailyGovernorResult(PORTFOLIO_ELIGIBLE, None)


def strategy_open_position_count(open_position_guard: OpenPositionGuard, strategy_id: str) -> int:
    """execution.position_guard.OpenPositionGuard is a GLOBAL, cross-strategy guard
    (its own docstring: keyed by position_id only, counts ALL registered AG positions
    regardless of strategy_id) hardcoded to MAX_OPEN_STRATEGY_POSITIONS=1 -- that shared
    constant is never touched here. This pilot's own max_open_positions=2 policy is
    necessarily a DIFFERENT, strategy-scoped count: how many of the currently
    open/registered positions belong to THIS strategy_id specifically (positions are
    optionally tagged with strategy_id at register_open() time -- see that method's
    docstring). This does not weaken the global guard; it is an independent count over
    the same underlying store, used only for this pilot's own, additional gate."""
    return sum(1 for record in open_position_guard.store.all().values()
              if record.get("strategy_id") == strategy_id)


def strategy_open_risk_pct(open_position_guard: OpenPositionGuard, strategy_id: str, equity: float) -> float:
    """Conservative/fail-closed aggregate-risk accounting (spec section 17): sums each
    open position's ORIGINAL risk_amount at position-open time (never a breakeven-aware
    mark-to-market recalculation, which this repo has no existing trustworthy primitive
    for) as a percentage of current equity. This can only OVER-count real remaining risk
    once a stop has moved to breakeven, never under-count it -- the safe direction for a
    risk gate to be wrong in."""
    if equity <= 0:
        return float("inf")
    total_risk = sum(float(record.get("risk_amount") or 0.0)
                     for record in open_position_guard.store.all().values()
                     if record.get("strategy_id") == strategy_id)
    return (total_risk / equity) * 100.0


def evaluate_execution_eligibility(
    strategy_id: str, trading_date: date, symbol: str, setup_id: str, proposal_id: str,
    ledger: DailyTradeLedger, open_position_guard: OpenPositionGuard, daily_loss_guard: DailyLossGuard,
    strategy_daily_loss_limit_r: float, max_open_positions: int, max_aggregate_open_risk_pct: float,
    equity: float, candidate_risk_amount: float,
) -> DailyGovernorResult:
    """For the later, separate, explicit execution workflow (spec sections 17-24) --
    NOT called by this pilot's own selection pipeline. Re-validates slot ownership, open
    positions (this pilot's own max_open_positions=2 threshold, not the shared global
    guard's 1), aggregate open risk, and the daily loss lock at the moment execution is
    actually attempted, since all can change between selection time and execution time."""
    ownership = validate_slot_ownership(strategy_id, trading_date, symbol, setup_id, proposal_id, ledger)
    if not ownership.success:
        return DailyGovernorResult(PORTFOLIO_BLOCKED, ownership.reason_code)
    if strategy_open_position_count(open_position_guard, strategy_id) >= max_open_positions:
        return DailyGovernorResult(PORTFOLIO_BLOCKED, REASON_OPEN_POSITION_LIMIT)
    existing_risk_pct = strategy_open_risk_pct(open_position_guard, strategy_id, equity)
    candidate_risk_pct = (candidate_risk_amount / equity) * 100.0 if equity > 0 else float("inf")
    if existing_risk_pct + candidate_risk_pct > max_aggregate_open_risk_pct:
        return DailyGovernorResult(PORTFOLIO_BLOCKED, REASON_AGGREGATE_OPEN_RISK)
    if daily_loss_guard.is_blocked(trading_date):
        return DailyGovernorResult(PORTFOLIO_BLOCKED, REASON_PROJECT_DAILY_LOSS_GUARD)
    if daily_loss_guard.realized_r(trading_date) <= strategy_daily_loss_limit_r:
        return DailyGovernorResult(PORTFOLIO_BLOCKED, REASON_STRATEGY_DAILY_LOSS_LIMIT_EXECUTION)
    return DailyGovernorResult(PORTFOLIO_ELIGIBLE, None)


def validate_slot_ownership(
    strategy_id: str, trading_date: date, symbol: str, setup_id: str, proposal_id: str,
    ledger: DailyTradeLedger,
) -> ClaimResult:
    """The execution-gateway-facing check (spec section 21): before ANY execution
    pathway may act on a persisted proposal, it must call this and require success=True.
    A blocked/non-selected candidate's persisted (non-actionable) proposal record fails
    this check by construction -- its identity never matches an owned ledger slot."""
    slot = ledger.symbol_slot(strategy_id, trading_date, symbol)
    if slot is None:
        return ClaimResult(False, "PROPOSAL_NOT_DAILY_SLOT_OWNER", None)
    owns = slot.get("setup_id") == setup_id and slot.get("proposal_id") == proposal_id
    if not owns:
        return ClaimResult(False, "PROPOSAL_NOT_DAILY_SLOT_OWNER", slot)
    return ClaimResult(True, None, slot)
