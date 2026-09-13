"""AG_VANTAGE_MT5_CRYPTO_VENUE_V1 (2026-09-13).

Proves the existing manual Vantage Demo MT5 execution bridge is genuinely asset-class
agnostic -- that BTCUSD/ETHUSD (canonical BTCUSDT/ETHUSDT) flow through the SAME chain,
with the SAME gates and the SAME reason codes, as EURUSD/GBPUSD do today -- and that the
crypto contract shape (contract_size=1, tick_size=0.01, 1 lot = 1 coin) is handled with
no FX assumption anywhere.

Nothing here submits a broker order: `execution.mt5_gateway.order_open` is monkeypatched
in every test that reaches it, exactly as tests/test_execution_executor.py already does.
The only tests that touch the real terminal are marked `live_mt5` and are strictly
read-only (symbol_info / symbol_info_tick).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import assistant.commands as commands_module
from execution import executor
from execution.models import ExecutionSource, OrderSendResult, TradeCommand
from mt5 import symbol_resolver as mt5_symbol_resolver
from mt5.broker_symbol_resolver import resolve_broker_symbol
from trade_management.models import (
    GEOMETRY_VALID,
    OVERALL_READY,
    SIZING_READY,
    SymbolMeta as TmSymbolMeta,
)
from trade_management.pretrade_engine import evaluate_trade_management
from trade_management.models import TradeManagementRequest

# Live-captured from the connected Vantage Markets Demo account (2026-09-13, read-only
# symbol_info()): BTCUSD/ETHUSD really do report contract_size 1.0, tick_size/point 0.01,
# tick_value 0.01, volume_min/step 0.01, digits 2 -- i.e. nothing like FX's
# contract_size=100000 / tick_size=1e-05. These fixtures encode that real shape.
_CRYPTO_TICK_SIZE = 0.01
_CRYPTO_TICK_VALUE = 0.01
_CRYPTO_CONTRACT_SIZE = 1.0

VANTAGE_CRYPTO_SYMBOLS = ("BTCUSD", "ETHUSD")
CANONICAL_TO_BROKER = {"BTCUSDT": "BTCUSD", "ETHUSDT": "ETHUSD"}


def _crypto_symbol_info(symbol: str = "BTCUSD", **overrides):
    fields = dict(
        name=symbol, visible=True, trade_tick_size=_CRYPTO_TICK_SIZE,
        trade_tick_value=_CRYPTO_TICK_VALUE, trade_contract_size=_CRYPTO_CONTRACT_SIZE,
        volume_min=0.01, volume_max=100.0, volume_step=0.01, digits=2, point=0.01,
        trade_stops_level=0, trade_freeze_level=0,
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _crypto_tm_symbol_meta() -> TmSymbolMeta:
    return TmSymbolMeta(
        symbol="BTCUSD", tick_size=_CRYPTO_TICK_SIZE, tick_value=_CRYPTO_TICK_VALUE,
        contract_size=_CRYPTO_CONTRACT_SIZE, volume_min=0.01, volume_max=100.0,
        volume_step=0.01, digits=2, point=0.01,
    )


# --- 1. Canonical -> broker symbol resolution (config-driven, already generic) --------

@pytest.mark.parametrize("canonical,broker_symbol", sorted(CANONICAL_TO_BROKER.items()))
def test_canonical_crypto_symbols_resolve_to_the_vantage_broker_names(canonical, broker_symbol):
    assert resolve_broker_symbol(canonical, "VANTAGE") == broker_symbol


# --- 2. get_symbol_meta handles the crypto contract shape with no FX assumption -------

def test_get_symbol_meta_accepts_a_crypto_shaped_contract(monkeypatch):
    """contract_size=1 / tick_size=0.01 must pass through untouched -- get_symbol_meta
    must not assume FX's 100000 contract size or 1e-05 tick size anywhere."""
    monkeypatch.setattr(mt5_symbol_resolver.mt5, "symbol_info", lambda s: _crypto_symbol_info(s))

    meta = mt5_symbol_resolver.get_symbol_meta("BTCUSD")

    assert meta.symbol == "BTCUSD"
    assert meta.contract_size == _CRYPTO_CONTRACT_SIZE
    assert meta.tick_size == _CRYPTO_TICK_SIZE
    assert meta.tick_value == _CRYPTO_TICK_VALUE
    assert meta.volume_step == 0.01
    assert meta.digits == 2
    assert meta.point == 0.01
    assert meta.metadata_source == mt5_symbol_resolver.METADATA_SOURCE_EXCHANGE_VERIFIED


