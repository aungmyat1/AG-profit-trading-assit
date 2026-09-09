"""AG_STRATEGY_DIRECTION_CONTRACT_V1 canonical directional model.

Invariant 2: exactly three states. Invariant 3: MarketBiasResult is the canonical
interface between intelligence and strategy. Invariant 11/12: bias is never an entry
signal and cannot submit an order -- this dataclass structurally cannot carry
entry_price/stop_loss/take_profit/lot_size/order_type; there is no field for any of
them, by design (see test_market_intelligence.py::
test_market_bias_result_has_no_execution_fields, which asserts this via introspection so
a future accidental addition fails the test, not just this docstring).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Tuple

Bias = Literal["BULLISH", "BEARISH", "NEUTRAL"]

MODEL_VERSION = "AG_MARKET_BIAS_RESOLVER_V1"


class InvalidBiasStateError(ValueError):
    """Fail-closed: raised rather than silently accepting/normalizing an unknown
    directional label (invariant 31: no silent UPTREND/BUY/LONG/POSITIVE mapping)."""


_ALLOWED_BIAS_STATES = ("BULLISH", "BEARISH", "NEUTRAL")


@dataclass(frozen=True)
class MarketBiasResult:
    """The ONE canonical directional interface (invariant 3). Immutable once produced
    for a decision cycle (invariant/P6) -- a frozen dataclass enforces this at the
    language level; a changed market context must produce a NEW MarketBiasResult with
    a new decision_time/input_fingerprint, never a mutation of this one."""

    bias: Bias
    confidence: str

    decision_cycle_id: str  # e.g. "EURUSD:2026-09-10:ASIAN_LONDON" -- P7
    symbol: str
    decision_time: datetime

    htf_structure: str
    mtf_alignment: str
    liquidity_context: str
    session_context: str

    reason_codes: Tuple[str, ...]

    model_version: str
    input_fingerprint: str

    def __post_init__(self) -> None:
        if self.bias not in _ALLOWED_BIAS_STATES:
            raise InvalidBiasStateError(
                f"{self.bias!r} is not one of {_ALLOWED_BIAS_STATES} -- MarketBiasResult "
                "never silently normalizes an unrecognized directional label."
            )
        if self.decision_time.tzinfo is None:
            raise ValueError("decision_time must be timezone-aware (P33 no-lookahead discipline)")


def compute_input_fingerprint(*evidence_fields: object) -> str:
    """Deterministic sha256 over the exact evidence fields a resolver call consumed --
    same inputs must always produce the same fingerprint (P54: input fingerprint
    stability), and a changed input must always change it."""
    blob = "|".join(repr(f) for f in evidence_fields).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def make_decision_cycle_id(symbol: str, decision_date, session_pair: str) -> str:
    """Reuses this repo's own existing identity convention
    (STRATEGY_ID:SYMBOL:CYCLE:TRADING_DATE-shaped composite keys already used throughout
    artifacts/outcome_resolution/ and journal/) rather than inventing a second identity
    system (P7: "do not invent a second identity system")."""
    return f"{symbol}:{decision_date.isoformat()}:{session_pair}"
