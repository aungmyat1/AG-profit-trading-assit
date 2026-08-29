"""SMC_TRADE_PROPOSAL_V1 -- deterministic, evidence-gated trade proposals over
SMC_CONDITIONAL_ENTRY_V2's composer output. See gate.py's module docstring for the
DETECTION != PROPOSAL != EXECUTION boundary this module preserves.
"""
from .explain import explain
from .gate import generate_proposals
from .models import SMC_TRADE_PROPOSAL_V1, STATUS_ENTRY_CANDIDATE_READY, SMCTradeProposal

__all__ = ["generate_proposals", "explain", "SMCTradeProposal", "SMC_TRADE_PROPOSAL_V1", "STATUS_ENTRY_CANDIDATE_READY"]
