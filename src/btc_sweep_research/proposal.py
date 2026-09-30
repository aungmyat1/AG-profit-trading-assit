"""BTC research proposal contract (spec section 24) -- RESEARCH_ONLY, PROPOSAL_ONLY.

Deliberately its OWN dataclass, not execution.adapter.TradeProposal: TradeProposal is the
shared Forex+Crypto shape ExecutionCoordinator/select_adapter already route through
CryptoExecutionAdapter (execution/adapter.py), which is a real (if NOT_IMPLEMENTED)
execution-domain object with its own submit() contract. This BTCSweepResearchProposal is
explicitly OUTSIDE that execution domain -- see execution_domain/execution_authority below
-- and is never passed to execution.executor / mt5.management_gateway / execution.adapter
/ execution.coordinator anywhere in this package (see tests/
test_btc_proposal_execution_boundary.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

EXECUTION_DOMAIN_CRYPTO_RESEARCH = "CRYPTO_RESEARCH"
EXECUTION_AUTHORITY_DISABLED = "DISABLED"
AUTHORITY_RESEARCH_ONLY = "RESEARCH_ONLY"


@dataclass(frozen=True)
class BTCSweepResearchProposal:
    """One qualified (ENTRY_READY) BTC sweep-retest occurrence, fully described for
    research/observation purposes. Every field in spec section 24 is present."""

    strategy: str
    strategy_version: str
    authority: str  # always AUTHORITY_RESEARCH_ONLY

    exchange: str
    instrument: str
    direction: str  # "LONG" / "SHORT"

    reference_day: date
    reference_high: float
    reference_low: float

    sweep: dict  # {"level": float, "extreme": float, "time": datetime}
    confirmation: dict  # {"broken_swing_price": float, "mss_time": datetime}
    entry: float
    stop: float
    target: dict  # {"tp1": float, "tp2": float}
    RR: Optional[float]  # tp2_r_multiple

    estimated_fees: float
    funding_assumption: dict  # see btc_sweep_research.costs.CostEstimate, serialized

    data_timestamp: datetime  # when the underlying candle data was fetched/evaluated
    expiry: Optional[datetime]

    occurrence_id: str

    # Explicit execution-domain boundary (spec section 24) -- this proposal type can never
    # be mistaken for an executable one downstream.
    execution_domain: str = EXECUTION_DOMAIN_CRYPTO_RESEARCH
    execution_authority: str = EXECUTION_AUTHORITY_DISABLED

    volume: Optional[float] = None
    risk_amount: Optional[float] = None
    setup_id: Optional[str] = None
    evidence: dict = field(default_factory=dict)

    # Two-layer result model (remediation Gap 2): this proposal is only ever built once
    # strategy_qualified=True (see strategy_engine.sweep_retest.models.SetupState) -- the
    # occurrence existed and is recorded regardless of these two fields. They report
    # whether a shared tradability guard (daily_loss_guard/open_position_guard) would
    # additionally have allowed a simulated trade on it, WITHOUT ever erasing the
    # occurrence itself: tradability_allowed=False (guard-blocked) rows still get an
    # occurrence_id, still get recorded in the research ledger, and still count toward
    # opportunity-completeness metrics -- only simulated-trade eligibility differs.
    tradability_allowed: bool = True
    tradability_block_reason: Optional[str] = None
