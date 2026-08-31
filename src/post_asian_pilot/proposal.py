"""Builds the pilot's complete Entry Proposal from a READY PostAsianDecision.

Reuses the existing, already-tested risk-sizing pipeline verbatim:
    TradeSignal -> execution.intent_builder.build_intent() -> TradeIntent
                -> execution.adapter.TradeProposal.from_trade_intent()
TP1 comes from execution.validator.leg1_take_profit() (already reads the strategy's own
signed OPPOSITE_SESSION_BOUNDARY leg off TradeSignal.box_high/box_low -- untouched).
TP2 (the 25%-runner-to-5R leg) has no TradeIntent/TradeProposal equivalent yet
(execution.adapter.TradeProposal.from_trade_intent's own docstring: "no TradeIntent
equivalent... never invented") -- computed here directly from the strategy's own signed
total_target_r (5.0, strategies/ST_ASIAN_SWEEP_5R_V1.yaml) and attached via
dataclasses.replace, without modifying execution/adapter.py or execution/intent_builder.py.

Never calls execution.executor / execution.mt5_gateway / order_check / order_send.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from execution.adapter import TradeProposal
from execution.intent_builder import build_intent
from execution.models import STATUS_READY as INTENT_STATUS_READY
from execution.validator import leg1_take_profit
from mt5.symbol_resolver import SymbolMeta
from strategy_engine.models import StrategyConfig, TradeSignal

from .decision import PostAsianDecision

EXECUTION_STATUS_CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
PROPOSAL_EXPIRY_MINUTES = 15  # one M15 bar -- a stale sweep signal is not re-validated, see report.py


@dataclass(frozen=True)
class PostAsianEntryProposal:
    proposal_id: str
    trade_proposal: TradeProposal   # entry/stop_loss/tp1/tp2/volume/risk_amount/risk_percent
    setup_id: str

    reference_session: str
    swept_level: Optional[float]

    session_snapshot_id: str
    evidence_snapshot_id: str
    reason_codes: Tuple[str, ...]

    created_at: datetime
    valid_from: datetime
    expires_at: datetime

    decision_status: str = "READY"
    execution_status: str = EXECUTION_STATUS_CONFIRMATION_REQUIRED
    execution_authorized: bool = False
    user_confirmation_required: bool = True


@dataclass(frozen=True)
class ProposalResult:
    status: str  # "READY" or a rejection reason_code (e.g. BLOCKED reason)
    proposal: Optional[PostAsianEntryProposal]
    reason_code: str


def build_entry_proposal(
    decision: PostAsianDecision, strategy: StrategyConfig, equity: float,
    symbol_meta: SymbolMeta, risk_per_trade_pct: float,
    session_snapshot_id: str, swept_level: Optional[float] = None,
    now: Optional[datetime] = None,
) -> ProposalResult:
    if decision.status != "READY" or decision.signal is None:
        return ProposalResult(status="NOT_READY", proposal=None, reason_code="DECISION_NOT_READY")

    signal: TradeSignal = decision.signal
    intent_result = build_intent(signal, strategy, equity, symbol_meta, risk_per_trade_pct)
    if intent_result.status != INTENT_STATUS_READY or intent_result.intent is None:
        return ProposalResult(status="BLOCKED", proposal=None, reason_code=intent_result.reason_code)

    trade_proposal = TradeProposal.from_trade_intent(intent_result.intent)

    total_target_r = strategy.total_target_r
    risk_distance = abs(intent_result.intent.entry - intent_result.intent.stop_loss)
    if signal.direction == "LONG":
        tp2 = intent_result.intent.entry + total_target_r * risk_distance
    else:
        tp2 = intent_result.intent.entry - total_target_r * risk_distance
    trade_proposal = dataclasses.replace(trade_proposal, tp2=tp2)

    now = now or datetime.now(timezone.utc)
    expires_at = decision.valid_until or (now + timedelta(minutes=PROPOSAL_EXPIRY_MINUTES))

    proposal = PostAsianEntryProposal(
        proposal_id=f"PROPOSAL-{trade_proposal.setup_id}",
        trade_proposal=trade_proposal,
        setup_id=trade_proposal.setup_id,
        reference_session=decision.reference_session,
        swept_level=swept_level,
        session_snapshot_id=session_snapshot_id,
        evidence_snapshot_id=decision.decision_id,
        reason_codes=decision.reason_codes,
        created_at=now, valid_from=now, expires_at=expires_at,
    )
    return ProposalResult(status="READY", proposal=proposal, reason_code=intent_result.reason_code)
