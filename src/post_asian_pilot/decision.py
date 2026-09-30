"""PostAsianDecision: normalizes strategy_engine.evaluate()'s TradeSignal (plus
window/regime context) into the pilot's six public states -- WATCH/READY/NO_TRADE/
DATA_ERROR/EXPIRED/BLOCKED. DATA_ERROR is produced by the caller from a caught
MarketDataError (never translated into NO_TRADE, per spec); BLOCKED is layered on top by
governor.py/tiebreak.py after a READY decision passes portfolio/risk gates -- this module
only ever emits WATCH/READY/NO_TRADE/EXPIRED itself.

SCOPE DECISION (documented, not silent): strategy_engine.session.route_completed_session
is a generic TREND/SWEEP/RANGE router shared by other session strategies, but
ST_ASIAN_SWEEP_5R_V1's own entry_rules (strategies/ST_ASIAN_SWEEP_5R_V1.yaml) define ONLY
sweep triggers (SWEEP_REFERENCE_LOW/HIGH) -- no trend or range-boundary-rejection entry
formulas anywhere in that file. A VALID TradeSignal whose `setup` is TREND or RANGE is
therefore NOT part of this strategy's own signed contract and is deliberately mapped to
NO_TRADE (reason NON_SWEEP_SETUP_OUT_OF_SCOPE) rather than promoted to READY -- this
preserves "ST_ASIAN_SWEEP_5R_V1's existing canonical sweep semantics" exactly, without
ever needing to modify the shared, frozen strategy_engine router.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, Tuple

from strategy_engine.models import TradeSignal

STATUS_WATCH = "WATCH"
STATUS_READY = "READY"
STATUS_NO_TRADE = "NO_TRADE"
STATUS_DATA_ERROR = "DATA_ERROR"
STATUS_EXPIRED = "EXPIRED"
STATUS_BLOCKED = "BLOCKED"

_OUT_OF_SCOPE_REASON = "NON_SWEEP_SETUP_OUT_OF_SCOPE"


@dataclass(frozen=True)
class PostAsianDecision:
    decision_id: str
    strategy_id: str
    strategy_version: str
    symbol: str
    trading_date: date
    reference_session: str
    status: str
    reason_codes: Tuple[str, ...]
    evaluation_time: datetime
    session_snapshot_id: Optional[str] = None
    signal: Optional[TradeSignal] = None
    # The CLOSED M15 candle whose completion caused READY (strategy_engine's own
    # SetupDecision.signal_timestamp, verbatim) -- NOT evaluation_time (polling/wall-clock
    # time). This is the ONLY field selection/tie-break logic may order candidates by; see
    # tiebreak.py. None for non-READY decisions (nothing "became ready").
    ready_at: Optional[datetime] = None
    missing_condition: Optional[str] = None
    trigger_type: Optional[str] = None
    trigger_level: Optional[float] = None
    trigger_timeframe: Optional[str] = None
    valid_until: Optional[datetime] = None


def _decision_id(strategy_id: str, symbol: str, trading_date: date, evaluation_time: datetime) -> str:
    import hashlib
    digest = hashlib.blake2b(
        f"{strategy_id}|{symbol}|{trading_date.isoformat()}|{evaluation_time.isoformat()}".encode("utf-8"),
        digest_size=8,
    ).hexdigest()
    return f"DECISION-{symbol}-{digest}"


def map_trade_signal_to_decision(
    signal: TradeSignal, session_snapshot_id: str, evaluation_time: datetime,
    window_end_utc: datetime,
) -> PostAsianDecision:
    common = dict(
        decision_id=_decision_id(signal.strategy_id, signal.symbol, signal.session_date, evaluation_time),
        strategy_id=signal.strategy_id, strategy_version=signal.strategy_version, symbol=signal.symbol,
        trading_date=signal.session_date, reference_session=signal.reference_session,
        evaluation_time=evaluation_time, session_snapshot_id=session_snapshot_id, signal=signal,
    )

    if signal.status == "SIGNAL":
        if signal.setup == "SWEEP":
            if signal.signal_timestamp is None:
                # STOP CONDITION (spec): ready_at must be derivable from authoritative
                # strategy evidence. entry_2_sweep always sets signal_timestamp for a
                # VALID sweep decision -- reaching here means that invariant broke.
                raise ValueError(
                    f"READY sweep signal {signal.signal_id!r} has no signal_timestamp -- "
                    "cannot derive ready_at from authoritative strategy evidence")
            return PostAsianDecision(
                status=STATUS_READY, reason_codes=(signal.reason_code,),
                ready_at=signal.signal_timestamp,
                trigger_type="LIQUIDITY_SWEEP", trigger_level=signal.entry, trigger_timeframe="M15",
                valid_until=window_end_utc, **common,
            )
        return PostAsianDecision(
            status=STATUS_NO_TRADE, reason_codes=(signal.reason_code, _OUT_OF_SCOPE_REASON), **common,
        )

    # status == "NO_TRADE"
    if signal.reason_code == "NO_SETUP_BY_WINDOW_END":
        if evaluation_time >= window_end_utc:
            return PostAsianDecision(status=STATUS_EXPIRED, reason_codes=(signal.reason_code,), **common)
        return PostAsianDecision(
            status=STATUS_WATCH, reason_codes=(signal.reason_code,),
            missing_condition="WAITING_REFERENCE_SWEEP", trigger_type="LIQUIDITY_SWEEP",
            trigger_timeframe="M15", valid_until=window_end_utc, **common,
        )

    return PostAsianDecision(status=STATUS_NO_TRADE, reason_codes=(signal.reason_code,), **common)


def data_error_decision(
    strategy_id: str, strategy_version: str, symbol: str, trading_date: date,
    reference_session: str, evaluation_time: datetime, reason_codes: Tuple[str, ...],
) -> PostAsianDecision:
    return PostAsianDecision(
        decision_id=_decision_id(strategy_id, symbol, trading_date, evaluation_time),
        strategy_id=strategy_id, strategy_version=strategy_version, symbol=symbol, trading_date=trading_date,
        reference_session=reference_session, status=STATUS_DATA_ERROR, reason_codes=reason_codes,
        evaluation_time=evaluation_time,
    )


def watch_decision(
    strategy_id: str, strategy_version: str, symbol: str, trading_date: date,
    reference_session: str, evaluation_time: datetime, missing_condition: str,
    reason_codes: Tuple[str, ...] = (), valid_until: Optional[datetime] = None,
) -> PostAsianDecision:
    """For pre-evaluation WATCH states (session not yet frozen, window not yet open) --
    no TradeSignal exists yet to map."""
    return PostAsianDecision(
        decision_id=_decision_id(strategy_id, symbol, trading_date, evaluation_time),
        strategy_id=strategy_id, strategy_version=strategy_version, symbol=symbol, trading_date=trading_date,
        reference_session=reference_session, status=STATUS_WATCH, reason_codes=reason_codes,
        evaluation_time=evaluation_time, missing_condition=missing_condition, valid_until=valid_until,
    )
