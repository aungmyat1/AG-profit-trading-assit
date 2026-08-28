"""End-to-end (single-cycle) tests for trade_management.manager, with every MT5 read
monkeypatched -- no live terminal connection needed. Exercises the full
claim -> detect -> evaluate -> validate -> gateway(dry-run) -> journal chain, matching
how scripts/manage_positions.py actually calls this module.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from mt5.account import Account
from mt5.symbol_resolver import SymbolMeta
from trade_management import journal, manager
from trade_management.claims import claim_position
from trade_management.models import STATE_MANAGED_OPEN, NormalizedPosition
from trade_management.state import load_state

SYMBOL_META = SymbolMeta(
    symbol="EURUSD", tick_size=0.00001, tick_value=1.0, contract_size=100000.0,
    volume_min=0.01, volume_max=50.0, volume_step=0.01, digits=5,
)
FAKE_ACCOUNT = Account(
    login=1, server="Test-Demo", is_demo=True, balance=10_000.0, equity=10_000.0,
    trade_allowed=True, is_hedging_account=False,
)


def _raw_position(volume=0.40, sl=1.16800):
    return SimpleNamespace(
        ticket=123456789, type=0, volume=volume, price_open=1.17000, sl=sl, tp=None,
        profit=0.0, swap=0.0, symbol="EURUSD", comment="", magic=0,
        time=int(datetime(2026, 8, 27, tzinfo=timezone.utc).timestamp()),
    )


def _setup(tmp_path, monkeypatch, bid_ask, raw_position):
    claims_path = str(tmp_path / "claims.json")
    base_dir = str(tmp_path / "journal")

    position = NormalizedPosition(
        ticket=123456789, symbol="EURUSD", direction="BUY", volume_initial=0.40, volume_current=0.40,
        entry_price=1.17000, current_bid=bid_ask[0], current_ask=bid_ask[1], current_price=bid_ask[0],
        sl=1.16800, tp=None, profit=0.0, swap=0.0, commission=None, magic=0, comment="",
        open_time=datetime(2026, 8, 27, tzinfo=timezone.utc), account_login=1, account_server="Test-Demo",
    )
    claim, reason = claim_position(position, tp1=1.17600, final_r_multiple=5.0, path=claims_path)
    assert reason is None

    monkeypatch.setattr(manager.mt5_account, "account", lambda: FAKE_ACCOUNT)
    monkeypatch.setattr(manager.mt5_account, "positions", lambda ticket=None, symbol=None: [raw_position])
    monkeypatch.setattr(manager, "get_tick", lambda symbol: SimpleNamespace(bid=bid_ask[0], ask=bid_ask[1]))
    monkeypatch.setattr(manager, "get_symbol_meta", lambda symbol: SYMBOL_META)

    return claims_path, base_dir


def test_cycle_holds_below_tp1(tmp_path, monkeypatch):
    claims_path, base_dir = _setup(tmp_path, monkeypatch, bid_ask=(1.17500, 1.17502), raw_position=_raw_position())

    result = manager.run_cycle_for_ticket(123456789, claims_path, base_dir)

    assert result.outcome == "HOLD"
    record = load_state(123456789, base_dir)
    assert record.state == STATE_MANAGED_OPEN


def test_cycle_at_tp1_is_dry_run_by_default_and_does_not_advance_state(tmp_path, monkeypatch):
    claims_path, base_dir = _setup(tmp_path, monkeypatch, bid_ask=(1.17600, 1.17602), raw_position=_raw_position())

    result = manager.run_cycle_for_ticket(123456789, claims_path, base_dir)

    assert result.outcome == "DRY_RUN"
    assert result.intent.action == "PARTIAL_CLOSE"
    record = load_state(123456789, base_dir)
    assert record.state == STATE_MANAGED_OPEN  # not advanced -- nothing was actually confirmed

    events = journal.read_events(123456789, base_dir)
    event_types = [e["event"] for e in events]
    assert "PARTIAL_CLOSE_REQUESTED" in event_types
    assert "PARTIAL_CLOSE_DRY_RUN" in event_types


def test_foreign_ticket_is_never_touched(tmp_path, monkeypatch):
    claims_path = str(tmp_path / "claims.json")
    base_dir = str(tmp_path / "journal")
    result = manager.run_cycle_for_ticket(999, claims_path, base_dir)
    assert result.outcome == "FOREIGN"
