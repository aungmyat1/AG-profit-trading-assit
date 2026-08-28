"""Public technique contract (spec 'Trade Assistant simplification', section 12):
lets a caller ask for "analyze EURUSD using SMC" separately from "analyze EURUSD using
DayTrading" through one explicit `technique` identifier, without merging the two
techniques' result shapes or duplicating either pipeline.

SMC routes to the existing five_skill_runtime.analyze_market() (FiveSkillAnalysisResult,
unchanged). DAYTRADING routes to daytrading.evaluate_daytrading() (DayTradingResult).
Deliberately the smallest possible dispatcher, not a fourth analysis engine -- see
daytrading/__init__.py's own docstring for why the two techniques stay siblings.
"""
from __future__ import annotations

from typing import Optional, Union

from daytrading import TECHNIQUE_DAYTRADING, TECHNIQUE_SMC, TECHNIQUES, DayTradingResult, evaluate_daytrading
from entry_confirmation import CandidateDirection

from .analysis_models import AssistantAnalysisRequest, FiveSkillAnalysisResult
from .five_skill_runtime import analyze_market

__all__ = ["analyze_by_technique", "TECHNIQUE_SMC", "TECHNIQUE_DAYTRADING", "TECHNIQUES"]


def _journal_decision(technique: str, symbol: str, result) -> None:
    """Best-effort journaling (spec sections 26-27): every analyze_by_technique() call
    is recorded, including WAIT/NO_TRADE/UNRESOLVED results, not only trade-ready ones.
    Journal I/O must never block or fail an analysis call -- same fail-open discipline
    as daytrading.pipeline's own optional-evidence try/except blocks."""
    try:
        from . import canonical_state, idea_journal

        if technique == TECHNIQUE_DAYTRADING:
            evaluation_time = getattr(result.narrative_bias, "evaluation_time", None)
            state = canonical_state.daytrading_canonical_state(result)
            reason = "; ".join(result.reasons) if result.reasons else None
        else:
            evaluation_time = getattr(result, "timestamp_utc", None)
            state = canonical_state.smc_canonical_state(result)
            reason = None
        idea_journal.record_decision(technique, symbol, evaluation_time, result, state, reason)
    except Exception:
        pass


def analyze_by_technique(
    technique: str,
    symbol: str,
    smc_request: Optional[AssistantAnalysisRequest] = None,
    candidate_direction: CandidateDirection = CandidateDirection.NONE,
    **daytrading_kwargs,
) -> Union[FiveSkillAnalysisResult, DayTradingResult]:
    if technique == TECHNIQUE_SMC:
        request = smc_request or AssistantAnalysisRequest(symbol=symbol)
        result = analyze_market(request)
        _journal_decision(TECHNIQUE_SMC, symbol, result)
        return result
    if technique == TECHNIQUE_DAYTRADING:
        result = evaluate_daytrading(symbol, candidate_direction=candidate_direction, **daytrading_kwargs)
        _journal_decision(TECHNIQUE_DAYTRADING, symbol, result)
        return result
    raise ValueError(f"Unknown technique {technique!r}; expected one of {TECHNIQUES}")