def test_get_symbol_meta_still_fails_closed_on_degenerate_crypto_metadata(monkeypatch):
    monkeypatch.setattr(
        mt5_symbol_resolver.mt5, "symbol_info",
        lambda s: _crypto_symbol_info(s, trade_contract_size=0.0),
    )
    monkeypatch.setattr(mt5_symbol_resolver.mt5, "last_error", lambda: (0, "ok"))

    with pytest.raises(mt5_symbol_resolver.SymbolMetaError):
        mt5_symbol_resolver.get_symbol_meta("BTCUSD")


def test_invisible_crypto_symbol_is_selected_into_market_watch(monkeypatch):
    """BTCUSD/ETHUSD are not in the Vantage Demo terminal's default Market Watch (FX is)
    -- the existing select-once path must therefore actually run for crypto."""
    selected = []
    infos = iter([_crypto_symbol_info("BTCUSD", visible=False), _crypto_symbol_info("BTCUSD")])
    monkeypatch.setattr(mt5_symbol_resolver.mt5, "symbol_info", lambda s: next(infos))
    monkeypatch.setattr(
        mt5_symbol_resolver.mt5, "symbol_select",
        lambda s, enable: (selected.append((s, enable)), True)[1],
    )

    meta = mt5_symbol_resolver.get_symbol_meta("BTCUSD")

    assert selected == [("BTCUSD", True)]
    assert meta.symbol == "BTCUSD"


# --- 3. Sizing / geometry on the crypto contract shape -------------------------------

def test_sizing_on_crypto_contract_shape_is_tick_value_based_not_pip_based():
    """1 lot BTCUSD = 1 BTC: tick_value/tick_size = 1.0 USD per 1.0 price unit per lot.
    A 1000-point ($1000) stop with a $100 risk budget must therefore size 0.1 lots -- a
    hardcoded FX pip-value formula would produce a wildly different number."""
    request = TradeManagementRequest(
        symbol="BTCUSD", direction="LONG", entry_price=77300.00, stop_loss=76300.00,
        take_profit=79300.00, risk_percent=1.0, equity=10000.0,
        symbol_meta=_crypto_tm_symbol_meta(),
    )

    result = evaluate_trade_management(request)

    assert result.overall_status == OVERALL_READY
    assert result.geometry.status == GEOMETRY_VALID
    assert result.geometry.stop_distance_price == pytest.approx(1000.0)
    assert result.geometry.stop_distance_points == pytest.approx(100000.0)
    assert result.sizing.status == SIZING_READY
    assert result.sizing.loss_per_lot == pytest.approx(1000.0)
    assert result.sizing.normalized_volume == pytest.approx(0.1)
    # Floor-only normalization must still never exceed the requested risk budget.
    assert result.sizing.actual_risk_percent <= 1.0


def test_crypto_sizing_below_broker_min_volume_fails_closed_like_fx():
    """A stop so wide that the risk budget cannot buy volume_min must be SIZE/VOLUME
    unavailable, never silently forced up to the minimum -- same rule FX already has."""
    request = TradeManagementRequest(
        symbol="BTCUSD", direction="LONG", entry_price=77300.00, stop_loss=27300.00,
        risk_percent=0.1, equity=1000.0, symbol_meta=_crypto_tm_symbol_meta(),
    )

    result = evaluate_trade_management(request)

    assert result.sizing.status != SIZING_READY
    assert result.sizing.normalized_volume is None


# --- 4. get_tick zero-quote guard (a crypto-first failure mode) ----------------------

