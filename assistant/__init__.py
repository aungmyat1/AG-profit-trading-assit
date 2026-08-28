"""Trading Assistant: the agent-facing orchestration/reporting layer.

analyze_market/runtime.evaluate carry no execution authority -- never call
execution.executor/mt5_gateway to place or modify an order. See PROJECT_STATUS.md
'Authority order'. The single, deliberate exception is assistant/commands.py
(execute_command), the central Trade Assistant execution funnel added by the 2026-08-28
Execution authority restructure -- see TRADE_ASSISTANT_ARCHITECTURE.md. It requires an
explicit, non-defaulted user_confirmed=True on every call; nothing here executes as a
side effect of analysis or of building a TradeProposal.

Three independent public runtime entry points (see TRADE_ASSISTANT_ARCHITECTURE.md's
"Strategy vs. capability boundary"):

    analyze_market(request)  -- FIVE_SKILL_ASSISTANT_RUNTIME_V1 (five_skill_runtime.py).
        Generic market analysis: Market Context -> requested core skills -> structured
        facts -> report. Never requires a registered strategy. No execution authority.

    runtime.evaluate(strategy_id, symbol, cycle, mode)  -- ASSISTANT_RUNTIME_V1
        (runtime.py). Dispatches to a registered strategy via strategy_manager/. Kept
        as a separate function (not merged into analyze_market) because it answers a
        different question and has a different authority chain -- see
        FIVE_SKILL_ASSISTANT_RUNTIME_V1_SPEC.md's "Strategy independence" section. No
        execution authority.

    commands.build_proposal(request) / commands.execute_command(command, user_confirmed)
        (commands.py). The central Trade Assistant execution funnel -- see that
        module's own docstring for the two-source (ASSISTANT_PROPOSAL /
        USER_EXPLICIT_ORDER) authorization model.
"""
from .analysis_models import (
    AssistantAnalysisRequest, FiveSkillAnalysisResult, TradeCandidate, TradeProposal,
)
from .assessment import AssistantAssessment, build_assistant_assessment
from .five_skill_runtime import analyze_market

__all__ = [
    "analyze_market", "AssistantAnalysisRequest", "FiveSkillAnalysisResult", "TradeCandidate",
    "TradeProposal", "build_assistant_assessment", "AssistantAssessment",
]
