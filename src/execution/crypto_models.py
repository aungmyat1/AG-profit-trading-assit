"""Crypto execution-layer command shape (Phase 2: offline architecture only -- see
docs/architecture and the task spec this module was built against). CryptoTradeCommand is
the Binance USDT-M perpetual futures analogue of execution.models.TradeCommand, but is
DELIBERATELY a fully separate dataclass with NO inheritance relationship to TradeCommand.

Why separate rather than a shared base/Union (read TradeCommand in execution/models.py
first, then this reasoning): TradeCommand's fields are MT5/FX-shaped at the type level --
`magic_number` is an MT5 order-tagging concept, `position_ticket` is an MT5 broker ticket
(int), `volume` means MT5 lots, `action` is OPEN/CLOSE against an MT5 position. Crypto has
none of those concepts and instead needs `quantity` (base-asset units, not lots),
`client_order_id` (Binance's own idempotency string, not an MT5 ticket), and
`account_environment`/`execution_domain` (Binance has no MT5-style symbol/broker session
model). The overlap is only "symbol + side + order_type" -- not enough to justify a shared
base without forcing every FX caller to carry crypto-shaped Optional fields it will never
use, or vice versa. A plain, separate dataclass is the minimal, correct answer; nothing in
this module imports or subclasses TradeCommand.

execute() in execution/executor.py already gates on `isinstance(command, TradeCommand)`
before reading any field (SUPPORTED_EXECUTION_DOMAIN = "MT5_FX") -- because
CryptoTradeCommand shares no inheritance with TradeCommand, that gate rejects it exactly
the same way it already rejects btc_sweep_research.proposal.BTCSweepResearchProposal (see
tests/test_crypto_command_execution_boundary.py, the crypto analogue of
tests/test_btc_proposal_execution_boundary.py).

No network call, no broker send, no credential access anywhere in this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from btc_sweep_research.proposal import (
    EXECUTION_AUTHORITY_DISABLED,
    EXECUTION_DOMAIN_CRYPTO_RESEARCH,
    BTCSweepResearchProposal,
)

# This command family's ONE supported execution domain in this phase. A class-level
# constant, not something a caller can redirect to a different domain: CryptoTradeCommand
# validates in __post_init__ (below) that the field actually equals this constant, so
# passing e.g. execution_domain="MT5_FX" to the constructor fails loudly rather than
# silently mislabeling a command.
EXECUTION_DOMAIN_BINANCE_USDTM = "BINANCE_USDTM"

ACCOUNT_ENVIRONMENT_DEMO = "DEMO"
ACCOUNT_ENVIRONMENT_REAL = "REAL"
_VALID_ACCOUNT_ENVIRONMENTS = (ACCOUNT_ENVIRONMENT_DEMO, ACCOUNT_ENVIRONMENT_REAL)

# Returned/raised when account_environment fails validation -- distinct from the
# dataclass's own TypeError-on-omission (see validate_account_environment()'s docstring
# for why both cases exist and are both tested).
BLOCKED_ACCOUNT_ENVIRONMENT_UNSPECIFIED = "BLOCKED_ACCOUNT_ENVIRONMENT_UNSPECIFIED"

_VALID_SIDES = ("BUY", "SELL")
_VALID_ORDER_TYPES = ("MARKET", "LIMIT")


class InvalidCryptoTradeCommand(ValueError):
    """Raised by CryptoTradeCommand.__post_init__ for a structurally invalid command
    (wrong execution_domain, unknown side/order_type, non-positive quantity). This is a
    programmer-error guard, not the account_environment gate -- that one is validated
    separately and does NOT raise from the constructor (see validate_account_environment
    below)."""


@dataclass(frozen=True)
class CryptoTradeCommand:
    """A caller-constructed request describing what a FUTURE, separately-authorized
    execution phase would submit to Binance USDT-M futures. Constructing one submits
    NOTHING -- there is no adapter in this repo that accepts this type (see
    execution/adapter.py::CryptoExecutionAdapter, which stays NOT_IMPLEMENTED, and
    execution/executor.py::execute(), which rejects it via the isinstance(TradeCommand)
    gate).

    account_environment has NO default value on purpose (see module docstring / spec):
    Python dataclasses make "= 'DEMO'" defaults easy to get wrong -- a caller who forgets
    to pass it should get an immediate TypeError from the constructor, not a silent
    DEMO/REAL mix-up. A caller building this from parsed external input (e.g. a future
    CLI flag) that supplies an EMPTY STRING will NOT get that TypeError (empty string is
    still a valid Python str) -- that case is caught separately by
    validate_account_environment() below, which callers (e.g. build_crypto_trade_command)
    MUST call before trusting the field.
    """

    command_id: str
    occurrence_id: str  # links back to the originating BTCSweepResearchProposal
    account_environment: str  # required, no default -- see docstring
    symbol: str
    side: str  # "BUY" / "SELL"
    order_type: str  # "MARKET" / "LIMIT"
    quantity: float
    client_order_id: str
    created_at: datetime
    price: Optional[float] = None  # required for LIMIT orders, unused for MARKET
    stop_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    risk_amount: Optional[float] = None
    comment: str = ""
    execution_domain: str = EXECUTION_DOMAIN_BINANCE_USDTM

    def __post_init__(self) -> None:
        if self.execution_domain != EXECUTION_DOMAIN_BINANCE_USDTM:
            raise InvalidCryptoTradeCommand(
                f"CryptoTradeCommand.execution_domain must be {EXECUTION_DOMAIN_BINANCE_USDTM!r}, "
                f"got {self.execution_domain!r}."
            )
        if self.side not in _VALID_SIDES:
            raise InvalidCryptoTradeCommand(f"side must be one of {_VALID_SIDES}, got {self.side!r}")
        if self.order_type not in _VALID_ORDER_TYPES:
            raise InvalidCryptoTradeCommand(f"order_type must be one of {_VALID_ORDER_TYPES}, got {self.order_type!r}")
        if self.order_type == "LIMIT" and self.price is None:
            raise InvalidCryptoTradeCommand("order_type=LIMIT requires a non-None price")
        if self.quantity is None or self.quantity <= 0:
            raise InvalidCryptoTradeCommand(f"quantity must be > 0, got {self.quantity!r}")


def validate_account_environment(account_environment: str) -> Optional[str]:
    """Returns None if account_environment is valid, else
    BLOCKED_ACCOUNT_ENVIRONMENT_UNSPECIFIED. Deliberately a plain function (not raised
    automatically from CryptoTradeCommand.__post_init__) so both failure shapes from the
    spec are independently testable: (1) omitting the constructor arg entirely -> Python's
    own TypeError, (2) passing an explicit invalid/empty string -> this function's typed
    rejection code, checked by every builder (see build_crypto_trade_command) before a
    command is ever constructed."""
    if account_environment not in _VALID_ACCOUNT_ENVIRONMENTS:
        return BLOCKED_ACCOUNT_ENVIRONMENT_UNSPECIFIED
    return None


# --- Proposal -> command boundary -------------------------------------------------------

BLOCKED_NOT_AUTHORIZED = "BLOCKED_CRYPTO_COMMAND_NOT_AUTHORIZED"
BLOCKED_PROPOSAL_NOT_RESEARCH_DOMAIN = "BLOCKED_PROPOSAL_NOT_RESEARCH_DOMAIN"
BLOCKED_INVALID_QUANTITY = "BLOCKED_INVALID_QUANTITY"

STATUS_BUILT = "BUILT"
STATUS_REJECTED = "REJECTED"


@dataclass(frozen=True)
class CryptoCommandBuildResult:
    """Outer, always-returned shape from build_crypto_trade_command() -- mirrors
    execution.executor's own "always return a typed result, never let a rejection show up
    as an incidental exception" convention (see executor.py::_reject / ExecutionReport)."""

    status: str  # STATUS_BUILT or STATUS_REJECTED
    reason_code: Optional[str] = None
    command: Optional[CryptoTradeCommand] = None


