"""Non-executable proposed trade ticket. STOP after this -- there is no path from here to any
broker order call. `execution_authorized` is a constant False, not a parameter.

Geometry comes from the engine's TradeSignal and the contract's own target legs:
TP1 = OPPOSITE_SESSION_BOUNDARY, TP2 = FIXED_R_MULTIPLE (contract total_target_r).
Risk % comes only from the resolved proposal scope (release pilot config); lots are
computed only when that is resolved AND the quote currency equals the account currency.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Optional

PROPOSAL_STATUS = "PROPOSED_INFORMATIONAL_NOT_EXECUTABLE"


def build_ticket(*, signal, strategy, record, quote, scope, account: Optional[dict], session: str,
                 now_utc: datetime, market_context: dict, data_freshness: dict) -> dict:
    long = signal.direction == "LONG"
    entry, sl, risk = signal.entry, signal.stop_loss, signal.risk_distance
    tp1 = signal.box_high if long else signal.box_low
    leg2 = next((l for l in strategy.legs if l.target_type == "FIXED_R_MULTIPLE"), None)
    r_mult = leg2.fixed_r_multiple if leg2 else strategy.total_target_r
    tp2 = entry + r_mult * risk if long else entry - r_mult * risk

    position_size, risk_amount, size_note = "NOT_CALCULATED", None, None
    equity = (account or {}).get("equity")
    acct_ccy = (account or {}).get("currency")
    if scope is None or not scope.authorized or scope.risk_per_trade_pct is None:
        size_note = "RISK_POLICY_AMBIGUOUS"
    elif not equity or not risk or risk <= 0:
        size_note = "ACCOUNT_EQUITY_OR_RISK_DISTANCE_UNAVAILABLE"
    else:
        risk_amount = round(float(equity) * scope.risk_per_trade_pct / 100.0, 2)
        if record.currency_profit != acct_ccy or record.contract_size <= 0 or record.volume_step <= 0:
            size_note = "CROSS_CURRENCY_CONVERSION_NOT_WIRED"
        else:
            raw = risk_amount / (risk * record.contract_size)
            lots = math.floor(raw / record.volume_step + 1e-9) * record.volume_step
            if lots < record.volume_min:
                size_note = "BELOW_BROKER_VOLUME_MIN"
            else:
                position_size = round(lots, 2)

    rr = lambda tp: round(abs(tp - entry) / risk, 2) if risk else None  # noqa: E731
    return {
        "ticket_id": f"SCAN:{signal.signal_id}",
        "timestamp_utc": now_utc.isoformat(),
        "canonical_symbol": record.canonical_symbol,
        "broker_symbol": record.broker_symbol,
        "strategy_id": signal.strategy_id,
        "strategy_version": signal.strategy_version,
        "session": session,
        "direction": signal.direction,
        "entry_type": strategy.entry_order_type,
        "entry_price": entry,
        "stop_loss": sl,
        "take_profit_1": tp1,
        "take_profit_2": round(tp2, record.digits),
        "risk_pct": scope.risk_per_trade_pct if scope else None,
        "risk_policy_source": scope.pilot_id if scope else None,
        "position_size": position_size,
        "position_size_note": size_note,
        "risk_amount": risk_amount,
        "rr_tp1": rr(tp1),
        "rr_tp2": rr(tp2),
        "invalidation": {"stop_loss": sl, "time": strategy.time_invalidation,
                         "structural": strategy.structural_invalidation},
        "market_context": market_context,
        "trigger_evidence": {"reason_code": signal.reason_code, "setup": signal.setup, "regime": signal.regime,
                             "signal_timestamp_utc": signal.signal_timestamp.isoformat() if signal.signal_timestamp else None,
                             "box_high": signal.box_high, "box_low": signal.box_low, "box_mid": signal.box_mid},
        "current_quote": quote.as_dict() if quote else None,
        "data_source": record.price_source,
        "data_freshness": data_freshness,
        "proposal_status": PROPOSAL_STATUS,
        "execution_authorized": False,
    }
