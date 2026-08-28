"""DayTrading skill 4: Risk Management -- "is the proposed day trade financially
acceptable, and what is the valid trade size?"

Thin wrapper over trade_management.evaluate_trade_management() (TRADE_MANAGEMENT_V1's
own geometry/sizing/RR engine, tick_size/tick_value-based, floor-only volume rounding --
never a parallel risk engine). This module only maps that result's overall_status
(READY/BLOCKED) onto DayTrading's own PASS/FAIL/UNRESOLVED vocabulary.
"""
from __future__ import annotations

from typing import Optional

from trade_management import TradeManagementRequest, evaluate_trade_management
from trade_management.models import OVERALL_READY

from .models import RISK_FAIL, RISK_PASS, RISK_UNRESOLVED, RiskManagementResult


def evaluate_risk_management(
    symbol: str,
    request: Optional[TradeManagementRequest],
) -> RiskManagementResult:
    if request is None:
        return RiskManagementResult(symbol=symbol, status=RISK_UNRESOLVED,
                                     reason="no trade geometry/sizing request supplied -- risk not evaluated.")

    tm = evaluate_trade_management(request)
    status = RISK_PASS if tm.overall_status == OVERALL_READY else RISK_FAIL
    rr = tm.geometry.rr_multiple if tm.geometry else None
    reason = None if status == RISK_PASS else ("; ".join(tm.reasons) or f"overall_status={tm.overall_status}.")

    return RiskManagementResult(symbol=symbol, status=status, trade_management=tm, risk_reward=rr, reason=reason)
