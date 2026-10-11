"""AG_TRADING_ASSISTANT_WORKFLOW_V1 canonical top-level states (spec section 22): maps
each technique's own detailed internal state vocabulary (daytrading.models.STATE_*/
LTF_*/RISK_*, five_skill_runtime's overall_status) onto the small practical vocabulary
NO_CONTEXT / WAIT_POI / WAIT_CONFIRMATION / RISK_CHECK / TRADE_PROPOSAL_READY /
NO_TRADE / INVALIDATED / UNRESOLVED -- pure mapping, no new detection, and the detailed
internal states stay exactly as they are on the underlying result (spec section 22:
"do not destroy detailed sub-statuses")."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from assistant.analysis_models import FiveSkillAnalysisResult
    from daytrading.models import DayTradingResult

NO_CONTEXT = "NO_CONTEXT"
WAIT_POI = "WAIT_POI"
WAIT_CONFIRMATION = "WAIT_CONFIRMATION"
RISK_CHECK = "RISK_CHECK"
TRADE_PROPOSAL_READY = "TRADE_PROPOSAL_READY"
NO_TRADE = "NO_TRADE"
INVALIDATED = "INVALIDATED"
UNRESOLVED = "UNRESOLVED"

CANONICAL_STATES = (
    NO_CONTEXT, WAIT_POI, WAIT_CONFIRMATION, RISK_CHECK, TRADE_PROPOSAL_READY,
    NO_TRADE, INVALIDATED, UNRESOLVED,
)

_DAYTRADING_STATE_MAP = {
    "WAIT_NARRATIVE": NO_CONTEXT,
    "WAIT_AFFINITY": WAIT_POI,
    "WAIT_LTF_EXECUTION": WAIT_CONFIRMATION,
    "WAIT_RISK": RISK_CHECK,
    "TRADE_READY_LONG": TRADE_PROPOSAL_READY,
    "TRADE_READY_SHORT": TRADE_PROPOSAL_READY,
    "NO_TRADE": NO_TRADE,
    "INVALIDATED": INVALIDATED,
}


def daytrading_canonical_state(result: "DayTradingResult") -> str:
    """Maps DayTradingResult.trade_state -- narrative UNRESOLVED (bias never became
    directional) is reported as trade_state=NO_TRADE upstream (daytrading.pipeline.
    derive_trade_state), so it's distinguished here directly off narrative_bias.bias
    rather than losing that distinction in the STATE_NO_TRADE bucket."""
    from daytrading.models import BIAS_BULLISH, BIAS_BEARISH

    if result.narrative_bias is not None and result.narrative_bias.bias not in (BIAS_BULLISH, BIAS_BEARISH):
        return NO_CONTEXT
    return _DAYTRADING_STATE_MAP.get(result.trade_state, UNRESOLVED)


_SMC_OVERALL_STATUS_MAP = {
    "READY": TRADE_PROPOSAL_READY,
    "PARTIAL": WAIT_CONFIRMATION,
    "BLOCKED": NO_CONTEXT,
}


def smc_canonical_state(result: "FiveSkillAnalysisResult") -> str:
    """SMC is advisory analysis, not a trade-state machine (spec section 32) -- READY
    means every requested skill produced usable evidence (closest analogue to a
    completed analysis, not literally an executable proposal), PARTIAL means some
    evidence is missing/waiting, BLOCKED means market context itself was unavailable."""
    return _SMC_OVERALL_STATUS_MAP.get(result.overall_status, UNRESOLVED)
