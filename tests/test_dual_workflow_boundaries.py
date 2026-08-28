"""DUAL_DAYTRADING_WORKFLOW_V1 spec sections 34/41/46: daytrading_workflow and
smc_watcher must stay proposal/alert-only -- no execution/order_send imports -- and must
not reimplement BOS/CHoCH/FVG/order-block/sweep/position-sizing primitives that already
exist elsewhere (verified by import-boundary, same static-source discipline as
test_entry_confirmation_v2.py's own execution/mt5 import-boundary tests).
"""
from __future__ import annotations

import ast
import pathlib

REPO_SRC = pathlib.Path(__file__).resolve().parents[1] / "src"


def _imported_module_names(path: pathlib.Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                yield node.module


def test_daytrading_workflow_has_no_execution_or_order_send_imports():
    pkg_dir = REPO_SRC / "daytrading_workflow"
    for path in pkg_dir.glob("*.py"):
        for name in _imported_module_names(path):
            assert not name.startswith("execution"), f"{path.name} imports {name}"


def test_smc_watcher_has_no_execution_or_order_send_imports():
    pkg_dir = REPO_SRC / "smc_watcher"
    for path in pkg_dir.glob("*.py"):
        for name in _imported_module_names(path):
            assert not name.startswith("execution"), f"{path.name} imports {name}"


def test_smc_watcher_alert_is_never_execution_eligible():
    from smc_watcher.conditions import evaluate_e3_condition
    from smc_watcher.watcher import SMCConditionWatcher
    import datetime as dt

    from liquidity.models import LiquidityLevel, LiquiditySide, LiquidityStatus

    level = LiquidityLevel(
        symbol="EURUSD", timeframe="M15", side=LiquiditySide.SELL_SIDE, source="ASIAN_LOW",
        price=1.1000, origin_time=dt.datetime(2026, 1, 5, tzinfo=dt.timezone.utc),
        status=LiquidityStatus.RECLAIMED, sweep_time=dt.datetime(2026, 1, 5, 6, 15, tzinfo=dt.timezone.utc),
    )
    e3 = evaluate_e3_condition(level)
    alert = SMCConditionWatcher().evaluate("SMC_CONDITIONAL", "EURUSD", e3_result=e3)
    assert alert.execution_eligible is False


def test_session_workflow_never_sets_execution_eligible_true_without_confirmation():
    import datetime as dt

    from daytrading.decision.models import MarketBias, MarketBiasDirection
    from daytrading_workflow.session_workflow import evaluate_session_completion
    from strategy_engine.session import Candle

    UTC = dt.timezone.utc

    def candle(hour, minute, o, h, l, c):
        return Candle(dt.datetime(2026, 1, 5, hour, minute, tzinfo=UTC), o, h, l, c)

    flat = [candle(*divmod(15 * i, 60), 1.1000, 1.1000, 1.1000, 1.1000) for i in range(24)]
    sweep = candle(6, 15, 1.0999, 1.0999, 1.0995, 1.1002)

    proposal = evaluate_session_completion(
        "TEST", "EURUSD", "asian", dt.date(2026, 1, 5), flat, 24,
        MarketBias(direction=MarketBiasDirection.BULLISH.value, timeframe="H1"),
        post_session_candles=[sweep],
    )
    assert proposal.proposal_status == "WAITING_CONFIRMATION"
