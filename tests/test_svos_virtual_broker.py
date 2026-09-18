"""Tests for svos.virtual_broker -- virtual LONG/SHORT lifecycle, friction, guards (P9/P13)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from svos.friction_profile import (
    FrictionComponent,
    FrictionComponentState,
    FrictionProfile,
    FrictionUnavailableError,
)
from svos.virtual_broker import (
    Side,
    VirtualAccount,
    VirtualBroker,
    VirtualCandle,
    VirtualOrderSpec,
)

T0 = datetime(2026, 9, 1, 8, 0)


def _candle(t0_min: int, o: float, h: float, lo: float, c: float) -> VirtualCandle:
    return VirtualCandle(time=T0 + timedelta(minutes=t0_min), open=o, high=h, low=lo, close=c)


def _account(**overrides) -> VirtualAccount:
    base = dict(
        starting_balance_R=100.0, max_open_positions=5,
        risk_per_trade_R=2.0, daily_loss_limit_R=20.0,
    )
    base.update(overrides)
    return VirtualAccount(**base)


def _friction(slippage_R: float = 0.0, spread_R: float = 0.0,
              commission_R: float = 0.0) -> FrictionProfile:
    return FrictionProfile(
        spread=FrictionComponent(FrictionComponentState.MODELED, spread_R),
        commission=FrictionComponent(FrictionComponentState.MODELED, commission_R),
        slippage=FrictionComponent(FrictionComponentState.MODELED, slippage_R),
    )


def test_long_partial_then_runner():
    broker = VirtualBroker(_friction(slippage_R=0.05), _account())
    broker.submit_market(VirtualOrderSpec(
        symbol="EURUSD", side=Side.LONG, stop_loss=0.9980,
        partial_target=1.0010, partial_pct=0.5, runner_target=1.0040,
    ))
    broker.on_candle(_candle(0, 1.0000, 1.0006, 0.9990, 1.0003))  # fill only
    broker.on_candle(_candle(15, 1.0003, 1.0015, 1.0001, 1.0012))  # partial
    broker.on_candle(_candle(30, 1.0012, 1.0042, 1.0010, 1.0038))  # runner

    trades = broker.ledger.trades
    assert len(trades) == 2
    assert trades[0].exit_reason == "PARTIAL_TARGET"
    assert trades[0].gross_R == pytest.approx(0.5)
    assert trades[1].exit_reason == "RUNNER_TARGET"
    assert trades[1].gross_R == pytest.approx(2.0)
    # friction: 0.05R per full position, proportional per leg
    assert trades[0].friction_R == pytest.approx(0.025)
    assert trades[1].friction_R == pytest.approx(0.025)
    # equity = 100 + 0.5*0.475 + 0.5*1.975
    assert broker.equity_R == pytest.approx(100 + 0.5 * 0.475 + 0.5 * 1.975)
    assert not broker.open_positions


def test_short_partial_then_runner():
    broker = VirtualBroker(_friction(), _account())
    broker.submit_market(VirtualOrderSpec(
        symbol="EURUSD", side=Side.SHORT, stop_loss=1.0020,
        partial_target=0.9990, partial_pct=0.5, runner_target=0.9960,
    ))
    broker.on_candle(_candle(0, 1.0000, 1.0002, 0.9992, 0.9995))  # fill only
    broker.on_candle(_candle(15, 0.9995, 0.9996, 0.9988, 0.9991))  # partial
    broker.on_candle(_candle(30, 0.9991, 0.9992, 0.9958, 0.9961))  # runner

    trades = broker.ledger.trades
    assert len(trades) == 2
    assert trades[0].gross_R == pytest.approx(0.5)
    assert trades[1].gross_R == pytest.approx(2.0)


def test_full_stop_loss():
    broker = VirtualBroker(_friction(), _account())
    broker.submit_market(VirtualOrderSpec(
        symbol="EURUSD", side=Side.LONG, stop_loss=0.9980,
    ))
    broker.on_candle(_candle(0, 1.0000, 1.0005, 0.9975, 0.9990))  # fill + SL same bar

    trades = broker.ledger.trades
    assert len(trades) == 1
    assert trades[0].exit_reason == "STOP_LOSS"
    assert trades[0].gross_R == pytest.approx(-1.0)


def test_session_exit():
    broker = VirtualBroker(_friction(), _account())
    session_end = T0 + timedelta(minutes=30)
    broker.submit_market(VirtualOrderSpec(
        symbol="EURUSD", side=Side.LONG, stop_loss=0.9980, session_exit_time=session_end,
    ))
    broker.on_candle(_candle(0, 1.0000, 1.0004, 0.9990, 1.0002))
    broker.on_candle(_candle(30, 1.0002, 1.0010, 0.9995, 1.0005))  # >= session end

    trades = broker.ledger.trades
    assert len(trades) == 1
    assert trades[0].exit_reason == "SESSION_EXIT"
    assert trades[0].gross_R == pytest.approx(0.25)


def test_max_open_positions_enforced_at_fill():
    broker = VirtualBroker(_friction(), _account(max_open_positions=1))
    o1 = broker.submit_market(VirtualOrderSpec(symbol="EURUSD", side=Side.LONG, stop_loss=0.9980))
    o2 = broker.submit_market(VirtualOrderSpec(symbol="EURUSD", side=Side.LONG, stop_loss=0.9980))
    assert o1.status.value == "PENDING" and o2.status.value == "PENDING"
    broker.on_candle(_candle(0, 1.0000, 1.0003, 0.9990, 1.0001))
    assert len(broker.ledger.fills) == 1
    assert len(broker.open_positions) == 1


def test_risk_per_trade_guard():
    broker = VirtualBroker(_friction(), _account(risk_per_trade_R=1.0))
    order = broker.submit_market(VirtualOrderSpec(
        symbol="EURUSD", side=Side.LONG, stop_loss=0.9980, risk_amount_R=2.0,
    ))
    assert order.status.value == "REJECTED"
    assert order.reason == "RISK_PER_TRADE_EXCEEDED"


def test_unavailable_friction_refuses_to_fill():
    profile = FrictionProfile(
        spread=FrictionComponent(FrictionComponentState.MODELED, 0.0),
        commission=FrictionComponent(FrictionComponentState.UNAVAILABLE, None),
        slippage=FrictionComponent(FrictionComponentState.MODELED, 0.0),
    )
    broker = VirtualBroker(profile, _account())
    broker.submit_market(VirtualOrderSpec(symbol="EURUSD", side=Side.LONG, stop_loss=0.9980))
    with pytest.raises(FrictionUnavailableError):
        broker.on_candle(_candle(0, 1.0000, 1.0003, 0.9990, 1.0001))
    assert len(broker.ledger.fills) == 0


def test_unavailable_never_converts_to_zero():
    profile = FrictionProfile(
        spread=FrictionComponent(FrictionComponentState.MODELED, 0.0),
        commission=FrictionComponent(FrictionComponentState.UNAVAILABLE, None),
        slippage=FrictionComponent(FrictionComponentState.MODELED, 0.0),
    )
    with pytest.raises(FrictionUnavailableError):
        profile.total_cost_R()
