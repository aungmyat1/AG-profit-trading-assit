"""ST_LARGE_SMC_V1 research-only decision engine (RESEARCH_ONLY_FUNNEL_V1).

Advisory/research only -- no proposal, demo, live, execution, or risk-sizing authority.
See strategies/ST_LARGE_SMC_V1.yaml and docs/specs/LARGE_SMC_V1_SPEC.md for the signed
contract this package implements.
"""
from __future__ import annotations

from .decision import (
    ENGINE_VERSION,
    STRATEGY_ID,
    LargeSMCDecisionState,
    LargeSMCResearchDecision,
)
from .engine import STRATEGY_VERSION, FROZEN_INSTRUMENT_UNIVERSE, LargeSMCResearchEngine
from .pending_entry import PendingEntryOutcome, simulate_pending_entry
from .target_model import TargetSelection, select_target

__all__ = [
    "STRATEGY_ID",
    "STRATEGY_VERSION",
    "ENGINE_VERSION",
    "FROZEN_INSTRUMENT_UNIVERSE",
    "LargeSMCDecisionState",
    "LargeSMCResearchDecision",
    "LargeSMCResearchEngine",
    "PendingEntryOutcome",
    "simulate_pending_entry",
    "TargetSelection",
    "select_target",
]
