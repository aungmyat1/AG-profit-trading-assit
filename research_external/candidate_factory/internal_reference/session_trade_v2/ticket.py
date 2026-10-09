from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, Sequence

from .engine import evaluate
from .models import Candle


def build_ticket(symbol: str, cycle: str, session_date: date,
                 reference_candles: Sequence[Candle], trade_candles: Sequence[Candle],
                 *, data_source: str = "MT5_VT_MARKETS_DEMO",
                 evaluated_at: datetime | None = None) -> Dict[str, Any]:
    """Build an informational V2 proposal. Never sizes or sends an order."""
    evaluated_at = evaluated_at or datetime.now(timezone.utc)
    d = evaluate(symbol, cycle, reference_candles, trade_candles)
    ticket: Dict[str, Any] = {
        "label": "INFORMATIONAL TICKET -- NOT A BROKER ORDER",
        "strategy_id": d.strategy_id,
        "strategy_version": d.strategy_version,
        "symbol": symbol,
        "cycle": cycle,
        "session_date": session_date.isoformat(),
        "data_source": data_source,
        "evaluated_at": evaluated_at.astimezone(timezone.utc).isoformat(),
        "delivery_mode": "ARCHIVE_ONLY",
        "execution_authority": "NONE",
        "demo_authorized": False,
        "live_authorized": False,
        "allow_order_send": False,
        "decision": "READY" if d.status == "SIGNAL" else "NO_TRADE",
        "reason_code": d.reason_code,
        "setup": d.setup,
        "box": {"high": d.box_high, "low": d.box_low, "mid": d.box_mid},
        "signal_timestamp": d.signal_timestamp.isoformat() if d.signal_timestamp else None,
    }
    if d.status == "SIGNAL":
        ticket.update({
            "direction": d.direction,
            "entry_order_type": d.entry_order_type,
            "entry": d.entry,
            "stop_loss": d.stop_loss,
            "risk_distance": d.risk_distance,
            "risk_per_trade_pct": 0.5,
            "position_size": "NOT_CALCULATED_RESEARCH_SHADOW",
            "targets": [
                {"leg": 1, "volume_pct": 0.75, "type": "FIXED_R_MULTIPLE_4", "price": d.target_4r},
                {"leg": 2, "volume_pct": 0.25, "type": "FIXED_R_MULTIPLE_5", "price": d.target_5r},
            ],
            "management": d.management,
        })
    return ticket