def test_get_tick_rejects_a_zero_quote_from_a_freshly_selected_symbol(monkeypatch):
    """Observed live: right after a symbol is selected into Market Watch, MT5 can return
    bid=0.0/ask=0.0 with a non-zero tick time. That is 'no quote yet', not a price."""
    from mt5 import market_data

    monkeypatch.setattr(market_data, "_require_connected", lambda: None)
    monkeypatch.setattr(market_data, "_require_symbol", lambda symbol: None)
    monkeypatch.setattr(
        market_data.mt5, "symbol_info_tick",
        lambda s: SimpleNamespace(time=1789288932, bid=0.0, ask=0.0),
    )

    with pytest.raises(market_data.MarketDataError) as exc_info:
        market_data.get_tick("BTCUSD")

    assert exc_info.value.reason_code == "DATA_MISSING"


def test_get_tick_accepts_a_normal_crypto_quote(monkeypatch):
    from mt5 import market_data

    monkeypatch.setattr(market_data, "_require_connected", lambda: None)
    monkeypatch.setattr(market_data, "_require_symbol", lambda symbol: None)
    monkeypatch.setattr(market_data, "_broker_offset_hours", lambda symbol: 0)
    monkeypatch.setattr(
        market_data.mt5, "symbol_info_tick",
        lambda s: SimpleNamespace(time=1789288932, bid=77292.86, ask=77309.92),
    )
    monkeypatch.setattr(market_data.mt5, "symbol_info", lambda s: SimpleNamespace(spread=1706))

    tick = market_data.get_tick("BTCUSD")

    assert tick.bid == pytest.approx(77292.86)
    assert tick.ask == pytest.approx(77309.92)


# --- 5. execute_command() gate parity: crypto is gated EXACTLY like FX ---------------

def _crypto_command(command_id="cmd-crypto-1", symbol="BTCUSD", **overrides):
    fields = dict(
        command_id=command_id, action="OPEN", symbol=symbol,
        source=ExecutionSource.USER_EXPLICIT_ORDER, side="BUY", order_type="MARKET",
        volume=0.01, entry=77300.00, sl=76300.00, tp=79300.00,
        comment="AG web | FRONTEND_MANUAL",
    )
    fields.update(overrides)
    return TradeCommand(**fields)


def _fx_command(command_id="cmd-fx-1"):
    return TradeCommand(
        command_id=command_id, action="OPEN", symbol="EURUSD",
        source=ExecutionSource.USER_EXPLICIT_ORDER, side="BUY", order_type="MARKET",
        volume=0.01, entry=1.15997, sl=1.15797, tp=1.16397,
        comment="AG web | FRONTEND_MANUAL",
    )


@pytest.mark.parametrize("symbol", VANTAGE_CRYPTO_SYMBOLS)
def test_unconfirmed_crypto_command_is_rejected_before_any_broker_call(monkeypatch, symbol):
    """The exact gate the FX bridge's own validation relied on
    (docs/status/AG_WEB_VANTAGE_DEMO_EXECUTION_BRIDGE_V1.md: "Non-confirmed execution
    bridge check: rejected with EXECUTION_NOT_AUTHORIZED before any broker mutation")."""
    calls = []
    monkeypatch.setattr(executor.mt5_gateway, "order_open", lambda **kw: calls.append(kw))

    report = commands_module.execute_command(_crypto_command(symbol=symbol), user_confirmed=False)

    assert report.status == "REJECTED"
    assert report.gate_reason_code == "EXECUTION_NOT_AUTHORIZED"
    assert calls == []


def test_crypto_and_fx_share_the_same_unconfirmed_rejection_code():
    fx = commands_module.execute_command(_fx_command(), user_confirmed=False)
    crypto = commands_module.execute_command(_crypto_command(), user_confirmed=False)
    assert crypto.gate_reason_code == fx.gate_reason_code == "EXECUTION_NOT_AUTHORIZED"


