"""ExecutionCoordinator: Strategy TradeProposal -> shared GLOBAL safety guards ->
execution.

    Strategy -> TradeProposal -> ExecutionCoordinator -> {OpenPositionGuard,
    DailyLossGuard} -> execution.executor.execute() (Forex) / CryptoExecutionAdapter
    (Crypto)

This module ORCHESTRATES existing execution capabilities; it does not reimplement any of
them. For Forex, execution.executor.execute() remains the sole authority for risk sizing,
broker normalization, stale-proposal checks, explicit confirmation, order_check/
order_send, journaling, duplicate protection, and MT5 reconciliation (see
execution/executor.py's own module docstring) -- this module only ever translates a
TradeProposal into the smallest TradeCommand executor.execute() already understands, then
calls it. For Crypto, this module goes no further than CryptoExecutionAdapter, which
performs no network/exchange call of any kind (see execution/adapter.py).

GLOBAL guards -- the actual point of this module: OpenPositionGuard (position_guard.py)
and DailyLossGuard (daily_loss_guard.py) were already asset-agnostic (OpenPositionGuard is
keyed by position_id only; DailyLossGuard is keyed by strategy_id+day), but before this
module only ST_LIQUIDITY_SWEEP_RETEST_V1's own evaluate_setup() pipeline ever checked
them, and only against ITS OWN strategy_id's daily-loss key -- a loss booked by a
different strategy_id (e.g. ST_ASIAN_SWEEP_5R_V1) never blocked it, and vice versa. This
module is what makes both guards truly CROSS-STRATEGY authoritative: every proposal
routed through ExecutionCoordinator.submit(), regardless of originating strategy_id or
asset, is checked against ONE shared OpenPositionGuard instance and ONE shared
DailyLossGuard instance scoped under GLOBAL_LEDGER_STRATEGY_ID (not any individual
strategy's own strategy_id) -- see .default(). ST_ASIAN_SWEEP_5R_V1's own signal path now
also reaches this same submit() -- via TradeProposal.from_trade_intent() (see
execution/adapter.py), the sibling of from_setup_state() -- so both strategies' realized
results land in the SAME shared ledger (AG_GLOBAL_EXECUTION_LIFECYCLE_V1).

FILL/CLOSE LIFECYCLE (AG_GLOBAL_EXECUTION_LIFECYCLE_V1): submit() itself only ever
registers a GLOBAL OPEN position once execution.executor.execute() reports a real broker
fill (see _submit_forex -> execution.lifecycle.register_confirmed_fill) -- a mere
submission, a rejection, or a confirmation-required response never does. Closing (partial
or full) is NOT observed synchronously by submit() -- MT5 fills/closes happen out of band
from the strategy loop that called submit() -- so reconcile() (execution/lifecycle.py)
must be run at restart, and periodically while the process stays up, to detect a broker-
confirmed FULL close and record its realized R exactly once. See execution/lifecycle.py's
own module docstring for the full contract and its documented gap (positions restored via
reconciliation alone, with no surviving OpenPositionGuard record, cannot recover their
original risk_amount/strategy_id and are intentionally left CLOSED_RISK_AMOUNT_MISSING
rather than guessed).

IDEMPOTENCY: delegates to execution.journal's existing command-claim mechanism
(journal.claim_command / journal.has_executed) rather than inventing a second persistence
shape -- setup_id becomes the Forex TradeCommand's command_id (see _forex_command()), the
SAME stable identity SweepRetestRuntime/state_store.py already key a setup on, so
executor.execute()'s own existing per-command_id journal (already the sole source of truth
executor checks for duplicate protection) is naturally keyed by setup_id too. submit()
additionally short-circuits BEFORE ever calling execute() again for a setup_id that has
already reached ORDER_EXECUTED, so a duplicate submission does not even re-enter the real
executor a second time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from execution import journal, lifecycle
from execution.adapter import AdapterSubmitResult, CryptoExecutionAdapter, TradeProposal
from execution.close_ledger import CloseLedger
from execution.daily_loss_guard import DailyLossGuard
from execution.executor import execute as executor_execute
from execution.lifecycle import _trading_day
from execution.models import ExecutionReport, ExecutionSource, TradeCommand
from execution.position_guard import OpenPositionGuard
from strategy_engine.sweep_retest.models import STATE_BLOCKED_DAILY_LOSS, STATE_BLOCKED_OPEN_POSITION
from strategy_engine.sweep_retest.profile import PROFILE_CRYPTO_PERP, PROFILE_FOREX

# Coordinator outcome strings. STATUS_BLOCKED_OPEN_POSITION/STATUS_BLOCKED_DAILY_LOSS reuse
# the LITERAL string values already defined in strategy_engine.sweep_retest.models (spec:
# "reuse those literal values rather than inventing new spellings for the same concept") --
# not new constants with a coincidentally-equal value.
STATUS_EXECUTION_DELEGATED = "EXECUTION_DELEGATED"
STATUS_CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
STATUS_BLOCKED_OPEN_POSITION = STATE_BLOCKED_OPEN_POSITION
STATUS_BLOCKED_DAILY_LOSS = STATE_BLOCKED_DAILY_LOSS
STATUS_BLOCKED_INVALID_METADATA = "BLOCKED_INVALID_METADATA"
STATUS_PROPOSAL_ONLY = "PROPOSAL_ONLY"
STATUS_DUPLICATE_REQUEST = "DUPLICATE_REQUEST"
STATUS_EXECUTION_REJECTED = "EXECUTION_REJECTED"

# One shared scope key so DailyLossGuard's realized-R ledger aggregates across EVERY
# strategy_id routed through this coordinator, not just one strategy's own trades (see
# module docstring). This is only the *key* the shared ledger is stored under -- the -2R
# threshold itself stays defined exactly once, as DAILY_LOSS_CIRCUIT_R in
# daily_loss_guard.py, never duplicated here.
GLOBAL_LEDGER_STRATEGY_ID = "AG_EXECUTION_COORDINATOR_GLOBAL"


@dataclass(frozen=True)
class CoordinatorResult:
    """Deterministic outer shape from ExecutionCoordinator.submit() -- always returned,
    never an exception for an expected block/rejection (same convention as
    execution.models.ExecutionReport / strategy_engine.sweep_retest.models.SetupState)."""

    status: str
    reason_code: str
    setup_id: str
    strategy_id: str
    profile_id: str
    execution_report: Optional[ExecutionReport] = None
    adapter_result: Optional[AdapterSubmitResult] = None


def _direction_to_side(direction: str) -> str:
    return "BUY" if direction == "LONG" else "SELL"


def _forex_command(proposal: TradeProposal) -> TradeCommand:
    """The smallest possible translation from an asset-independent TradeProposal to
    execution.executor's own TradeCommand contract -- executor's request shape is NOT
    restructured to fit TradeProposal (spec: "do not restructure the executor's own
    request contract").

    source=USER_EXPLICIT_ORDER, deliberately not ASSISTANT_PROPOSAL: ASSISTANT_PROPOSAL
    additionally requires a stored, non-stale TradeCandidate already registered in
    executor.ProposalStore -- built by the assistant's own proposal flow
    (trade_management.pretrade_engine-shaped), which a strategy-engine ENTRY_READY
    SetupState simply does not produce. Forcing one into existence here would itself be
    "reimplementing executor's request contract", exactly what this phase must not do.
    USER_EXPLICIT_ORDER requires no entry-confirmation/strategy-signal precondition of its
    own (see executor.py's module docstring) -- but that is orthogonal to user_confirmed,
    which executor.execute() ALWAYS requires separately and which submit() below always
    forwards unchanged from its own caller, never defaulting or inferring it.

    volume/sl/tp/entry are read directly off the proposal -- already computed upstream by
    evaluate_setup() -> execution.risk.size_position -- never recomputed here (spec).
    Because volume is supplied, executor.execute()'s own sizing-derivation branch never
    runs for a coordinated submission; only its geometry re-validation and broker send
    path do (unchanged, untouched).

    command_id = proposal.setup_id: the SAME stable identity SweepRetestRuntime/
    state_store.py already key a setup on -- see module docstring on IDEMPOTENCY.

    comment is left unset (empty) so executor.execute() falls back to its OWN
    _comment_tag(command.command_id) ("AGT:<command_id>") when it calls order_open --
    this is deliberate, not an oversight: that tag is also the exact string
    executor.py's own crash/restart broker reconciliation (_reconcile_via_broker) and
    this phase's execution/lifecycle.py restart reconciliation both scan a broker
    position's/deal's comment for. A prior version of this function set a
    strategy_id-only comment here, which silently defeated both of those (a coordinator-
    routed order's broker comment would then never contain its own command_id) -- fixed
    as part of AG_GLOBAL_EXECUTION_LIFECYCLE_V1 since restart reconciliation depends on
    reusing that existing tag convention rather than inventing a second one.
    """
    return TradeCommand(
        command_id=proposal.setup_id,
        action="OPEN",
        symbol=proposal.symbol,
        source=ExecutionSource.USER_EXPLICIT_ORDER,
        side=_direction_to_side(proposal.direction),
        order_type="MARKET",
        volume=proposal.volume,
        entry=proposal.entry,
        sl=proposal.stop_loss,
        tp=proposal.tp1,
        risk_percent=None,
    )


@dataclass(frozen=True)
class ExecutionCoordinator:
    """One coordinator instance = one shared pair of GLOBAL guards. Use .default() for the
    real, on-disk shared guards; tests may inject tmp_path-backed guards directly for
    isolation between test cases, same convention as OpenPositionGuard/DailyLossGuard's
    own tests (see tests/test_liquidity_sweep_retest_strategy.py)."""

    open_position_guard: OpenPositionGuard
    daily_loss_guard: DailyLossGuard
    # Optional/default-factory (AG_GLOBAL_EXECUTION_LIFECYCLE_V1): existing callers/tests
    # that construct ExecutionCoordinator(open_position_guard=..., daily_loss_guard=...)
    # positionally-by-keyword without a close_ledger keep working unchanged. The default
    # factory only ever points at the on-disk path -- it never touches disk unless a
    # lifecycle function actually calls mark_recorded()/is_recorded() on it.
    close_ledger: CloseLedger = field(default_factory=CloseLedger.default)

    @classmethod
    def default(cls) -> "ExecutionCoordinator":
        return cls(
            open_position_guard=OpenPositionGuard.default(),
            daily_loss_guard=DailyLossGuard.default(GLOBAL_LEDGER_STRATEGY_ID),
            close_ledger=CloseLedger.default(),
        )

    def submit(self, proposal: TradeProposal, *, user_confirmed: bool,
               now: Optional[datetime] = None) -> CoordinatorResult:
        base = dict(setup_id=proposal.setup_id, strategy_id=proposal.strategy_id,
                    profile_id=proposal.profile_id)

        # Coordinator-level idempotency short-circuit (see module docstring): a Forex
        # setup_id that already reached ORDER_EXECUTED must never re-enter execute() a
        # second time, not merely be re-rejected once it gets there.
        if proposal.profile_id == PROFILE_FOREX and journal.has_executed(proposal.setup_id):
            return CoordinatorResult(status=STATUS_DUPLICATE_REQUEST,
                                      reason_code="DUPLICATE_COMMAND_BLOCKED", **base)

        # GLOBAL, cross-strategy guards -- checked for EVERY profile, not just the
        # strategy that happens to own this setup_id. See module docstring.
        trading_day = _trading_day(now)
        if self.daily_loss_guard.is_blocked(trading_day):
            return CoordinatorResult(status=STATUS_BLOCKED_DAILY_LOSS,
                                      reason_code=STATE_BLOCKED_DAILY_LOSS, **base)
        if self.open_position_guard.is_blocked():
            return CoordinatorResult(status=STATUS_BLOCKED_OPEN_POSITION,
                                      reason_code=STATE_BLOCKED_OPEN_POSITION, **base)

        if proposal.profile_id == PROFILE_FOREX:
            return self._submit_forex(proposal, user_confirmed, base)
        if proposal.profile_id == PROFILE_CRYPTO_PERP:
            return self._submit_crypto(proposal, user_confirmed, base)
        raise ValueError(f"no execution route for profile {proposal.profile_id!r}")

    def _submit_forex(self, proposal: TradeProposal, user_confirmed: bool, base: dict) -> CoordinatorResult:
        command = _forex_command(proposal)
        report: ExecutionReport = executor_execute(command, user_confirmed=user_confirmed)

        if report.status == "EXECUTED":
            status = STATUS_EXECUTION_DELEGATED
            # BROKER_FILL_CONFIRMED -> register_open (see execution/lifecycle.py). Never
            # fires on CONFIRMATION_REQUIRED/DUPLICATE/REJECTED -- "SUBMITTED does not
            # automatically equal OPEN" (spec).
            lifecycle.register_confirmed_fill(self.open_position_guard, proposal, report)
        elif report.gate_reason_code == "EXECUTION_NOT_AUTHORIZED":
            status = STATUS_CONFIRMATION_REQUIRED
        elif report.gate_reason_code == "DUPLICATE_COMMAND_BLOCKED":
            status = STATUS_DUPLICATE_REQUEST
        else:
            status = STATUS_EXECUTION_REJECTED

        return CoordinatorResult(status=status, reason_code=report.gate_reason_code or report.status,
                                  execution_report=report, **base)

    def _submit_crypto(self, proposal: TradeProposal, user_confirmed: bool, base: dict) -> CoordinatorResult:
        # No exchange metadata retrieval/live path exists (spec: "do NOT implement
        # exchange metadata retrieval"). CryptoExecutionAdapter.submit() never reaches a
        # network/exchange call -- see its own docstring -- so there is nothing here to
        # gate with require_exchange_verified_metadata() yet; that guard exists for
        # whenever a real crypto execution path is actually built.
        adapter = CryptoExecutionAdapter()
        result: AdapterSubmitResult = adapter.submit(proposal, user_confirmed)

        # Crypto stays PROPOSAL_ONLY regardless of the adapter's own internal
        # reason_code -- keeps the coordinator's result-type set small and consistent
        # rather than leaking the adapter's own vocabulary (spec: "pick whichever keeps
        # the result-type set smallest and most consistent").
        return CoordinatorResult(status=STATUS_PROPOSAL_ONLY, reason_code=result.reason_code,
                                  adapter_result=result, **base)

    def reconcile(self, *, positions_lookup=None, deals_lookup=None,
                  now: Optional[datetime] = None) -> List[dict]:
        """Restart-safe (and safe to call periodically) reconciliation entrypoint -- see
        execution/lifecycle.py::reconcile_open_positions for the full contract. Defaults
        to the real mt5.account.positions / mt5.deals.deals_for_position broker reads;
        tests inject fakes, same idiom execution/executor.py itself uses."""
        if positions_lookup is None:
            from mt5.account import positions as positions_lookup  # local import: keep MT5 optional for pure-guard use
        if deals_lookup is None:
            from mt5.deals import deals_for_position as deals_lookup
        return lifecycle.reconcile_open_positions(
            self.open_position_guard, self.daily_loss_guard, self.close_ledger,
            positions_lookup=positions_lookup, deals_lookup=deals_lookup, now=now,
        )
