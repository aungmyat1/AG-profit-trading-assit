from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import ast
from types import SimpleNamespace as NS

import pytest

from demo_execution.stage_b import DemoExecutionRefused, DemoStageB

TOKEN = "owner-approved-012345"
NOW = dt.datetime(2026, 9, 30, 12, tzinfo=dt.timezone.utc)


class MockMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    DEAL_ENTRY_IN = 0
    DEAL_ENTRY_OUT = 1
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_DONE_PARTIAL = 10010

    def __init__(self):
        self.account = NS(trade_mode=0, server="VTMarkets-Demo", equity=10_000.0)
        self.deals = []
        self.sent = []

    def account_info(self): return self.account
    def history_deals_get(self, start, end): return self.deals
    def symbol_info(self, symbol): return NS(trade_tick_size=0.00001, trade_tick_value=1.0, volume_step=0.01, volume_min=0.01, volume_max=100.0)
    def symbol_info_tick(self, symbol): return NS(ask=1.10002, bid=1.10000)
    def order_send(self, request):
        self.sent.append(request)
        return NS(retcode=self.TRADE_RETCODE_DONE, order=77, deal=88)
    def positions_get(self, **kwargs): return (NS(ticket=99, symbol=kwargs["symbol"], volume=self.sent[-1]["volume"]),)


def ticket(client_id="ticket-1"):
    return {"status": "PREPARED_ONLY", "client_order_id": client_id, "symbol": "EURUSD", "direction": "BUY", "entry": 1.10002, "stop_loss": 1.09902, "take_profit": 1.10202}


def enabled(tmp_path: Path, mt5=None):
    engine = DemoStageB(mt5 or MockMT5(), tmp_path, enabled=True)
    engine.approvals.approve("ticket-1", TOKEN)
    return engine


def test_disabled_by_default_never_calls_order_send(tmp_path):
    mt5 = MockMT5(); engine = DemoStageB(mt5, tmp_path)
    engine.approvals.approve("ticket-1", TOKEN)
    with pytest.raises(DemoExecutionRefused, match="DISABLED"):
        engine.place(ticket(), TOKEN, now=NOW)
    assert mt5.sent == []


@pytest.mark.parametrize("mode,server,reason", [(1, "VTMarkets-Demo", "ACCOUNT_NOT_DEMO"), (0, "VTMarkets-Demo-2", "SERVER_NOT_APPROVED")])
def test_exact_demo_account_and_server_gate(tmp_path, mode, server, reason):
    mt5 = MockMT5(); mt5.account.trade_mode = mode; mt5.account.server = server
    engine = enabled(tmp_path, mt5)
    with pytest.raises(DemoExecutionRefused, match=reason): engine.place(ticket(), TOKEN, now=NOW)
    assert mt5.sent == []


def test_kill_switch_refuses(tmp_path):
    engine = enabled(tmp_path); engine.kill_switch_file.touch()
    with pytest.raises(DemoExecutionRefused, match="KILL_SWITCH"): engine.place(ticket(), TOKEN, now=NOW)
    assert engine.mt5.sent == []


def test_requires_prepared_ticket_and_one_use_explicit_approval(tmp_path):
    engine = enabled(tmp_path)
    bad = ticket(); bad["status"] = "READY"
    with pytest.raises(DemoExecutionRefused, match="PREPARED_ONLY"): engine.place(bad, TOKEN, now=NOW)
    with pytest.raises(DemoExecutionRefused, match="INVALID_OR_USED"): engine.place(ticket(), "wrong-token-12345", now=NOW)
    assert engine.mt5.sent == []


def test_fixed_half_percent_risk_success_and_full_reconciliation(tmp_path):
    engine = enabled(tmp_path)
    result = engine.place(ticket(), TOKEN, now=NOW)
    assert result["status"] == "CONFIRMED"
    assert len(engine.mt5.sent) == 1
    # $50 risk / ($0.001 / $0.00001 * $1 per tick) = 0.50 lots.
    assert engine.mt5.sent[0]["volume"] == 0.5
    events = [json.loads(line)["event"] for line in (tmp_path / "reconciliation.jsonl").read_text().splitlines()]
    assert events == ["REQUEST_RECEIVED", "ORDER_SEND_ATTEMPT", "ORDER_SEND_RESULT", "POST_SEND_RECONCILIATION"]


def test_idempotent_client_order_id_blocks_second_send(tmp_path):
    engine = enabled(tmp_path); engine.place(ticket(), TOKEN, now=NOW)
    with pytest.raises(DemoExecutionRefused, match="DUPLICATE"):
        engine.place(ticket(), TOKEN, now=NOW)
    assert len(engine.mt5.sent) == 1


def test_max_three_trades_per_utc_day(tmp_path):
    mt5 = MockMT5(); mt5.deals = [NS(entry=0), NS(entry=0), NS(entry=0)]
    engine = enabled(tmp_path, mt5)
    with pytest.raises(DemoExecutionRefused, match="MAX_TRADES"):
        engine.place(ticket(), TOKEN, now=NOW)
    assert mt5.sent == []


def test_daily_loss_cap_includes_profit_commission_swap_and_fee(tmp_path):
    mt5 = MockMT5(); mt5.account.equity = 9800
    mt5.deals = [NS(entry=1, profit=-190, commission=-5, swap=-3, fee=-2)]
    engine = enabled(tmp_path, mt5)
    with pytest.raises(DemoExecutionRefused, match="DAILY_LOSS_CAP"):
        engine.place(ticket(), TOKEN, now=NOW)
    assert mt5.sent == []


def test_source_has_no_scheduler_import():
    source = Path(__file__).parents[1].joinpath("stage_b.py").read_text(encoding="utf-8")
    imports = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    assert not any("schedul" in name.lower() for name in imports)
