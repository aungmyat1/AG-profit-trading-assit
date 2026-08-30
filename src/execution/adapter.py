"""Execution adapter boundary: Strategy TradeProposal -> ExecutionCoordinator ->
{MT5ExecutionAdapter, CryptoExecutionAdapter}.

Interface only in this change -- no Binance/Bybit/MEXC integration, and no live crypto
order path (spec: crypto "stays proposal-only", same posture as the Forex side already
has). Forex continues to use the existing execution/executor.py + mt5/management_gateway.py
path UNCHANGED; this module does not replace or wrap it, it only defines the pluggable
shape a future concrete crypto adapter (and, if ever wanted, a symmetric Forex adapter)
would implement, so ExecutionCoordinator can select one by MarketProfile without an
if/else baked into strategy code.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from mt5.symbol_resolver import METADATA_SOURCE_EXCHANGE_VERIFIED, SymbolMeta
from strategy_engine.sweep_retest.models import STATE_ENTRY_READY, SetupState
from strategy_engine.sweep_retest.profile import PROFILE_CRYPTO_PERP, PROFILE_FOREX


@dataclass(frozen=True)
class TradeProposal:
    """Asset-independent proposal handed from the strategy engine to an ExecutionAdapter.
    Only ever constructed from a SetupState in STATE_ENTRY_READY."""

    setup_id: str
    strategy_id: str
    symbol: str
    profile_id: str
    direction: str
    entry: float
    stop_loss: float
    tp1: Optional[float]
    tp2: Optional[float]
    volume: float
    risk_amount: float

    @classmethod
    def from_setup_state(cls, state: SetupState) -> "TradeProposal":
        if state.state != STATE_ENTRY_READY:
            raise ValueError(f"TradeProposal requires {STATE_ENTRY_READY}, got {state.state!r}")
        return cls(
            setup_id=state.setup_id, strategy_id=state.strategy_id, symbol=state.symbol,
            profile_id=state.profile_id, direction=state.direction, entry=state.entry,
            stop_loss=state.stop_loss, tp1=state.tp1, tp2=state.tp2,
            volume=state.volume, risk_amount=state.risk_amount,
        )


class SyntheticMetadataError(RuntimeError):
    """Raised when code attempts to use RESEARCH-ONLY synthetic symbol metadata (see
    strategy_engine.sweep_retest.crypto_symbols.crypto_symbol_meta()) as the basis for a
    real order. There is no live crypto execution path in this repo -- this guard exists
    so that if one is ever added, it fails closed BY CONSTRUCTION the moment it is wired
    to call require_exchange_verified_metadata() first (the mandatory pattern every other
    real-money code path in this repo follows, e.g. executor.py's stale-proposal/broker-
    reconciliation checks), rather than merely by a docstring warning."""


def require_exchange_verified_metadata(symbol_meta: SymbolMeta) -> None:
    """Fail closed: raises SyntheticMetadataError unless symbol_meta.metadata_source ==
    EXCHANGE_VERIFIED. Any future real order-sending code path (Forex or Crypto) MUST call
    this on its SymbolMeta before constructing a broker/exchange request -- it is the one
    place "was this metadata actually fetched from a live venue" is decided."""
    if symbol_meta.metadata_source != METADATA_SOURCE_EXCHANGE_VERIFIED:
        raise SyntheticMetadataError(
            f"{symbol_meta.symbol!r} metadata_source={symbol_meta.metadata_source!r} is not "
            f"{METADATA_SOURCE_EXCHANGE_VERIFIED!r} -- refusing to use RESEARCH-ONLY synthetic "
            "metadata as the basis for a real order."
        )


@dataclass(frozen=True)
class AdapterSubmitResult:
    status: str  # "NOT_IMPLEMENTED" for both adapters in this change (see each class)
    reason_code: str


class ExecutionAdapter(ABC):
    """One method a concrete adapter implements: turn a proposal into a broker/exchange
    order request. Neither concrete class below actually sends an order in this change."""

    @abstractmethod
    def submit(self, proposal: TradeProposal, user_confirmed: bool) -> AdapterSubmitResult:
        ...


class MT5ExecutionAdapter(ExecutionAdapter):
    """Wiring placeholder only -- the REAL, existing, demo/confirmation-gated Forex
    execution path is execution/executor.py + mt5/management_gateway.py, untouched by
    this change. This class exists purely so ExecutionCoordinator has a symmetric
    adapter to select for Forex proposals; callers should keep using execution.executor
    .execute() directly rather than this class's submit()."""

    def submit(self, proposal: TradeProposal, user_confirmed: bool) -> AdapterSubmitResult:
        raise NotImplementedError(
            "MT5ExecutionAdapter.submit is a wiring placeholder -- use execution.executor.execute() "
            "directly for the real, existing, demo/confirmation-gated MT5 path."
        )


class CryptoExecutionAdapter(ExecutionAdapter):
    """No exchange integration in this task (spec). submit() always returns
    NOT_IMPLEMENTED -- proposal-only posture, matching the Forex side's own execution
    safety contract (demo/explicit-confirmation authority, no live order path).

    No network/exchange call is reachable from this method at all -- it does not import
    an HTTP/websocket/exchange SDK, take credentials, or call out anywhere; it is a pure
    function of its arguments. A future concrete live-crypto submit() would additionally
    need to call require_exchange_verified_metadata() on its SymbolMeta before ever
    building a real order -- see that function's docstring."""

    def submit(self, proposal: TradeProposal, user_confirmed: bool) -> AdapterSubmitResult:
        return AdapterSubmitResult(status="NOT_IMPLEMENTED", reason_code="CRYPTO_EXECUTION_NOT_IMPLEMENTED")


_ADAPTERS = {PROFILE_FOREX: MT5ExecutionAdapter, PROFILE_CRYPTO_PERP: CryptoExecutionAdapter}


def select_adapter(profile_id: str) -> ExecutionAdapter:
    adapter_cls = _ADAPTERS.get(profile_id)
    if adapter_cls is None:
        raise ValueError(f"no ExecutionAdapter registered for profile {profile_id!r}")
    return adapter_cls()
