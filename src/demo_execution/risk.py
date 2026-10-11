"""C14 S1 risk caps over an explicit, complete host snapshot; pure sizing only.

No position/account query happens here. The future canonical C11 adapter must
supply a fresh DEMO snapshot (including foreign positions and reconciled daily
metrics); absence or incompleteness is a block, never a zero/default.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import ROUND_FLOOR, Decimal, InvalidOperation
from typing import Any, Optional, Sequence

from sizing_math.risk import size_position
from v1_tickets.guards import STALE_AFTER

MAX_RISK_PER_TRADE_PCT = 0.5
MAX_OPEN_POSITIONS_PER_INSTRUMENT = 1
MAX_TRADES_PER_STRATEGY_DAY = 5
MAX_STRATEGY_DAILY_LOSS_PCT = 1.0
MAX_ACCOUNT_DAILY_LOSS_PCT = 2.0


@dataclass(frozen=True)
class OpenPosition:
    """Read-only position projection; foreign magic numbers still occupy the symbol."""

    symbol: str
    magic_number: Optional[int]


@dataclass(frozen=True)
class RiskSnapshot:
    """Required inputs supplied by the future host/reconciliation integration.

    Daily loss values are positive percentages of the same DEMO-equity basis used
    for per-trade risk; they must include all reconciled realized and current open
    loss for the VT server day. `server_day` is supplied by that adapter, not
    guessed from UTC/local time. The pending reset-timezone confirmation is exposed
    in the result and in the committed scope config.
    """

    observed_at_utc: Optional[datetime]
    server_day: Optional[date]
    demo_equity: Optional[float]
    strategy_daily_loss_pct: Optional[float]
    account_daily_loss_pct: Optional[float]
    strategy_trades_today: Optional[int]
    open_positions: Optional[Sequence[OpenPosition]]
    positions_complete: bool
    daily_metrics_complete: bool
    symbol_meta: Any = None
    daily_reset_basis: Optional[str] = None


@dataclass(frozen=True)
class RiskAssessment:
    allowed: bool
    reason_code: str
    planned_volume: Optional[float] = None
    planned_risk_amount: Optional[float] = None
    planned_risk_pct: Optional[float] = None
    own_positions_on_symbol: int = 0
    foreign_positions_on_symbol: int = 0
    server_day: Optional[date] = None
    daily_reset_owner_confirm: bool = True


def _finite_number(value: Any, *, positive: bool = False) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if not math.isfinite(float(value)):
        return False
    return float(value) > 0 if positive else float(value) >= 0


def _aware_utc(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(timezone.utc)


def evaluate_risk_caps(ticket: dict[str, Any], scope: Any, snapshot: Optional[RiskSnapshot], *,
                       now_utc: datetime) -> RiskAssessment:
    """Apply all five approved limits and return size only when every input is verified."""
    if snapshot is None:
        return RiskAssessment(False, "RISK_SNAPSHOT_MISSING", daily_reset_owner_confirm=True)
    now = _aware_utc(now_utc)
    observed = _aware_utc(snapshot.observed_at_utc)
    if now is None or observed is None or observed > now or now - observed > STALE_AFTER:
        return RiskAssessment(False, "RISK_SNAPSHOT_STALE_OR_INVALID",
                              daily_reset_owner_confirm=bool(scope.daily_reset_owner_confirm))
    if (type(snapshot.server_day) is not date
            or snapshot.daily_reset_basis != scope.daily_reset_basis):
        return RiskAssessment(False, "RISK_SERVER_DAY_UNAVAILABLE",
                              daily_reset_owner_confirm=bool(scope.daily_reset_owner_confirm))
    if not _finite_number(snapshot.demo_equity, positive=True):
        return RiskAssessment(False, "RISK_DEMO_EQUITY_UNAVAILABLE", server_day=snapshot.server_day,
                              daily_reset_owner_confirm=bool(scope.daily_reset_owner_confirm))
    if (not snapshot.positions_complete or snapshot.open_positions is None
            or not snapshot.daily_metrics_complete):
        return RiskAssessment(False, "RISK_SNAPSHOT_INCOMPLETE", server_day=snapshot.server_day,
                              daily_reset_owner_confirm=bool(scope.daily_reset_owner_confirm))
    if (not _finite_number(snapshot.strategy_daily_loss_pct)
            or not _finite_number(snapshot.account_daily_loss_pct)
            or isinstance(snapshot.strategy_trades_today, bool)
            or not isinstance(snapshot.strategy_trades_today, int)
            or snapshot.strategy_trades_today < 0):
        return RiskAssessment(False, "RISK_DAILY_METRICS_INVALID", server_day=snapshot.server_day,
                              daily_reset_owner_confirm=bool(scope.daily_reset_owner_confirm))
    if snapshot.strategy_trades_today >= MAX_TRADES_PER_STRATEGY_DAY:
        return RiskAssessment(False, "STRATEGY_DAILY_TRADE_LIMIT", server_day=snapshot.server_day,
                              daily_reset_owner_confirm=bool(scope.daily_reset_owner_confirm))

    matching_positions: list[OpenPosition] = []
    accepted_names = {scope.symbol.upper(), scope.broker_symbol.upper()}
    for position in snapshot.open_positions:
        if not isinstance(position, OpenPosition) or not isinstance(position.symbol, str) or not position.symbol.strip():
            return RiskAssessment(False, "RISK_POSITION_SNAPSHOT_INVALID", server_day=snapshot.server_day,
                                  daily_reset_owner_confirm=bool(scope.daily_reset_owner_confirm))
        if position.magic_number is not None and (isinstance(position.magic_number, bool)
                                                  or not isinstance(position.magic_number, int)):
            return RiskAssessment(False, "RISK_POSITION_SNAPSHOT_INVALID", server_day=snapshot.server_day,
                                  daily_reset_owner_confirm=bool(scope.daily_reset_owner_confirm))
        if position.symbol.upper() in accepted_names:
            matching_positions.append(position)
    own_count = sum(position.magic_number == scope.magic_number for position in matching_positions)
    foreign_count = len(matching_positions) - own_count
    if len(matching_positions) >= MAX_OPEN_POSITIONS_PER_INSTRUMENT:
        return RiskAssessment(False, "INSTRUMENT_POSITION_LIMIT", own_positions_on_symbol=own_count,
                              foreign_positions_on_symbol=foreign_count, server_day=snapshot.server_day,
                              daily_reset_owner_confirm=bool(scope.daily_reset_owner_confirm))

    meta = snapshot.symbol_meta
    if (meta is None or getattr(meta, "symbol", None) != scope.broker_symbol
            or getattr(meta, "metadata_source", None) != "EXCHANGE_VERIFIED"):
        return RiskAssessment(False, "RISK_SYMBOL_METADATA_UNVERIFIED", own_positions_on_symbol=own_count,
                              foreign_positions_on_symbol=foreign_count, server_day=snapshot.server_day,
                              daily_reset_owner_confirm=bool(scope.daily_reset_owner_confirm))
    for field in ("tick_size", "tick_value", "contract_size", "volume_step", "volume_min", "volume_max"):
        if not _finite_number(getattr(meta, field, None), positive=True):
            return RiskAssessment(False, "RISK_SYMBOL_METADATA_INVALID", own_positions_on_symbol=own_count,
                                  foreign_positions_on_symbol=foreign_count, server_day=snapshot.server_day,
                                  daily_reset_owner_confirm=bool(scope.daily_reset_owner_confirm))
    if float(meta.volume_min) > float(meta.volume_max):
        return RiskAssessment(False, "RISK_SYMBOL_METADATA_INVALID", own_positions_on_symbol=own_count,
                              foreign_positions_on_symbol=foreign_count, server_day=snapshot.server_day,
                              daily_reset_owner_confirm=bool(scope.daily_reset_owner_confirm))

    entry = ticket.get("entry")
    stop = ticket.get("stop_loss", ticket.get("sl"))
    if not _finite_number(entry, positive=True) or not _finite_number(stop, positive=True):
        return RiskAssessment(False, "RISK_TICKET_GEOMETRY_INVALID", own_positions_on_symbol=own_count,
                              foreign_positions_on_symbol=foreign_count, server_day=snapshot.server_day,
                              daily_reset_owner_confirm=bool(scope.daily_reset_owner_confirm))
    volume, _, sizing_error = size_position(
        float(entry), float(stop), float(snapshot.demo_equity), MAX_RISK_PER_TRADE_PCT, meta)
    if sizing_error is not None or volume is None:
        return RiskAssessment(False, f"RISK_SIZING_{sizing_error or 'FAILED'}",
                              own_positions_on_symbol=own_count, foreign_positions_on_symbol=foreign_count,
                              server_day=snapshot.server_day,
                              daily_reset_owner_confirm=bool(scope.daily_reset_owner_confirm))
    try:
        # Recompute the final amount in decimal arithmetic. sizing_math.risk deliberately
        # tolerates binary-float noise at volume-step boundaries; this final C14 check must
        # never let that tolerance round risk above the approved ceiling.
        entry_d, stop_d = Decimal(str(entry)), Decimal(str(stop))
        equity_d = Decimal(str(snapshot.demo_equity))
        tick_size_d = Decimal(str(meta.tick_size))
        tick_value_d = Decimal(str(meta.tick_value))
        step_d = Decimal(str(meta.volume_step))
        volume_d = Decimal(str(volume))
        risk_budget_d = equity_d * Decimal("0.5") / Decimal("100")
        loss_per_lot_d = abs(entry_d - stop_d) / tick_size_d * tick_value_d
        if loss_per_lot_d <= 0 or step_d <= 0:
            raise InvalidOperation
        exact_risk_d = volume_d * loss_per_lot_d
        if exact_risk_d > risk_budget_d:
            safe_steps = (risk_budget_d / loss_per_lot_d / step_d).to_integral_value(rounding=ROUND_FLOOR)
            volume_d = safe_steps * step_d
            if volume_d < Decimal(str(meta.volume_min)):
                return RiskAssessment(False, "RISK_SIZING_VOLUME_BELOW_MIN",
                                      own_positions_on_symbol=own_count,
                                      foreign_positions_on_symbol=foreign_count,
                                      server_day=snapshot.server_day,
                                      daily_reset_owner_confirm=bool(scope.daily_reset_owner_confirm))
            exact_risk_d = volume_d * loss_per_lot_d
        volume = float(volume_d)
        risk_amount = float(exact_risk_d)
        risk_pct = float(exact_risk_d / equity_d * Decimal("100"))
    except (InvalidOperation, ZeroDivisionError, ValueError):
        return RiskAssessment(False, "RISK_SIZING_ARITHMETIC_INVALID",
                              own_positions_on_symbol=own_count, foreign_positions_on_symbol=foreign_count,
                              server_day=snapshot.server_day,
                              daily_reset_owner_confirm=bool(scope.daily_reset_owner_confirm))
    if not math.isfinite(risk_pct) or risk_pct > MAX_RISK_PER_TRADE_PCT:
        return RiskAssessment(False, "PER_TRADE_RISK_LIMIT", volume, risk_amount, risk_pct,
                              own_count, foreign_count, snapshot.server_day,
                              bool(scope.daily_reset_owner_confirm))
    if float(snapshot.strategy_daily_loss_pct) + risk_pct > MAX_STRATEGY_DAILY_LOSS_PCT + 1e-9:
        return RiskAssessment(False, "STRATEGY_DAILY_LOSS_LIMIT", volume, risk_amount, risk_pct,
                              own_count, foreign_count, snapshot.server_day,
                              bool(scope.daily_reset_owner_confirm))
    if float(snapshot.account_daily_loss_pct) + risk_pct > MAX_ACCOUNT_DAILY_LOSS_PCT + 1e-9:
        return RiskAssessment(False, "ACCOUNT_DAILY_LOSS_LIMIT", volume, risk_amount, risk_pct,
                              own_count, foreign_count, snapshot.server_day,
                              bool(scope.daily_reset_owner_confirm))
    return RiskAssessment(True, "C14_RISK_CAPS_PASS", volume, risk_amount, risk_pct,
                          own_count, foreign_count, snapshot.server_day,
                          bool(scope.daily_reset_owner_confirm))
