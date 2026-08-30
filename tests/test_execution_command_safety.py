"""Execution command safety through the public executor interface.

MT5 calls are replaced only at the broker seam; the real execution journal is used.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import threading
from types import SimpleNamespace

import pytest

from execution import executor
from execution import journal as execution_journal
from execution.models import ExecutionSource, OrderSendResult, TradeCommand
from mt5.management_gateway import GatewayResult
from mt5.symbol_resolver import SymbolMeta
from trade_management.models import (
    GEOMETRY_VALID,
    OVERALL_READY,
    SIZING_NOT_REQUESTED,
    PositionSizing,
    PositionStateAdvisory,
    TradeGeometry,
    TradeManagementResult,
)


def _close_command(command_id: str, volume: float | None = None) -> TradeCommand:
    return TradeCommand(
        command_id=command_id,
        action="CLOSE",
        symbol="EURUSD",
        source=ExecutionSource.USER_EXPLICIT_ORDER,
        position_ticket=987654321,
        volume=volume,
    )


def _open_command(command_id: str) -> TradeCommand:
    return TradeCommand(
        command_id=command_id,
        action="OPEN",
        symbol="EURUSD",
        source=ExecutionSource.USER_EXPLICIT_ORDER,
        side="SELL",
        volume=0.31,
        entry=1.16442,
        sl=1.16474,
        tp=1.16346,
    )


def _valid_trade_management_result() -> TradeManagementResult:
    return TradeManagementResult(
        symbol="EURUSD",
        direction="SHORT",
        overall_status=OVERALL_READY,
        geometry=TradeGeometry(
            status=GEOMETRY_VALID,
            direction="SHORT",
            entry=1.16442,
            stop_loss=1.16474,
            take_profit=1.16346,
        ),
        sizing=PositionSizing(status=SIZING_NOT_REQUESTED),
        position_state=PositionStateAdvisory(status="NOT_EVALUATED"),
    )


def _symbol_meta() -> SymbolMeta:
    return SymbolMeta(
        symbol="EURUSD",
        tick_size=0.00001,
        tick_value=1.0,
        contract_size=100000.0,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
        digits=5,
        point=0.00001,
    )


def test_repeated_close_command_impacts_broker_at_most_once(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        executor,
        "get_positions",
        lambda ticket=None: [SimpleNamespace(symbol="EURUSD", type=1, volume=0.31)],
    )
    monkeypatch.setattr(executor, "get_symbol_meta", lambda symbol: _symbol_meta())
    monkeypatch.setattr(
        executor,
        "get_tick",
        lambda symbol: SimpleNamespace(bid=1.16400, ask=1.16414, spread_points=14),
    )
    calls = []

    def close_position(ticket, symbol, direction, volume, price):
        calls.append((ticket, volume))
        return GatewayResult(dry_run=False, request={}, executed=True, retcode=10009, comment="ok")

    monkeypatch.setattr(executor, "close_position", close_position)

    first = executor.execute(_close_command("repeat-close"), user_confirmed=True)
    second = executor.execute(_close_command("repeat-close"), user_confirmed=True)

    assert first.status == "EXECUTED"
    assert second.status == "REJECTED"
    assert second.gate_reason_code == "DUPLICATE_COMMAND_BLOCKED"
    assert len(calls) == 1


def test_concurrent_close_workers_acquire_one_execution_claim(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    duplicate_check_barrier = threading.Barrier(2)
    original_has_executed = executor.journal.has_executed
    check_state = threading.local()

    def synchronized_duplicate_check(command_id, base_dir="journal"):
        if not getattr(check_state, "initial_check_done", False):
            check_state.initial_check_done = True
            duplicate_check_barrier.wait(timeout=5)
            return False
        return original_has_executed(command_id, base_dir)

    monkeypatch.setattr(
        executor.journal,
        "has_executed",
        synchronized_duplicate_check,
    )
    monkeypatch.setattr(
        executor,
        "get_positions",
        lambda ticket=None: [SimpleNamespace(symbol="EURUSD", type=1, volume=0.31)],
    )
    monkeypatch.setattr(executor, "get_symbol_meta", lambda symbol: _symbol_meta())
    monkeypatch.setattr(
        executor,
        "get_tick",
        lambda symbol: SimpleNamespace(bid=1.16400, ask=1.16414, spread_points=14),
    )
    calls = []

    def close_position(ticket, symbol, direction, volume, price):
        calls.append((ticket, volume))
        return GatewayResult(dry_run=False, request={}, executed=True, retcode=10009, comment="ok")

    monkeypatch.setattr(executor, "close_position", close_position)
    command = _close_command("concurrent-close")

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(executor.execute, command, user_confirmed=True)
        second = pool.submit(executor.execute, command, user_confirmed=True)
        reports = [first.result(timeout=5), second.result(timeout=5)]

    assert sorted(report.status for report in reports) == ["EXECUTED", "REJECTED"]
    assert len(calls) == 1


def test_concurrent_open_workers_acquire_one_execution_claim(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    duplicate_check_barrier = threading.Barrier(2)
    original_has_executed = executor.journal.has_executed
    check_state = threading.local()

    def synchronized_duplicate_check(command_id, base_dir="journal"):
        if not getattr(check_state, "initial_check_done", False):
            check_state.initial_check_done = True
            duplicate_check_barrier.wait(timeout=5)
            return False
        return original_has_executed(command_id, base_dir)

    monkeypatch.setattr(
        executor.journal,
        "has_executed",
        synchronized_duplicate_check,
    )
    monkeypatch.setattr(executor, "evaluate_trade_management", lambda request: _valid_trade_management_result())
    monkeypatch.setattr(executor, "get_positions", lambda **kwargs: [])
    monkeypatch.setattr(executor, "deals_for_symbol", lambda symbol, **kwargs: [])
    calls = []

    def order_open(**kwargs):
        calls.append(kwargs)
        return OrderSendResult(
            status="EXECUTED",
            reason_code="ORDER_SEND_DONE",
            symbol="EURUSD",
            side="SELL",
            requested_volume=0.31,
            filled_volume=0.31,
            ticket=1,
            deal_id=2,
        )

    monkeypatch.setattr(executor.mt5_gateway, "order_open", order_open)
    command = _open_command("concurrent-open")

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(executor.execute, command, user_confirmed=True)
        second = pool.submit(executor.execute, command, user_confirmed=True)
        reports = [first.result(timeout=5), second.result(timeout=5)]

    assert sorted(report.status for report in reports) == ["EXECUTED", "REJECTED"]
    assert len(calls) == 1


@pytest.mark.parametrize("requested", [0.0, -0.01, float("nan"), float("inf"), 0.32])
def test_invalid_close_volume_is_blocked_before_broker(monkeypatch, tmp_path, requested):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        executor,
        "get_positions",
        lambda ticket=None: [SimpleNamespace(symbol="EURUSD", type=0, volume=0.31)],
    )
    monkeypatch.setattr(executor, "get_symbol_meta", lambda symbol: _symbol_meta())
    monkeypatch.setattr(
        executor,
        "get_tick",
        lambda symbol: SimpleNamespace(bid=1.16400, ask=1.16414, spread_points=14),
    )
    calls = []
    monkeypatch.setattr(executor, "close_position", lambda *args: calls.append(args))

    report = executor.execute(
        _close_command(f"invalid-{requested!r}", volume=requested),
        user_confirmed=True,
    )

    assert report.status == "REJECTED"
    assert calls == []


@pytest.mark.parametrize(
    ("requested", "expected"),
    [
        (0.019, 0.01),  # off-step requests floor conservatively
        (0.01, 0.01),   # minimum valid partial close
        (0.12, 0.12),   # normal partial close
        (None, 0.31),   # omitted volume closes the full current position
    ],
)
def test_valid_close_volume_is_normalized_before_broker(monkeypatch, tmp_path, requested, expected):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        executor,
        "get_positions",
        lambda ticket=None: [SimpleNamespace(symbol="EURUSD", type=0, volume=0.31)],
    )
    monkeypatch.setattr(executor, "get_symbol_meta", lambda symbol: _symbol_meta())
    monkeypatch.setattr(
        executor,
        "get_tick",
        lambda symbol: SimpleNamespace(bid=1.16400, ask=1.16414, spread_points=14),
    )
    received = []

    def close_position(ticket, symbol, direction, volume, price):
        received.append(volume)
        return GatewayResult(dry_run=False, request={}, executed=True, retcode=10009, comment="ok")

    monkeypatch.setattr(executor, "close_position", close_position)

    report = executor.execute(
        _close_command(f"valid-{requested!r}", volume=requested),
        user_confirmed=True,
    )

    assert report.status == "EXECUTED"
    assert received == [expected]


@pytest.mark.parametrize(
    "command_id",
    ["../escape", r"..\escape", "foo/bar", r"foo\bar", r"C:\absolute\escape"],
)
def test_command_id_cannot_escape_journal_directory(tmp_path, command_id):
    journal_dir = tmp_path / "journal"

    assert execution_journal.claim_command(command_id, str(journal_dir)) is True
    execution_journal.record_event(command_id, "ORDER_EXECUTED", str(journal_dir))

    assert execution_journal.has_executed(command_id, str(journal_dir)) is True
    created = [path.resolve() for path in tmp_path.rglob("*") if path.is_file()]
    assert created
    assert all(path.is_relative_to(journal_dir.resolve()) for path in created)
    assert all(command_id not in path.name for path in created)


def test_execution_claim_survives_restart_without_process_memory(tmp_path):
    journal_dir = tmp_path / "journal"

    assert execution_journal.claim_command("restart-safe", str(journal_dir)) is True
    assert execution_journal.claim_command("restart-safe", str(journal_dir)) is False


def test_legacy_executed_journal_still_blocks_reexecution(tmp_path):
    journal_dir = tmp_path / "journal"
    journal_dir.mkdir()
    legacy = journal_dir / "execution_legacy-command.jsonl"
    legacy.write_text(
        '{"command_id":"legacy-command","event":"ORDER_EXECUTED"}\n',
        encoding="utf-8",
    )

    assert execution_journal.has_executed("legacy-command", str(journal_dir)) is True
    assert execution_journal.claim_command("legacy-command", str(journal_dir)) is False
