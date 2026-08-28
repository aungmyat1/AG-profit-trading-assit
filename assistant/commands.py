"""Central Trade Assistant command surface (Execution authority restructure, 2026-08-28).

This is the ONLY module in assistant/ allowed to import execution.executor. Every other
assistant/ entrypoint (analyze_market, runtime.evaluate) stays execution-free per
assistant/__init__.py's own authority statement.

Three things this module can do:
  build_proposal(request)                    -- analysis only, never touches execution.
  resolve_active_proposal(proposal_id=None)   -- deterministic "which proposal does
                                                  'execute it' mean" resolution
                                                  (AG_ASSISTANT_PROPOSAL_EXECUTION_V1,
                                                  2026-08-28). Never itself authorizes
                                                  execution.
  execute_command(command, user_confirmed)    -- the single funnel into
                                                  execution.executor.execute(). Requires
                                                  the caller to have just received an
                                                  explicit user instruction this turn.

Producing a TradeProposal is never itself execution authorization -- see
assistant/analysis_models.py::TradeProposal's own docstring.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from execution.executor import ProposalStore, execute as execution_execute
from execution.models import ExecutionReport, TradeCommand

from .analysis_models import (
    AssistantAnalysisRequest, FiveSkillAnalysisResult, PROPOSAL_READY, TradeProposal,
)
from .five_skill_runtime import analyze_market

_PROPOSAL_TTL_MINUTES = 15

_store = ProposalStore()

NO_ACTIVE_PROPOSAL = "NO_ACTIVE_PROPOSAL"
AMBIGUOUS_PROPOSAL = "AMBIGUOUS_PROPOSAL"
PROPOSAL_NOT_FOUND = "PROPOSAL_NOT_FOUND"


def build_proposal(request: AssistantAnalysisRequest, analysis_summary: str = "",
                    evidence: tuple = ()) -> TradeProposal:
    """Runs the existing five-skill analysis and wraps its candidate into a
    TradeProposal. Requires request.candidate to already be populated (direction/
    entry/SL/TP/etc, per assistant.analysis_models.TradeCandidate) -- this function
    does not invent one. No execution call anywhere in this function."""
    if request.candidate is None:
        raise ValueError("build_proposal requires request.candidate to be set.")

    result: FiveSkillAnalysisResult = analyze_market(request)

    now = datetime.now(timezone.utc)
    proposal = TradeProposal(
        proposal_id=str(uuid.uuid4()),
        created_at=now,
        expires_at=now + timedelta(minutes=_PROPOSAL_TTL_MINUTES),
        symbol=request.symbol,
        timeframe=request.timeframe,
        candidate=request.candidate,
        analysis_summary=analysis_summary,
        evidence=evidence,
    )
    _store.put(proposal)
    return proposal


def get_proposal(proposal_id: str):
    return _store.get(proposal_id)


def list_eligible_proposals(symbol: Optional[str] = None) -> Tuple[TradeProposal, ...]:
    """Proposals still open for a decision -- status READY_FOR_USER_DECISION and not
    past expires_at. Optionally narrowed to one symbol (a bare "execute it" said right
    after analyzing EURUSD should not resolve against an unrelated GBPUSD proposal from
    earlier in the conversation)."""
    now = datetime.now(timezone.utc)
    eligible = [
        p for p in _store.all()
        if p.status == PROPOSAL_READY and p.expires_at > now
        and (symbol is None or p.symbol == symbol)
    ]
    return tuple(eligible)


def resolve_active_proposal(proposal_id: Optional[str] = None, symbol: Optional[str] = None):
    """(proposal_or_None, reason_code_or_None) -- deterministic "execute it" resolution
    (section 5): an explicit proposal_id always resolves directly (PROPOSAL_NOT_FOUND if
    unknown); with no proposal_id, 0 eligible proposals -> NO_ACTIVE_PROPOSAL, exactly 1
    -> resolved, more than 1 -> AMBIGUOUS_PROPOSAL (never guessed)."""
    if proposal_id is not None:
        proposal = _store.get(proposal_id)
        if proposal is None:
            return None, PROPOSAL_NOT_FOUND
        return proposal, None

    eligible = list_eligible_proposals(symbol=symbol)
    if len(eligible) == 0:
        return None, NO_ACTIVE_PROPOSAL
    if len(eligible) > 1:
        return None, AMBIGUOUS_PROPOSAL
    return eligible[0], None


def execute_command(command: TradeCommand, user_confirmed: bool) -> ExecutionReport:
    """The single funnel into execution.executor.execute(). user_confirmed must be True
    only when the user's own message this turn was an explicit execution instruction
    (e.g. "execute it", "sell EURUSD 0.31 lots ...", "close this position") -- analysis
    or a proposal being generated is never sufficient on its own."""
    return execution_execute(command, user_confirmed=user_confirmed, proposal_store=_store)
