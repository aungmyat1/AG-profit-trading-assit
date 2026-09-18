"""VirtualBroker (P9/P13) -- an isolated broker simulator with ZERO reach to MT5.

Consumes real (already-closed) market candles but creates NO broker mutation. The hard
invariant `MT5_ORDER_SEND_REACHABLE_FROM_VIRTUAL_BROKER = false` is structural: this
module imports nothing from src/execution/, src/mt5/, or the MetaTrader5 package, and
never references order_send/order_check (statically verified by
tests/test_svos_mt5_isolation.py).

Supported lifecycle (market-style virtual entry):
    LONG / SHORT -> fill at next bar open + admitted slippage
    -> SL | partial target (-> breakeven transition) | runner target | session/time exit

Intrabar policy is explicit and conservative by default: when a single bar touches both
the stop and a target, the stop is assumed to hit first (worst case). Position sizing,
risk_R, spread/commission/slippage (via svos.friction_profile.FrictionProfile), realized_R
and net_R are all modeled in R units; the virtual account has no currency and no
connection to any MT5 balance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Sequence, Tuple

from .friction_profile import FrictionProfile

_SIDE_SIGN = {"LONG": 1.0, "SHORT": -1.0}


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    REJECTED = "REJECTED"


class PositionStatus(str, Enum):
    OPEN = "OPEN"
    PARTIAL = "PARTIAL"      # partial taken, stop moved to breakeven
    CLOSED = "CLOSED"


@dataclass(frozen=True)
class VirtualCandle:
    time: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class VirtualOrderSpec:
    symbol: str
    side: Side
    stop_loss: float
    size: float = 1.0
    partial_target: Optional[float] = None
    partial_pct: float = 0.5
    runner_target: Optional[float] = None
    session_exit_time: Optional[datetime] = None
    risk_amount_R: float = 1.0


@dataclass(frozen=True)
class VirtualOrder:
    order_id: str
    symbol: str
    side: Side
    size: float
    stop_loss: float
    partial_target: Optional[float]
    partial_pct: float
    runner_target: Optional[float]
    session_exit_time: Optional[datetime]
    risk_amount_R: float
    status: OrderStatus = OrderStatus.PENDING
    reason: str = ""


@dataclass(frozen=True)
class VirtualFill:
    fill_id: str
    order_id: str
    timestamp: datetime
    price: float
    size: float
    slippage_R: float


@dataclass
class VirtualPosition:
    position_id: str
    order_id: str
    symbol: str
    side: Side
    size: float
    entry_price: float
    initial_stop: float       # original stop distance -> R denominator (never moves)
    stop_loss: float          # current stop (moves to breakeven after partial)
    partial_target: Optional[float]
    partial_pct: float
    runner_target: Optional[float]
    session_exit_time: Optional[datetime]
    risk_amount_R: float
    status: PositionStatus = PositionStatus.OPEN
    partialed: bool = False
    events: List[dict] = field(default_factory=list)


@dataclass(frozen=True)
class VirtualTrade:
    trade_id: str
    position_id: str
    order_id: str
    symbol: str
    side: Side
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    exit_reason: str
    size_fraction: float
    gross_R: float
    friction_R: float
    net_R: float


@dataclass(frozen=True)
class VirtualAccount:
    starting_balance_R: float
    max_open_positions: int
    risk_per_trade_R: float
    daily_loss_limit_R: float
    realized_pnl_R: float = 0.0
    open_risk_R: float = 0.0
    peak_equity_R: float = 0.0

    @property
    def equity_R(self) -> float:
        return self.starting_balance_R + self.realized_pnl_R

    @property
    def drawdown_R(self) -> float:
        return max(0.0, self.peak_equity_R - self.equity_R)


class VirtualBrokerLedger:
    """Append-only ledger of fills and trades. Immutable from the outside: `record_*`
    appends a frozen dataclass and never mutates an existing row."""

    def __init__(self) -> None:
        self._fills: List[VirtualFill] = []
        self._trades: List[VirtualTrade] = []

    @property
    def fills(self) -> Tuple[VirtualFill, ...]:
        return tuple(self._fills)

    @property
    def trades(self) -> Tuple[VirtualTrade, ...]:
        return tuple(self._trades)

    def record_fill(self, fill: VirtualFill) -> None:
        self._fills.append(fill)

    def record_trade(self, trade: VirtualTrade) -> None:
        self._trades.append(trade)

    def to_dict(self) -> dict:
        return {
            "fills": [f.__dict__ for f in self._fills],
            "trades": [t.__dict__ for t in self._trades],
        }


def _r_multiple(entry: float, initial_stop: float, price: float, side: Side) -> float:
    risk = abs(entry - initial_stop)
    if risk <= 0:
        raise ValueError("zero stop distance -- cannot compute R")
    return _SIDE_SIGN[side.value] * (price - entry) / risk


class VirtualBroker:
    def __init__(
        self,
        friction: FrictionProfile,
        account: VirtualAccount,
        intrabar_policy: str = "CONSERVATIVE_STOP_FIRST",
    ) -> None:
        if intrabar_policy != "CONSERVATIVE_STOP_FIRST":
            raise ValueError(f"unsupported intrabar policy {intrabar_policy!r}")
        self._friction = friction
        self._account = account
        self._ledger = VirtualBrokerLedger()
        self._orders: List[VirtualOrder] = []
        self._positions: List[VirtualPosition] = []
        self._open_positions: List[VirtualPosition] = []
        self._next_ids = {"order": 0, "fill": 0, "trade": 0, "position": 0}
        self._today: Optional[str] = None
        self._daily_realized_R: float = 0.0

    # -- read views ----------------------------------------------------------
    @property
    def ledger(self) -> VirtualBrokerLedger:
        return self._ledger

    @property
    def open_positions(self) -> Tuple[VirtualPosition, ...]:
        return tuple(self._open_positions)

    @property
    def equity_R(self) -> float:
        return self.account_snapshot().equity_R

    @property
    def pending_orders(self) -> Tuple[VirtualOrder, ...]:
        return tuple(o for o in self._orders if o.status is OrderStatus.PENDING)

    def account_snapshot(self) -> VirtualAccount:
        realized = sum(t.net_R * t.size_fraction for t in self._ledger.trades)
        peak = max(self._account.peak_equity_R, self._account.starting_balance_R + realized)
        open_risk = sum(p.risk_amount_R for p in self._open_positions)
        return VirtualAccount(
            starting_balance_R=self._account.starting_balance_R,
            max_open_positions=self._account.max_open_positions,
            risk_per_trade_R=self._account.risk_per_trade_R,
            daily_loss_limit_R=self._account.daily_loss_limit_R,
            realized_pnl_R=realized,
            open_risk_R=open_risk,
            peak_equity_R=peak,
        )

    # -- order entry ---------------------------------------------------------
    def submit_market(self, spec: VirtualOrderSpec) -> VirtualOrder:
        self._next_ids["order"] += 1
        order = VirtualOrder(
            order_id=f"VO-{self._next_ids['order']:06d}",
            symbol=spec.symbol, side=spec.side, size=spec.size,
            stop_loss=spec.stop_loss, partial_target=spec.partial_target,
            partial_pct=spec.partial_pct, runner_target=spec.runner_target,
            session_exit_time=spec.session_exit_time, risk_amount_R=spec.risk_amount_R,
        )

        if spec.side is Side.LONG and spec.partial_target is not None and spec.partial_target <= spec.stop_loss:
            return self._reject(order, "PARTIAL_TARGET_NOT_BEYOND_STOP")
        if spec.side is Side.SHORT and spec.partial_target is not None and spec.partial_target >= spec.stop_loss:
            return self._reject(order, "PARTIAL_TARGET_NOT_BEYOND_STOP")
        if spec.risk_amount_R > self._account.risk_per_trade_R:
            return self._reject(order, "RISK_PER_TRADE_EXCEEDED")
        if len(self._open_positions) >= self._account.max_open_positions:
            return self._reject(order, "MAX_OPEN_POSITIONS")
        if self._daily_realized_R <= -self._account.daily_loss_limit_R:
            return self._reject(order, "DAILY_LOSS_LIMIT")

        self._orders.append(order)
        return order

    def _reject(self, order: VirtualOrder, reason: str) -> VirtualOrder:
        rejected = VirtualOrder(
            order_id=order.order_id, symbol=order.symbol, side=order.side, size=order.size,
            stop_loss=order.stop_loss, partial_target=order.partial_target,
            partial_pct=order.partial_pct, runner_target=order.runner_target,
            session_exit_time=order.session_exit_time, risk_amount_R=order.risk_amount_R,
            status=OrderStatus.REJECTED, reason=reason,
        )
        self._orders.append(rejected)
        return rejected

    # -- bar processing ------------------------------------------------------
    def on_candle(self, candle: VirtualCandle) -> Tuple[VirtualFill, ...]:
        if not self._friction.admitted():
            from .friction_profile import FrictionUnavailableError

            raise FrictionUnavailableError("broker refuses to fill under a non-admitted friction profile")

        self._roll_daily(candle.time)
        new_fills: List[VirtualFill] = []

        # 1) fill pending orders at this bar's open + admitted slippage
        for order in list(self._orders):
            if order.status is not OrderStatus.PENDING:
                continue
            if len(self._open_positions) >= self._account.max_open_positions:
                self._mark_rejected(order, "MAX_OPEN_POSITIONS")
                continue
            fill_price = candle.open
            slippage_R = self._friction.slippage.value_R or 0.0
            self._next_ids["fill"] += 1
            fill = VirtualFill(
                fill_id=f"VF-{self._next_ids['fill']:06d}",
                order_id=order.order_id,
                timestamp=candle.time,
                price=fill_price,
                size=order.size,
                slippage_R=slippage_R,
            )
            self._ledger.record_fill(fill)
            new_fills.append(fill)
            order = self._mark_filled(order)
            self._open_positions.append(self._new_position(order, fill))

        # 2) manage open positions against this bar (fill happened at open; intrabar uses high/low)
        for position in list(self._open_positions):
            self._manage(position, candle)

        return tuple(new_fills)

    def _roll_daily(self, now: datetime) -> None:
        day = now.date().isoformat()
        if self._today is None:
            self._today = day
        elif day != self._today:
            self._today = day
            self._daily_realized_R = 0.0

    def _mark_filled(self, order: VirtualOrder) -> VirtualOrder:
        for i, o in enumerate(self._orders):
            if o.order_id == order.order_id:
                self._orders[i] = VirtualOrder(
                    order_id=o.order_id, symbol=o.symbol, side=o.side, size=o.size,
                    stop_loss=o.stop_loss, partial_target=o.partial_target,
                    partial_pct=o.partial_pct, runner_target=o.runner_target,
                    session_exit_time=o.session_exit_time, risk_amount_R=o.risk_amount_R,
                    status=OrderStatus.FILLED, reason=o.reason,
                )
                return self._orders[i]
        return order

    def _mark_rejected(self, order: VirtualOrder, reason: str) -> None:
        for i, o in enumerate(self._orders):
            if o.order_id == order.order_id:
                self._orders[i] = VirtualOrder(
                    order_id=o.order_id, symbol=o.symbol, side=o.side, size=o.size,
                    stop_loss=o.stop_loss, partial_target=o.partial_target,
                    partial_pct=o.partial_pct, runner_target=o.runner_target,
                    session_exit_time=o.session_exit_time, risk_amount_R=o.risk_amount_R,
                    status=OrderStatus.REJECTED, reason=reason,
                )
                return

    def _new_position(self, order: VirtualOrder, fill: VirtualFill) -> VirtualPosition:
        partial_target = order.partial_target
        # Fail closed to "no partial" when the target is on the wrong side of the fill.
        if order.side is Side.LONG and partial_target is not None and partial_target <= fill.price:
            partial_target = None
        if order.side is Side.SHORT and partial_target is not None and partial_target >= fill.price:
            partial_target = None
        self._next_ids["position"] += 1
        return VirtualPosition(
            position_id=f"VP-{self._next_ids['position']:06d}",
            order_id=order.order_id,
            symbol=order.symbol, side=order.side, size=fill.size,
            entry_price=fill.price, initial_stop=order.stop_loss, stop_loss=order.stop_loss,
            partial_target=partial_target, partial_pct=order.partial_pct,
            runner_target=order.runner_target, session_exit_time=order.session_exit_time,
            risk_amount_R=order.risk_amount_R,
        )

    def _friction_R(self) -> float:
        return self._friction.total_cost_R()

    def _manage(self, position: VirtualPosition, candle: VirtualCandle) -> None:
        is_long = position.side is Side.LONG

        def hit_low(price: float) -> bool:
            return candle.low <= price

        def hit_high(price: float) -> bool:
            return candle.high >= price

        sl_hit = hit_low(position.stop_loss) if is_long else hit_high(position.stop_loss)

        # partial leg first (if configured and not yet taken)
        if position.partial_target is not None and not position.partialed:
            pt_hit = hit_high(position.partial_target) if is_long else hit_low(position.partial_target)
            if sl_hit and pt_hit:
                # conservative intrabar policy: stop assumed first -> full stop-out
                self._book_trade(position, candle.time, position.stop_loss, "STOP_FIRST_SAME_BAR", 1.0)
                self._close_position(position)
                return
            if pt_hit:
                self._book_trade(position, candle.time, position.partial_target, "PARTIAL_TARGET", position.partial_pct)
                position.partialed = True
                position.status = PositionStatus.PARTIAL
                position.events.append({"time": str(candle.time), "event": "PARTIAL_TARGET"})
                position.stop_loss = position.entry_price  # breakeven transition
                sl_hit = hit_low(position.stop_loss) if is_long else hit_high(position.stop_loss)

        remaining = 1.0 - position.partial_pct if position.partialed else 1.0

        if sl_hit:
            self._book_trade(position, candle.time, position.stop_loss, "STOP_LOSS", remaining)
            self._close_position(position)
            return

        if position.runner_target is not None:
            rt_hit = hit_high(position.runner_target) if is_long else hit_low(position.runner_target)
            if rt_hit:
                self._book_trade(position, candle.time, position.runner_target, "RUNNER_TARGET", remaining)
                self._close_position(position)
                return

        if position.session_exit_time is not None and candle.time >= position.session_exit_time:
            self._book_trade(position, candle.time, candle.close, "SESSION_EXIT", remaining)
            self._close_position(position)

    def _book_trade(
        self, position: VirtualPosition, exit_time: datetime, exit_price: float,
        reason: str, size_fraction: float,
    ) -> None:
        gross_R = _r_multiple(position.entry_price, position.initial_stop, exit_price, position.side)
        friction_R = self._friction_R() * size_fraction
        net_R = gross_R - friction_R
        self._next_ids["trade"] += 1
        position.events.append({"time": str(exit_time), "event": reason, "exit_price": exit_price})
        entry_time = self._entry_time(position)
        self._ledger.record_trade(
            VirtualTrade(
                trade_id=f"VT-{self._next_ids['trade']:06d}",
                position_id=position.position_id,
                order_id=position.order_id,
                symbol=position.symbol, side=position.side,
                entry_time=entry_time,
                entry_price=position.entry_price,
                exit_time=exit_time, exit_price=exit_price, exit_reason=reason,
                size_fraction=size_fraction,
                gross_R=gross_R, friction_R=friction_R, net_R=net_R,
            )
        )

    @staticmethod
    def _entry_time(position: VirtualPosition) -> datetime:
        return position.events[0]["time"] if position.events else None

    def _close_position(self, position: VirtualPosition) -> None:
        position.status = PositionStatus.CLOSED
        self._open_positions.remove(position)
        self._daily_realized_R += sum(
            t.net_R for t in self._ledger.trades if t.position_id == position.position_id
        )

    # -- checkpoint (restart-safe) -------------------------------------------
    def to_checkpoint(self) -> dict:
        return {
            "account": {
                "starting_balance_R": self._account.starting_balance_R,
                "max_open_positions": self._account.max_open_positions,
                "risk_per_trade_R": self._account.risk_per_trade_R,
                "daily_loss_limit_R": self._account.daily_loss_limit_R,
                "peak_equity_R": self._account.peak_equity_R,
            },
            "orders": [o.__dict__ for o in self._orders],
            "positions": [p.__dict__ for p in self._open_positions],
            "ledger": self._ledger.to_dict(),
            "next_ids": dict(self._next_ids),
            "daily_realized_R": self._daily_realized_R,
        }
