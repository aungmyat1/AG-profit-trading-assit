"""Application service for the observe-only Owner Analysis read model."""
from __future__ import annotations

from typing import Optional

from post_asian_pilot.pipeline import PairResult, PilotCycleResult, run_pilot_cycle
from post_asian_pilot.pilot_config import load_pilot_config

from .schemas import OpportunityAnalysisResponse


class OpportunityAnalysisError(ValueError):
    """A client-safe, fail-closed evaluation error."""


def _iso(value) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _project_pair(result: PilotCycleResult, pair: PairResult) -> OpportunityAnalysisResponse:
    decision = pair.decision
    proposal = pair.proposal
    trade = proposal.trade_proposal if proposal is not None else None
    expires_at = proposal.expires_at if proposal is not None else None
    if expires_at is None and decision.status == "EXPIRED":
        expires_at = decision.valid_until

    # The evaluation timestamp is the existing pipeline clock for this result. No
    # second freshness policy is introduced for this read model.
    is_stale = decision.status == "EXPIRED" or (
        expires_at is not None and result.evaluation_time > expires_at
    )
    if proposal is not None and decision.status == "READY":
        proposal_state = "PROPOSAL_READY" if not is_stale else "EXPIRED"
    elif pair.portfolio_state == "BLOCKED":
        proposal_state = "BLOCKED"
    else:
        proposal_state = "NONE"

    signal = decision.signal
    direction = signal.direction if signal is not None else None
    entry = trade.entry if trade is not None else None
    stop = trade.stop_loss if trade is not None else None
    targets = [value for value in (
        getattr(trade, "tp1", None) if trade is not None else None,
        getattr(trade, "tp2", None) if trade is not None else None,
    ) if value is not None]
    capacity_available = pair.portfolio_state in {"ELIGIBLE", "SELECTED"}
    capacity_reason = pair.portfolio_reason_code or (
        "AVAILABLE" if capacity_available else "NOT_AVAILABLE"
    )
    return OpportunityAnalysisResponse(
        strategy_id=result.strategy.strategy_id,
        symbol=pair.symbol,
        decision_state=decision.status,
        portfolio_state=pair.portfolio_state,
        proposal_state=proposal_state,
        evaluated_at=decision.evaluation_time.isoformat(),
        market_data_as_of=_iso(pair.market_snapshot.market_data_asof if pair.market_snapshot else None),
        proposal_expires_at=_iso(expires_at),
        is_stale=is_stale,
        direction=direction,
        entry=entry,
        stop=stop,
        targets=targets,
        capacity_available=capacity_available,
        capacity_reason=capacity_reason,
        reason_codes=list(decision.reason_codes),
        missing_condition=decision.missing_condition,
        next_required_evidence=decision.missing_condition,
        execution_authority="NONE",
    )


def get_opportunity_analysis(symbol: Optional[str] = None, pilot_path: Optional[str] = None) -> list[OpportunityAnalysisResponse]:
    """Evaluate the existing Post-Asian strategy through its audited read path."""
    pilot = load_pilot_config(pilot_path) if pilot_path else load_pilot_config()
    if symbol is not None and symbol not in pilot.universe:
        raise OpportunityAnalysisError("UNSUPPORTED_SYMBOL")
    try:
        result = run_pilot_cycle(pilot_path, observe_only=True)
    except OpportunityAnalysisError:
        raise
    except Exception as exc:  # caller turns this into a structured 502
        raise OpportunityAnalysisError(f"EVALUATION_ERROR:{type(exc).__name__}") from exc
    pairs = [pair for pair in result.pairs if symbol is None or pair.symbol == symbol]
    if not pairs:
        raise OpportunityAnalysisError("UNSUPPORTED_SYMBOL")
    return [_project_pair(result, pair) for pair in pairs]
