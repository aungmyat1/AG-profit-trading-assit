"""AG V1 FX/gold informational tickets from the frozen ST_ASIAN_SWEEP_5R_V1@1.1.1 engine.

The engine decides; this module never changes a rule. Ticket fields beyond the
TradeSignal come verbatim from the frozen contract's own definitions:
- leg 1 target = OPPOSITE_SESSION_BOUNDARY;
- leg 2 target = FIXED_R_MULTIPLE 5.0;
- time invalidation = 15:00 GMT.
Position size is omitted because risk_per_trade is unspecified in the contract (ledger open
gap). A READY is withheld by v1_tickets.guards: STALE when the data or signal bar closed more
than 15 min ago, SPREAD_TOO_WIDE when the live spread exceeds 15% of the stop distance, and
NO_TRADE (SPREAD_NOT_EVALUATED) when no live spread was supplied.

Symbol metadata and broker symbols come only from verified host captures (HOST_CAPTURED).
EURUSD and GBPUSD must resolve to their -VIP captures; there is no fallback to the plain
canonical symbol -- broker_symbol() raises METADATA_MISSING instead. Without a capture a ticket
is stamped FIXTURE_ONLY; EURUSD/GBPUSD prices still round to the owner-approved 5 digits.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, Optional, Sequence

from host_evidence.symbol_metadata import HOST_CAPTURED, METADATA_MISSING, HostDataError, load_record
from strategy_engine import evaluate, load_strategy
from strategy_engine.session import Candle
from v1_tickets.guards import gate_ready
from v1_tickets.ready_authority import SHADOW_INFO_ONLY, apply_ready_authority
from ticket_delivery.archive import (
    CYCLE_STATE_BLOCKED, CYCLE_STATE_DATA_ERROR, CYCLE_STATE_NO_TRADE, CYCLE_STATE_READY,
    CycleDecisionRecord, archive_cycle_decision,
)

STRATEGY_PATH = "strategies/ST_ASIAN_SWEEP_5R_V1.yaml"
V1_FX_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD")
V1_CYCLES = ("ASIAN_LONDON", "LONDON_NEWYORK")
REFERENCE_NOT_READY = "REFERENCE_NOT_READY"   # evaluated before the reference window closed (lifecycle)
# STALE-FIX-1: where a ticket's signal time came from. A signal age is measured only from the
# engine's own signal timestamp; there is no fallback to a trade-session bar.
SIGNAL_TIME_ENGINE = "ENGINE"
SIGNAL_TIME_MISSING = "MISSING"
SIGNAL_TIME_NOT_APPLICABLE = "NOT_APPLICABLE"
SIGNAL_TIME_UNAVAILABLE = "SIGNAL_TIME_UNAVAILABLE"   # SIGNAL without an engine timestamp -> DATA_ERROR
EVIDENCED_DIGITS = {"EURUSD": 5, "GBPUSD": 5}   # point 1e-05, owner-approved dataset manifests (rounding only)
REQUIRED_BROKER_SYMBOL = {"EURUSD": "EURUSD-VIP", "GBPUSD": "GBPUSD-VIP"}   # VT Markets tradable -VIP symbols
M15 = dt.timedelta(minutes=15)
HOST_METADATA_FIELDS = (
    "digits", "point", "trade_tick_size", "trade_tick_value", "trade_contract_size", "volume_min",
    "volume_step", "volume_max", "trade_stops_level", "trade_freeze_level", "spread", "currency_profit",
    "server UTC offset (broker_time)",
)
APPLICATION_RELEASE = "AG_V1_CLOUD"


def host_record(symbol: str) -> Optional[Dict[str, Any]]:
    """Verified host capture (sha256-checked); for EURUSD/GBPUSD only the -VIP capture counts."""
    record = load_record(symbol)
    if record is None or record["broker_symbol"] != REQUIRED_BROKER_SYMBOL.get(symbol, record["broker_symbol"]):
        return None
    return record


def _digits(symbol: str) -> Optional[int]:
    record = host_record(symbol)
    return int(record["fields"]["digits"]) if record is not None else EVIDENCED_DIGITS.get(symbol)


def metadata_status(symbol: str) -> str:
    return HOST_CAPTURED if host_record(symbol) is not None else "FIXTURE_ONLY"


def broker_symbol(symbol: str) -> str:
    """Exact broker symbol from the host capture. No fallback to the canonical name."""
    record = host_record(symbol)
    if record is None:
        raise HostDataError(METADATA_MISSING, f"{symbol}: no verified host capture"
                            + (f" of {REQUIRED_BROKER_SYMBOL[symbol]}" if symbol in REQUIRED_BROKER_SYMBOL else ""))
    return record["broker_symbol"]


def _r(symbol: str, value: Optional[float]) -> Optional[float]:
    digits = _digits(symbol) if value is not None else None
    return value if digits is None else round(value, digits)


def session_windows_utc(day: dt.date) -> Dict[str, Dict[str, tuple]]:
    """Fixed-UTC windows of the frozen session pairs (GMT in the YAML), half-open [start, end).
    Never DST-shifted (owner decision C3); local time is display-only via session_clock."""
    def at(t: str) -> dt.datetime:
        return dt.datetime.combine(day, dt.time(*map(int, str(t).split(":"))), tzinfo=dt.timezone.utc)
    return {p.pair_id: {"ref": (at(p.reference_session.start_time_gmt), at(p.reference_session.end_time_gmt)),
                        "trade": (at(p.trade_session.start_time_gmt), at(p.trade_session.end_time_gmt))}
            for p in load_strategy(STRATEGY_PATH).session_pairs}


def build_fx_error_ticket(
    symbol: str, cycle: str, session_date: dt.date, *, evaluated_at: dt.datetime,
    reason_code: str, detail: str = "", decision: str = "DATA_ERROR",
    data_source: str = "MT5_VT_MARKETS_DEMO",
) -> Dict[str, Any]:
    """Create an archivable fail-closed result when acquisition/runtime fails before
    the strategy engine can run.  It deliberately contains no entry or price levels."""
    if symbol not in V1_FX_SYMBOLS or cycle not in V1_CYCLES:
        raise ValueError(f"{symbol}/{cycle} is not a V1 FX ticket cycle")
    if decision not in ("DATA_ERROR", "BLOCKED"):
        raise ValueError("external failure decision must be DATA_ERROR or BLOCKED")
    strategy = load_strategy(STRATEGY_PATH)
    return {
        "label": "INFORMATIONAL TICKET -- NOT A BROKER ORDER",
        "strategy_id": strategy.strategy_id,
        "strategy_version": strategy.version,
        "symbol": symbol,
        "cycle": cycle,
        "session_date": session_date.isoformat(),
        "data_source": data_source,
        "evaluated_at": evaluated_at.astimezone(dt.timezone.utc).isoformat(),
        "metadata_status": metadata_status(symbol),
        "delivery_mode": "ARCHIVE_ONLY",
        "decision": decision,
        "reason_code": reason_code,
        "detail": detail[:300],
        "signal_time_source": SIGNAL_TIME_NOT_APPLICABLE,
    }


def build_fx_ticket(
    symbol: str, cycle: str, session_date: dt.date, session_candles: Sequence[Candle], expected_bar_count: int,
    post_session_candles: Sequence[Candle], *, data_source: str, evaluated_at: dt.datetime,
    data_close: Optional[dt.datetime] = None, spread: Optional[float] = None,
    strategy_path: str = STRATEGY_PATH,
) -> Dict[str, Any]:
    """`data_close`: close time of the latest live bar (None = no data-age gate); `spread`: live
    ask - bid in price units (None = SPREAD_NOT_EVALUATED, no READY). `strategy_path`: offline
    logic-gate replay of a registered candidate version only; runtime callers keep the default."""
    if symbol not in V1_FX_SYMBOLS or cycle not in V1_CYCLES:
        raise ValueError(f"{symbol}/{cycle} is not a V1 FX ticket cycle")
    strategy = load_strategy(strategy_path)
    base: Dict[str, Any] = {
        "label": "INFORMATIONAL TICKET -- NOT A BROKER ORDER", "strategy_id": strategy.strategy_id,
        "strategy_version": strategy.version, "symbol": symbol, "cycle": cycle,
        "session_date": session_date.isoformat(), "data_source": data_source,
        "evaluated_at": evaluated_at.astimezone(dt.timezone.utc).isoformat(),
        "metadata_status": metadata_status(symbol), "delivery_mode": "ARCHIVE_ONLY",
        "signal_time_source": SIGNAL_TIME_NOT_APPLICABLE,
    }
    ref_end = session_windows_utc(session_date)[cycle]["ref"][1]
    if evaluated_at < ref_end:
        # Lifecycle, not a data fault: the reference box cannot be complete before its window
        # closes. Decided on the clock alone, so missing/corrupt bars after ref_end still reach
        # the engine and stay DATA_ERROR.
        return {**base, "decision": REFERENCE_NOT_READY, "reason_code": REFERENCE_NOT_READY,
                "detail": f"reference window closes {ref_end.isoformat()}"}
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
        ticket["signal_time_source"] = SIGNAL_TIME_ENGINE if sig.signal_timestamp else SIGNAL_TIME_MISSING
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
    # entry_2/entry_3 stamp the qualifying M15 bar's open. A SIGNAL without that engine time
    # (e.g. entry_1, box-based) has no signal age, so it fails closed instead of borrowing a bar time.
    signal_open = sig.signal_timestamp if sig.status == "SIGNAL" else None
    if sig.status == "SIGNAL" and signal_open is None:
        ticket.update({"decision": "DATA_ERROR", "reason_code": SIGNAL_TIME_UNAVAILABLE,
                       "engine_reason_code": sig.reason_code, "signal_close_utc": None,
                       "detail": "engine supplied no signal timestamp; no signal age exists"})
        return apply_ready_authority(ticket)
    gated = gate_ready(ticket, now=evaluated_at, data_close=data_close,
                       signal_close=signal_open + M15 if signal_open is not None else None,
                       spread=spread, risk=sig.risk_distance)
    return apply_ready_authority(gated)            # D6: READY authority switch (config, fail closed)


_STATE = {"READY": CYCLE_STATE_READY, "NO_TRADE": CYCLE_STATE_NO_TRADE, "DATA_ERROR": CYCLE_STATE_DATA_ERROR,
          "BLOCKED": CYCLE_STATE_BLOCKED,
          # Gate-withheld decisions archive as NO_TRADE; the payload/reason code keeps the specific state.
          "STALE": CYCLE_STATE_NO_TRADE, "SPREAD_TOO_WIDE": CYCLE_STATE_NO_TRADE,
          REFERENCE_NOT_READY: CYCLE_STATE_NO_TRADE, SHADOW_INFO_ONLY: CYCLE_STATE_NO_TRADE}


def archive_fx_ticket(ticket: Dict[str, Any], root: str) -> str:
    record = CycleDecisionRecord(
        strategy_id=ticket["strategy_id"], strategy_version=ticket["strategy_version"],
        application_release=APPLICATION_RELEASE, symbol=ticket["symbol"], cycle=ticket["cycle"],
        trading_date=dt.date.fromisoformat(ticket["session_date"]), cycle_state=_STATE[ticket["decision"]],
        evaluation_time_utc=ticket["evaluated_at"], payload=ticket, reason_codes=(ticket["reason_code"],),
    )
    return archive_cycle_decision(record, root=root)