@pytest.mark.parametrize("symbol", VANTAGE_CRYPTO_SYMBOLS)
def test_confirmed_crypto_command_still_passes_through_geometry_and_the_gateway(monkeypatch, symbol):
    """A confirmed crypto command must reach mt5_gateway.order_open with the crypto
    symbol and crypto volume intact -- i.e. nothing between execute_command() and the
    gateway silently rewrites or rejects a non-FX symbol."""
    monkeypatch.setattr(executor.journal, "has_executed", lambda command_id: False)
    monkeypatch.setattr(executor.journal, "claim_command", lambda command_id: True)
    monkeypatch.setattr(executor.journal, "record_event", lambda *a, **kw: None)
    monkeypatch.setattr(executor, "get_positions", lambda **kw: [])
    monkeypatch.setattr(executor, "deals_for_symbol", lambda s, **kw: [])
    monkeypatch.setattr(executor, "get_symbol_meta", lambda s: _crypto_tm_symbol_meta())
    sent = {}

    def _fake_order_open(**kwargs):
        sent.update(kwargs)
        return OrderSendResult(
            status="REJECTED", reason_code="DRY_RUN", symbol=kwargs["symbol"],
            side=kwargs["side"], requested_volume=kwargs["volume"],
        )

    monkeypatch.setattr(executor.mt5_gateway, "order_open", _fake_order_open)

    report = commands_module.execute_command(
        _crypto_command(command_id=f"cmd-{symbol}", symbol=symbol), user_confirmed=True,
    )

    assert sent["symbol"] == symbol
    assert sent["volume"] == pytest.approx(0.01)
    assert sent["sl"] == pytest.approx(76300.00)
    # The gateway's own fail-closed default (config not TRADING / sends disallowed) is
    # what stops the order here -- not a crypto-specific rule.
    assert report.gate_reason_code == "DRY_RUN"


def test_crypto_geometry_is_rejected_by_the_same_rule_as_fx(monkeypatch):
    """SL on the wrong side of entry must be rejected for crypto with the same
    geometry reason code FX gets -- no crypto-specific leniency."""
    monkeypatch.setattr(executor.journal, "has_executed", lambda command_id: False)
    monkeypatch.setattr(executor.journal, "claim_command", lambda command_id: True)
    monkeypatch.setattr(executor.journal, "record_event", lambda *a, **kw: None)
    calls = []
    monkeypatch.setattr(executor.mt5_gateway, "order_open", lambda **kw: calls.append(kw))

    report = commands_module.execute_command(
        _crypto_command(command_id="cmd-bad-geometry", sl=78300.00), user_confirmed=True,
    )

    assert report.status == "REJECTED"
    assert report.gate_reason_code == "INVALID_LONG_STOP"
    assert calls == []


def test_gateway_account_guard_is_not_bypassed_for_crypto():
    """mt5_gateway.order_open's account authorization is symbol-independent by
    construction: the demo/identity check takes no symbol argument, so there is no
    per-symbol branch a crypto order could take around it."""
    import inspect

    from execution import mt5_gateway

    source = inspect.getsource(mt5_gateway)
    assert "_account_authorized_for_send()" in source
    assert inspect.signature(mt5_gateway._account_authorized_for_send).parameters == {}
    # and the guard it delegates to is likewise symbol-independent
    from mt5.account_guard import verify_configured_account

    assert inspect.signature(verify_configured_account).parameters == {}


# --- 6. Live, strictly read-only verification against the real terminal --------------

@pytest.mark.live_mt5
@pytest.mark.parametrize("canonical,broker_symbol", sorted(CANONICAL_TO_BROKER.items()))
def test_live_vantage_crypto_symbol_is_tradable_and_quotes(canonical, broker_symbol):
    """Read-only: resolves the canonical symbol, reads its broker contract metadata and
    a current quote. Submits nothing. Skips honestly where no terminal is available."""
    import MetaTrader5 as mt5

    if not mt5.initialize():
        pytest.skip("MT5_TERMINAL_UNAVAILABLE: mt5.initialize() failed")
    try:
        assert resolve_broker_symbol(canonical, "VANTAGE") == broker_symbol
        info = mt5.symbol_info(broker_symbol)
        if info is None:
            pytest.skip(f"{broker_symbol} not offered by the connected account")
        if not info.visible:
            assert mt5.symbol_select(broker_symbol, True)
        meta = mt5_symbol_resolver.get_symbol_meta(broker_symbol)
        assert meta.tick_size > 0 and meta.tick_value > 0 and meta.contract_size > 0
        assert meta.volume_min > 0 and meta.volume_step > 0
        # SYMBOL_TRADE_MODE_FULL == 4
        assert mt5.symbol_info(broker_symbol).trade_mode == 4
    finally:
        mt5.shutdown()
