"""run_daily_routine() -- the D1 -> H1 -> M5 gate sequence (spec section 13). Never
allows D1 -> proposal or H1 -> execute directly; M5 only runs once H1 has a location,
and a proposal_id only appears once M5 reaches READY_FOR_PROPOSAL AND risk passes."""
from __future__ import annotations

from .d1_context import build_d1_context
from .h1_setup import build_h1_setup_context
from .m5_execution import evaluate_m5_execution
from .models import (
    DIRECTIONAL_PERMISSION_INDETERMINATE,
    DIRECTIONAL_PERMISSION_NO_TRADE,
    H1_INVALIDATED,
    M5_INDETERMINATE,
    M5_NO_TRADE,
    M5_READY_FOR_PROPOSAL,
    M5_RISK_REJECTED,
    DailyRoutineResult,
)

_NEXT_ACTION = {
    "D1_UNAVAILABLE": "Wait for D1 market data to become available.",
    "D1_INDETERMINATE": "D1 structure is undefined -- no directional permission; wait for the next D1 close.",
    "H1_WAITING": "Wait for an H1 POI aligned with the D1 direction to form.",
    "M5_WAITING": "Wait for M5 sweep/confirmation aligned with the selected H1 POI.",
    "RISK_REJECTED": "Entry/stop geometry or sizing failed trade_management's checks -- no proposal.",
    "READY": "A risk-managed entry array is ready -- review the proposal for explicit user approval.",
    "NO_TRADE": "No qualifying setup found this cycle.",
}


def run_daily_routine(symbol: str, strategy_id: str = "SMC_CONDITIONAL_ENTRY_V2") -> DailyRoutineResult:
    d1 = build_d1_context(symbol)

    if d1.status == "UNAVAILABLE":
        h1 = build_h1_setup_context(symbol, d1)
        return DailyRoutineResult(symbol=symbol, as_of=None, d1=d1, h1=h1,
                                  m5=_blocked_m5(symbol, h1), overall_status="STALE_DATA",
                                  next_action=_NEXT_ACTION["D1_UNAVAILABLE"])

    if d1.directional_permission in (DIRECTIONAL_PERMISSION_INDETERMINATE, DIRECTIONAL_PERMISSION_NO_TRADE):
        h1 = build_h1_setup_context(symbol, d1)
        return DailyRoutineResult(symbol=symbol, as_of=None, d1=d1, h1=h1,
                                  m5=_blocked_m5(symbol, h1), overall_status="INDETERMINATE",
                                  next_action=_NEXT_ACTION["D1_INDETERMINATE"])

    h1 = build_h1_setup_context(symbol, d1)

    if h1.status == H1_INVALIDATED:
        return DailyRoutineResult(symbol=symbol, as_of=None, d1=d1, h1=h1, m5=_blocked_m5(symbol, h1),
                                  overall_status="INVALIDATED", next_action=_NEXT_ACTION["H1_WAITING"])

    if h1.selected_poi is None:
        return DailyRoutineResult(symbol=symbol, as_of=None, d1=d1, h1=h1, m5=_blocked_m5(symbol, h1),
                                  overall_status="WAITING", next_action=_NEXT_ACTION["H1_WAITING"])

    m5 = evaluate_m5_execution(symbol, h1, strategy_id=strategy_id)

    if m5.status == M5_READY_FOR_PROPOSAL:
        overall, action = "READY_FOR_PROPOSAL", _NEXT_ACTION["READY"]
    elif m5.status == M5_RISK_REJECTED:
        overall, action = "RISK_REJECTED", _NEXT_ACTION["RISK_REJECTED"]
    elif m5.status == M5_NO_TRADE:
        overall, action = "NO_TRADE", _NEXT_ACTION["NO_TRADE"]
    elif m5.status == M5_INDETERMINATE:
        overall, action = "INDETERMINATE", _NEXT_ACTION["M5_WAITING"]
    else:
        overall, action = "WAITING", _NEXT_ACTION["M5_WAITING"]

    proposal_id = m5.entry_array_result.proposal_id if (
        overall == "READY_FOR_PROPOSAL" and m5.entry_array_result is not None) else None

    return DailyRoutineResult(symbol=symbol, as_of=m5.as_of, d1=d1, h1=h1, m5=m5,
                              overall_status=overall, next_action=action, proposal_id=proposal_id)


def _blocked_m5(symbol: str, h1) -> "M5ExecutionContext":  # noqa: F821 -- see models.M5ExecutionContext
    from .models import M5ExecutionContext, M5_WAITING_H1_LOCATION
    return M5ExecutionContext(symbol=symbol, as_of=None, d1_permission=h1.d1_directional_permission,
                              h1_location=h1.status, status=M5_WAITING_H1_LOCATION,
                              reasoning_codes=("D1_OR_H1_NOT_READY",))
