"""AG V1 FX/gold informational tickets from the frozen ST_ASIAN_SWEEP_5R_V1@1.1.1 engine.

The engine decides; this module never changes a rule. Ticket fields beyond the
TradeSignal come verbatim from the frozen contract's own definitions:
- leg 1 target = OPPOSITE_SESSION_BOUNDARY;
- leg 2 target = FIXED_R_MULTIPLE 5.0;
- time invalidation = 15:00 GMT.
Position size is omitted because risk_per_trade is unspecified in the contract (ledger open
gap). The spread check is NOT_EVALUATED because the cycle has no live quote.

Symbol metadata: EURUSD and GBPUSD have repo-evidenced point sizes (owner-approved
manifests). USDJPY and XAUUSD have none, so their tickets are stamped FIXTURE_ONLY and
prices are left unrounded until the host captures MT5 symbol_info() (see
HOST_METADATA_FIELDS).
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, Optional, Sequence

from strategy_engine import evaluate, load_strategy
from strategy_engine.session import Candle
from ticket_delivery.archive import (
    CYCLE_STATE_DATA_ERROR, CYCLE_STATE_NO_TRADE, CYCLE_STATE_READY, CycleDecisionRecord, archive_cycle_decision,
)

STRATEGY_PATH = "strategies/ST_ASIAN_SWEEP_5R_V1.yaml"
V1_FX_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD")
V1_CYCLES = ("ASIAN_LONDON", "LONDON_NEWYORK")
EVIDENCED_DIGITS = {"EURUSD": 5, "GBPUSD": 5}   # point 1e-05, owner-approved dataset manifests
HOST_METADATA_FIELDS = (
    "digits", "point", "trade_tick_size", "trade_tick_value", "trade_contract_size", "volume_min",
    "volume_step", "volume_max", "trade_stops_level", "trade_freeze_level", "spread", "currency_profit",
    "server UTC offset (broker_time)",
)
APPLICATION_RELEASE = "AG_V1_CLOUD"


def metadata_status(symbol: str) -> str:
    return "REPO_EVIDENCED" if symbol in EVIDENCED_DIGITS else "FIXTURE_ONLY"


def _r(symbol: str, value: Optional[float]) -> Optional[float]:
    if value is None or symbol not in EVIDENCED_DIGITS:
        return value
    return round(value, EVIDENCED_DIGITS[symbol])


def build_fx_ticket(
    symbol: str, cycle: str, session_date: dt.date, session_candles: Sequence[Candle], expected_bar_count: int,
    post_session_candles: Sequence[Candle], *, data_source: str, evaluated_at: dt.datetime,
) -> Dict[str, Any]:
    if symbol not in V1_FX_SYMBOLS or cycle not in V1_CYCLES:
        raise ValueError(f"{symbol}/{cycle} is not a V1 FX ticket cycle")
    strategy = load_strategy(STRATEGY_PATH)
    base: Dict[str, Any] = {
        "label": "INFORMATIONAL TICKET -- NOT A BROKER ORDER", "strategy_id": strategy.strategy_id,
        "strategy_version": strategy.version, "symbol": symbol, "cycle": cycle,
        "session_date": session_date.isoformat(), "data_source": data_source,
        "evaluated_at": evaluated_at.astimezone(dt.timezone.utc).isoformat(),
        "metadata_status": metadata_status(symbol), "delivery_mode": "ARCHIVE_ONLY",
    }
    try:
        sig = evaluate(strategy, cycle, symbol, session_date, session_candles, expected_bar_count,
                       post_session_candles)
    except Exception as exc:  # noqa: BLE001 -- any engine/data failure is a DATA_ERROR ticket, never a guess
        return {**base, "decision": "DATA_ERROR", "reason_code": type(exc).__name__, "detail": str(exc)[:300]}
    ticket = {**base, "decision": "READY" if sig.status == "SIGNAL" else "NO_TRADE", "reason_code": sig.reason_code,
              "regime": sig.regime, "setup": sig.setup, "signal_id": sig.signal_id,
              "box": {"high": _r(symbol, sig.box_high), "low": _r(symbol, sig.box_low), "mid": _r(symbol, sig.box_mid)},
              "signal_timestamp": sig.signal_timestamp.isoformat() if sig.signal_timestamp else None}
    if sig.status == "SIGNAL":
        long = sig.direction == "LONG"
        tp1 = sig.box_high if long else sig.box_low
        tp2 = sig.entry + (5.0 if long else -5.0) * sig.risk_distance
        ticket.update({
            "direction": sig.direction, "entry_order_type": "MARKET", "entry": _r(symbol, sig.entry),
            "stop_loss": _r(symbol, sig.stop_loss), "risk_distance": sig.risk_distance,
            "targets": [{"leg": 1, "volume_pct": 0.75, "type": "OPPOSITE_SESSION_BOUNDARY", "price": _r(symbol, tp1)},
                        {"leg": 2, "volume_pct": 0.25, "type": "FIXED_R_MULTIPLE_5", "price": _r(symbol, tp2)}],
            "time_invalidation_gmt": "15:00", "spread_check": "NOT_EVALUATED", "position_size": "NOT_SPECIFIED",
        })
    return ticket


_STATE = {"READY": CYCLE_STATE_READY, "NO_TRADE": CYCLE_STATE_NO_TRADE, "DATA_ERROR": CYCLE_STATE_DATA_ERROR}


def archive_fx_ticket(ticket: Dict[str, Any], root: str) -> str:
    record = CycleDecisionRecord(
        strategy_id=ticket["strategy_id"], strategy_version=ticket["strategy_version"],
        application_release=APPLICATION_RELEASE, symbol=ticket["symbol"], cycle=ticket["cycle"],
        trading_date=dt.date.fromisoformat(ticket["session_date"]), cycle_state=_STATE[ticket["decision"]],
        evaluation_time_utc=ticket["evaluated_at"], payload=ticket, reason_codes=(ticket["reason_code"],),
    )
    return archive_cycle_decision(record, root=root)