def build_crypto_trade_command(
    proposal: BTCSweepResearchProposal,
    *,
    account_environment: str,
    authorized: bool,
    command_id: str,
    client_order_id: str,
    quantity: float,
    order_type: str = "MARKET",
    price: Optional[float] = None,
    now: Optional[datetime] = None,
) -> CryptoCommandBuildResult:
    """Proposal -> command boundary function (spec item 2). `authorized` has NO default --
    omitting it is a TypeError, and passing it as anything other than an explicit,
    freshly-supplied True is a hard rejection. The point: a BTCSweepResearchProposal
    reaching ENTRY_READY/strategy_qualified=True (the proposal's own internal state) is
    NEVER by itself sufficient to build a command -- the caller must supply a fresh
    authorization signal from OUTSIDE this function's own proposal input on every call.
    This function does not (and structurally cannot) infer `authorized` from `proposal`.

    Returns a typed CryptoCommandBuildResult in every case -- never raises for an
    expected rejection (unauthorized, bad account_environment, bad proposal domain,
    non-positive quantity); only a genuinely malformed CryptoTradeCommand construction
    (see CryptoTradeCommand.__post_init__) would raise, which should not be reachable
    given the checks below.
    """
    if not authorized:
        return CryptoCommandBuildResult(STATUS_REJECTED, BLOCKED_NOT_AUTHORIZED)

    env_error = validate_account_environment(account_environment)
    if env_error is not None:
        return CryptoCommandBuildResult(STATUS_REJECTED, env_error)

    if (
        proposal.execution_domain != EXECUTION_DOMAIN_CRYPTO_RESEARCH
        or proposal.execution_authority != EXECUTION_AUTHORITY_DISABLED
    ):
        return CryptoCommandBuildResult(STATUS_REJECTED, BLOCKED_PROPOSAL_NOT_RESEARCH_DOMAIN)

    if quantity is None or quantity <= 0:
        return CryptoCommandBuildResult(STATUS_REJECTED, BLOCKED_INVALID_QUANTITY)

    side = "BUY" if proposal.direction == "LONG" else "SELL"
    tp1 = proposal.target.get("tp1") if isinstance(proposal.target, dict) else None

    command = CryptoTradeCommand(
        command_id=command_id,
        occurrence_id=proposal.occurrence_id,
        account_environment=account_environment,
        symbol=proposal.instrument,
        side=side,
        order_type=order_type,
        quantity=quantity,
        client_order_id=client_order_id,
        created_at=now or datetime.now(timezone.utc),
        price=price,
        stop_price=proposal.stop,
        take_profit_price=tp1,
        risk_amount=proposal.risk_amount,
    )
    return CryptoCommandBuildResult(STATUS_BUILT, None, command)
