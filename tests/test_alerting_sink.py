"""AlertSink (spec section 27): publish() only, JSONL journal follows this repo's
existing append-only journal convention (assistant/idea_journal.py)."""
from __future__ import annotations

import datetime as dt
import json
import os

from alerting.sink import JsonlAlertSink, LogAlertSink
from smc_watcher.conditions import evaluate_e3_condition
from smc_watcher.watcher import SMCConditionWatcher
from liquidity.models import LiquidityLevel, LiquiditySide, LiquidityStatus

UTC = dt.timezone.utc


def _alert():
    level = LiquidityLevel(
        symbol="EURUSD", timeframe="M15", side=LiquiditySide.SELL_SIDE, source="ASIAN_LOW",
        price=1.1000, origin_time=dt.datetime(2026, 1, 5, tzinfo=UTC),
        status=LiquidityStatus.RECLAIMED, sweep_time=dt.datetime(2026, 1, 5, 6, 15, tzinfo=UTC),
    )
    e3 = evaluate_e3_condition(level)
    return SMCConditionWatcher().evaluate("SMC_CONDITIONAL", "EURUSD", e3_result=e3)


def test_log_alert_sink_does_not_raise(caplog):
    LogAlertSink().publish(_alert())


def test_jsonl_alert_sink_appends_one_line(tmp_path):
    path = os.path.join(str(tmp_path), "smc_alerts.jsonl")
    sink = JsonlAlertSink(path=path)
    sink.publish(_alert())
    with open(path, "r", encoding="utf-8") as f:
        lines = [line for line in f if line.strip()]
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["symbol"] == "EURUSD"
    assert entry["execution_eligible"] is False
