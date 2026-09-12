"""Broker-side close notification (stop-loss hit and friends).

Before this, trade_management.manager.run_cycle_for_ticket() detected a vanished
position, reconciled it to STATE_CLOSED, and returned with no Telegram alert at all --
breakeven / TP1 partial / managed exit notified, an SL hit did not.

Every MT5 read and the whole Telegram transport are mocked here; nothing in this file
touches a terminal, a broker, or the network.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from mt5.account import Account
from mt5.symbol_resolver import SymbolMeta
from trade_management import journal, manager
from trade_management.claims import claim_position
from trade_management.close_reason import (
    CLOSE_REASON_MANUAL,
    CLOSE_REASON_SL,
    CLOSE_REASON_TP,
    CLOSE_REASON_UNKNOWN,
    resolve_close_reason,
)
from trade_management.models import STATE_CLOSED, NormalizedPosition
from trade_management.state import load_state

TICKET = 123456789

SYMBOL_META = SymbolMeta(
    symbol="EURUSD", tick_size=0.00001, tick_value=1.0, contract_size=100000.0,
    volume_min=0.01, volume_max=50.0, volume_step=0.01, digits=5,
)
FAKE_ACCOUNT = Account(
    login=1, server="Test-Demo", is_demo=True, balance=10_000.0, equity=10_000.0,
    trade_allowed=True, is_hedging_account=False,
)


def _deal(entry: int, reason: int):
    return SimpleNamespace(entry=entry, reason=reason, symbol="EURUSD", volume=0.40)


class _Sink:
    """Stands in for notifications.trade_management_alerts.notify_position_closed."""

    def __init__(self, raises: Exception | None = None):
        self.calls: list[tuple] = []
        self._raises = raises

    def __call__(self, ticket, symbol, close_reason, *, base_dir="journal", config=None):
        self.calls.append((ticket, symbol, close_reason))
        if self._raises is not None:
            raise self._raises


@pytest.fixture()
def closed_position_env(tmp_path, monkeypatch):
    """A claimed ticket whose position no longer exists at the broker."""
    claims_path = str(tmp_path / "claims.json")
    base_dir = str(tmp_path / "journal")

    position = NormalizedPosition(
        ticket=TICKET, symbol="EURUSD", direction="BUY", volume_initial=0.40, volume_current=0.40,
        entry_price=1.17000, current_bid=1.17000, current_ask=1.17002, current_price=1.17000,
        sl=1.16800, tp=None, profit=0.0, swap=0.0, commission=None, magic=0, comment="",
        open_time=datetime(2026, 8, 27, tzinfo=timezone.utc), account_login=1, account_server="Test-Demo",
    )
    claim, reason = claim_position(position, tp1=1.17600, final_r_multiple=5.0, path=claims_path)
    assert reason is None

    monkeypatch.setattr(manager.mt5_account, "account", lambda: FAKE_ACCOUNT)
    monkeypatch.setattr(manager.mt5_account, "positions", lambda ticket=None, symbol=None: [])
    monkeypatch.setattr(manager, "get_tick", lambda symbol: None)
    monkeypatch.setattr(manager, "get_symbol_meta", lambda symbol: SYMBOL_META)

    return SimpleNamespace(claims_path=claims_path, base_dir=base_dir, monkeypatch=monkeypatch)


def _arm(env, *, deals, sink=None):
    sink = sink or _Sink()
    env.monkeypatch.setattr(manager, "resolve_close_reason", lambda ticket: resolve_close_reason(ticket, lambda _t: deals))
    env.monkeypatch.setattr(manager, "notify_position_closed", sink)
    return sink


# --- close-reason classification (pure) --------------------------------------------

def test_resolve_close_reason_reads_the_closing_deal_only():
    deals = [_deal(entry=0, reason=0), _deal(entry=1, reason=4)]  # entry-in then SL exit
    assert resolve_close_reason(TICKET, lambda _t: deals) == CLOSE_REASON_SL


@pytest.mark.parametrize(
    "reason_code,expected",
    [(4, CLOSE_REASON_SL), (5, CLOSE_REASON_TP), (0, CLOSE_REASON_MANUAL), (99, CLOSE_REASON_UNKNOWN)],
)
def test_resolve_close_reason_maps_mt5_deal_reasons(reason_code, expected):
    assert resolve_close_reason(TICKET, lambda _t: [_deal(entry=1, reason=reason_code)]) == expected


def test_resolve_close_reason_never_infers_sl_from_a_loss():
    # a losing close with no deal-reason evidence must be UNKNOWN, not guessed as SL
    losing_but_unlabelled = [SimpleNamespace(entry=1, reason=None, profit=-250.0)]
    assert resolve_close_reason(TICKET, lambda _t: losing_but_unlabelled) == CLOSE_REASON_UNKNOWN


def test_resolve_close_reason_survives_history_failure():
    def boom(_ticket):
        raise RuntimeError("HISTORY_DEALS_GET_FAILED")

    assert resolve_close_reason(TICKET, boom) == CLOSE_REASON_UNKNOWN


# --- manager integration -----------------------------------------------------------

def test_sl_hit_emits_exactly_one_notification(closed_position_env):
    env = closed_position_env
    sink = _arm(env, deals=[_deal(entry=1, reason=4)])

    result = manager.run_cycle_for_ticket(TICKET, env.claims_path, env.base_dir)

    assert result.outcome == "BLOCKED"  # POSITION_CLOSED_EXTERNALLY, pre-existing behaviour
    assert load_state(TICKET, env.base_dir).state == STATE_CLOSED
    assert sink.calls == [(TICKET, "EURUSD", CLOSE_REASON_SL)]

    detected = [e for e in journal.read_events(TICKET, env.base_dir) if e["event"] == "BROKER_SIDE_CLOSE_DETECTED"]
    assert len(detected) == 1
    assert detected[0]["close_reason"] == CLOSE_REASON_SL
    assert detected[0]["notified"] is True


def test_reconcile_of_already_closed_position_does_not_duplicate(closed_position_env):
    env = closed_position_env
    sink = _arm(env, deals=[_deal(entry=1, reason=4)])

    manager.run_cycle_for_ticket(TICKET, env.claims_path, env.base_dir)
    # simulates both a scheduler re-run and a process restart: state + journal are the
    # only carried-over context, and the manager is re-entered from scratch
    manager.run_cycle_for_ticket(TICKET, env.claims_path, env.base_dir)
    manager.run_cycle_for_ticket(TICKET, env.claims_path, env.base_dir)

    assert len(sink.calls) == 1
    detected = [e for e in journal.read_events(TICKET, env.base_dir) if e["event"] == "BROKER_SIDE_CLOSE_DETECTED"]
    assert len(detected) == 1


def test_broker_tp_close_is_classified_not_reported_as_sl(closed_position_env):
    env = closed_position_env
    sink = _arm(env, deals=[_deal(entry=1, reason=5)])

    manager.run_cycle_for_ticket(TICKET, env.claims_path, env.base_dir)

    assert sink.calls == [(TICKET, "EURUSD", CLOSE_REASON_TP)]


def test_undeterminable_close_reason_reports_unknown(closed_position_env):
    env = closed_position_env
    sink = _arm(env, deals=[])

    manager.run_cycle_for_ticket(TICKET, env.claims_path, env.base_dir)

    assert sink.calls == [(TICKET, "EURUSD", CLOSE_REASON_UNKNOWN)]


def test_self_managed_close_is_not_double_reported(closed_position_env):
    env = closed_position_env
    sink = _arm(env, deals=[_deal(entry=1, reason=3)])
    # this manager's own confirmed exit already fired notify_confirmed_action("CLOSE")
    journal.record_event(TICKET, "CLOSE_CONFIRMED", env.base_dir, intent_id="i-1")

    manager.run_cycle_for_ticket(TICKET, env.claims_path, env.base_dir)

    assert sink.calls == []
    detected = [e for e in journal.read_events(TICKET, env.base_dir) if e["event"] == "BROKER_SIDE_CLOSE_DETECTED"]
    assert len(detected) == 1
    assert detected[0]["notified"] is False


def test_telegram_unavailable_does_not_break_reconciliation(closed_position_env):
    env = closed_position_env
    sink = _arm(env, deals=[_deal(entry=1, reason=4)], sink=_Sink(raises=RuntimeError("telegram down")))

    result = manager.run_cycle_for_ticket(TICKET, env.claims_path, env.base_dir)

    assert result.outcome == "BLOCKED"
    assert load_state(TICKET, env.base_dir).state == STATE_CLOSED  # close still committed
    assert len(sink.calls) == 1


def test_open_position_cycle_emits_no_close_notification(tmp_path, monkeypatch):
    """Regression guard: the TP1/breakeven/hold paths must be untouched by this hook."""
    claims_path = str(tmp_path / "claims.json")
    base_dir = str(tmp_path / "journal")
    position = NormalizedPosition(
        ticket=TICKET, symbol="EURUSD", direction="BUY", volume_initial=0.40, volume_current=0.40,
        entry_price=1.17000, current_bid=1.17500, current_ask=1.17502, current_price=1.17500,
        sl=1.16800, tp=None, profit=0.0, swap=0.0, commission=None, magic=0, comment="",
        open_time=datetime(2026, 8, 27, tzinfo=timezone.utc), account_login=1, account_server="Test-Demo",
    )
    claim, reason = claim_position(position, tp1=1.17600, final_r_multiple=5.0, path=claims_path)
    assert reason is None

    raw = SimpleNamespace(
        ticket=TICKET, type=0, volume=0.40, price_open=1.17000, sl=1.16800, tp=None,
        profit=0.0, swap=0.0, symbol="EURUSD", comment="", magic=0,
        time=int(datetime(2026, 8, 27, tzinfo=timezone.utc).timestamp()),
    )
    monkeypatch.setattr(manager.mt5_account, "account", lambda: FAKE_ACCOUNT)
    monkeypatch.setattr(manager.mt5_account, "positions", lambda ticket=None, symbol=None: [raw])
    monkeypatch.setattr(manager, "get_tick", lambda symbol: SimpleNamespace(bid=1.17500, ask=1.17502))
    monkeypatch.setattr(manager, "get_symbol_meta", lambda symbol: SYMBOL_META)
    sink = _Sink()
    monkeypatch.setattr(manager, "notify_position_closed", sink)

    result = manager.run_cycle_for_ticket(TICKET, claims_path, base_dir)

    assert result.outcome == "HOLD"
    assert sink.calls == []
