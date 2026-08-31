"""Tests for execution.coordinator.ExecutionCoordinator: TradeProposal -> shared GLOBAL
guards -> execution.executor.execute() (Forex) / CryptoExecutionAdapter (Crypto).

Same isolation idiom as tests/test_execution_executor.py: mt5_gateway.order_open and
execution.journal's functions are monkeypatched at the point executor.py imports them --
no live MT5 terminal, no real journal/ writes. Guards use tmp_path-backed JsonKeyValueStore
instances, same convention as tests/test_liquidity_sweep_retest_strategy.py.
"""
from __future__ import annotations

import datetime as dt

import pytest

from execution import build_intent, executor
from execution.adapter import SyntheticMetadataError, TradeProposal, require_exchange_verified_metadata
from execution.close_ledger import CloseLedger
from execution.coordinator import (
    GLOBAL_LEDGER_STRATEGY_ID,
    STATUS_BLOCKED_DAILY_LOSS,
    STATUS_BLOCKED_OPEN_POSITION,
    STATUS_CONFIRMATION_REQUIRED,
    STATUS_DUPLICATE_REQUEST,
    STATUS_EXECUTION_DELEGATED,
    STATUS_PROPOSAL_ONLY,
    ExecutionCoordinator,
    _forex_command,
)
from execution.daily_loss_guard import DailyLossGuard
from execution.models import OrderSendResult
from execution.position_guard import OpenPositionGuard
from mt5.symbol_resolver import METADATA_SOURCE_EXCHANGE_VERIFIED, SymbolMeta
from runtime_state.store import JsonKeyValueStore
from strategy_engine.models import RiskConfig, StrategyConfig, TargetLeg, TradeSignal
from strategy_engine.sweep_retest.crypto_symbols import crypto_symbol_meta
from strategy_engine.sweep_retest.profile import PROFILE_CRYPTO_PERP, PROFILE_FOREX
from trade_management.models import (
    GEOMETRY_VALID,
    OVERALL_READY,
    SIZING_NOT_REQUESTED,
    PositionSizing,
    PositionStateAdvisory,
    TradeGeometry,
    TradeManagementResult,
)

UTC = dt.timezone.utc
STRATEGY_A = "ST_ASIAN_SWEEP_5R_V1"
STRATEGY_B = "ST_LIQUIDITY_SWEEP_RETEST_V1"


def _fake_tm_result(direction: str, entry: float, sl: float, tp) -> TradeManagementResult:
    return TradeManagementResult(
        symbol="EURUSD", direction=direction, overall_status=OVERALL_READY,
        geometry=TradeGeometry(status=GEOMETRY_VALID, direction=direction, entry=entry,
                                stop_loss=sl, take_profit=tp),
        sizing=PositionSizing(status=SIZING_NOT_REQUESTED),
        position_state=PositionStateAdvisory(status="NOT_EVALUATED"),
    )


def _forex_proposal(**overrides) -> TradeProposal:
    fields = dict(
        setup_id="EURUSD:2026-01-05:001", strategy_id=STRATEGY_B, symbol="EURUSD",
        profile_id=PROFILE_FOREX, direction="LONG", entry=1.1000, stop_loss=1.0950,
        tp1=1.1050, tp2=1.1100, volume=0.5, risk_amount=100.0,
    )
    fields.update(overrides)
    return TradeProposal(**fields)


def _crypto_proposal(**overrides) -> TradeProposal:
    fields = dict(
        setup_id="BTCUSDT:2026-01-05:001", strategy_id=STRATEGY_B, symbol="BTCUSDT",
        profile_id=PROFILE_CRYPTO_PERP, direction="SHORT", entry=42000.0, stop_loss=42200.0,
        tp1=41500.0, tp2=41000.0, volume=0.01, risk_amount=50.0,
    )
    fields.update(overrides)
    return TradeProposal(**fields)


def _coordinator(tmp_path) -> ExecutionCoordinator:
    return ExecutionCoordinator(
        open_position_guard=OpenPositionGuard(JsonKeyValueStore(str(tmp_path / "open_positions.json"))),
        daily_loss_guard=DailyLossGuard(JsonKeyValueStore(str(tmp_path / "daily_r.json")), GLOBAL_LEDGER_STRATEGY_ID),
        close_ledger=CloseLedger(JsonKeyValueStore(str(tmp_path / "closed_r.json"))),
    )


# ============================================================================= session strategy routing (Tests 1, 3, 4)

def _session_strategy_config() -> StrategyConfig:
    """Minimal StrategyConfig with an unambiguous MARKET entry_order_type -- same idiom
    tests/test_execution_intent_builder.py's own _strategy() helper uses. The REAL
    registered strategies/ST_ASIAN_SWEEP_5R_V1.yaml declares entry_order_type:
    MARKET_OR_LIMIT (a pre-existing, documented ambiguity -- strategies/STRATEGY_LEDGER.md
    'Open gaps', also asserted by
    tests/test_execution_intent_builder.py::test_real_strategy_config_is_ambiguous_on_entry_order_type),
    which build_intent() rejects with ENTRY_EXECUTION_UNDEFINED regardless of this phase --
    fixing that ambiguity is strategy-config scope, explicitly out of bounds here (spec:
    do not change signal/session rules). This fixture isolates ExecutionCoordinator's own
    routing behavior from that pre-existing, unrelated config gap."""
    return StrategyConfig(
        strategy_id=STRATEGY_A, strategy_name="Asian Sweep 5R", strategy_family="Session",
        version="1.0.0", status="ACTIVE_INCUBATION", instruments=("EURUSD",), timeframe="M15",
        magic_number=777001, session_pairs=(),
        risk=RiskConfig("FIXED_PERCENT_OR_CONTRACT", "PERCENT_OF_SESSION_RANGE", 0.25, 2.0, 10),
        entry_order_type="MARKET", total_target_r=5.0,
        legs=(TargetLeg(leg_id=1, volume_pct=0.75, target_type="OPPOSITE_SESSION_BOUNDARY"),),
        max_range_pips_eurusd=25.0, time_invalidation="15:00 GMT", structural_invalidation="x",
        source_path="test",
    )


def _session_signal() -> TradeSignal:
    return TradeSignal(
        signal_id="ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:EURUSD:2026-01-05", strategy_id=STRATEGY_A,
        strategy_version="1.0.0", symbol="EURUSD", pair_id="ASIAN_LONDON", reference_session="Asian",
        session_date=dt.date(2026, 1, 5), box_high=1.1050, box_low=1.0950, box_mid=1.1000,
        regime="RANGE", setup="SWEEP", status="SIGNAL", reason_code="LOWER_SWEEP_STRICT_PENETRATION",
        direction="LONG", entry=1.1000, stop_loss=1.0990, risk_distance=0.0010,
    )


def _session_strategy_proposal() -> TradeProposal:
    """The seam: strategy_engine.TradeSignal -> execution.intent_builder.build_intent()
    (unchanged, reused) -> TradeIntent -> TradeProposal.from_trade_intent() (the sibling
    constructor added for this phase) -- proves ST_ASIAN_SWEEP_5R_V1's own signal/sizing
    pipeline, not a stand-in, produces the proposal that reaches submit()."""
    result = build_intent(_session_signal(), _session_strategy_config(), equity=10_000.0,
                           symbol_meta=SymbolMeta(symbol="EURUSD", tick_size=0.00001, tick_value=1.0,
                                                   contract_size=100000.0, volume_min=0.01,
                                                   volume_max=50.0, volume_step=0.01, digits=5),
                           risk_per_trade_pct=1.0)
    assert result.intent is not None  # sanity: fixture itself must reach STATUS_READY
    return TradeProposal.from_trade_intent(result.intent)


def test_session_strategy_signal_routes_through_coordinator(monkeypatch, tmp_path):
    proposal = _session_strategy_proposal()
    assert proposal.strategy_id == STRATEGY_A
    _mock_geometry(monkeypatch, "LONG", proposal.entry, proposal.stop_loss, proposal.tp1)
    calls = _mock_order_open(monkeypatch, side="BUY", symbol="EURUSD")

    coordinator = _coordinator(tmp_path)
    result = coordinator.submit(proposal, user_confirmed=True)

    assert result.status == STATUS_EXECUTION_DELEGATED
    assert len(calls) == 1
    assert calls[0]["volume"] == pytest.approx(proposal.volume)  # read off the intent, not recomputed
    assert coordinator.open_position_guard.is_blocked() is True  # confirmed fill registered open


def test_session_strategy_open_position_blocks_sweep_retest_proposal(monkeypatch, tmp_path):
    coordinator = _coordinator(tmp_path)
    coordinator.open_position_guard.register_open("555", STRATEGY_A, "EURUSD", risk_amount=100.0)
    calls = _mock_order_open(monkeypatch)

    result = coordinator.submit(_forex_proposal(strategy_id=STRATEGY_B), user_confirmed=True)

    assert result.status == STATUS_BLOCKED_OPEN_POSITION
    assert calls == []


def test_sweep_retest_open_position_blocks_session_strategy_proposal(monkeypatch, tmp_path):
    coordinator = _coordinator(tmp_path)
    coordinator.open_position_guard.register_open("556", STRATEGY_B, "GBPUSD", risk_amount=100.0)
    calls = _mock_order_open(monkeypatch)

    proposal = _session_strategy_proposal()
    result = coordinator.submit(proposal, user_confirmed=True)

    assert result.status == STATUS_BLOCKED_OPEN_POSITION
    assert calls == []


@pytest.fixture(autouse=True)
def _isolated_journal(monkeypatch):
    # Same isolation as tests/test_execution_executor.py -- no real journal/ filesystem
    # writes, no live MT5 terminal. execution.coordinator imports the SAME journal module
    # object executor.py does (`from execution import journal`), so patching it here
    # covers both the coordinator's own has_executed() short-circuit check and executor's
    # internal claim_command/record_event calls.
    monkeypatch.setattr(executor.journal, "claim_command", lambda command_id: True)
    monkeypatch.setattr(executor.journal, "has_executed", lambda command_id: False)
    monkeypatch.setattr(executor.journal, "record_event", lambda *a, **kw: None)


def _mock_geometry(monkeypatch, direction, entry, sl, tp):
    monkeypatch.setattr(executor, "evaluate_trade_management",
                         lambda request: _fake_tm_result(direction, entry, sl, tp))


def _mock_order_open(monkeypatch, **result_overrides):
    calls = []
    fields = dict(status="EXECUTED", reason_code="ORDER_SEND_DONE", symbol="EURUSD",
                  side="BUY", filled_volume=0.5, fill_price=1.1000, ticket=555, deal_id=999,
                  broker_retcode=10009)
    fields.update(result_overrides)

    def fake_order_open(**kwargs):
        calls.append(kwargs)
        return OrderSendResult(**fields)

    monkeypatch.setattr(executor.mt5_gateway, "order_open", fake_order_open)
    return calls


# ============================================================================= Forex routing

def test_forex_proposal_routes_to_existing_executor(monkeypatch, tmp_path):
    proposal = _forex_proposal()
    _mock_geometry(monkeypatch, "LONG", proposal.entry, proposal.stop_loss, proposal.tp1)
    calls = _mock_order_open(monkeypatch, side="BUY", symbol="EURUSD")

    coordinator = _coordinator(tmp_path)
    result = coordinator.submit(proposal, user_confirmed=True)

    assert result.status == STATUS_EXECUTION_DELEGATED
    assert len(calls) == 1
    assert calls[0]["symbol"] == "EURUSD"
    assert calls[0]["volume"] == pytest.approx(0.5)  # read off the proposal, not recomputed
    assert result.execution_report is not None
    assert result.execution_report.result.ticket == 555  # real executor's ExecutionReport, not a stand-in


def test_forex_does_not_bypass_explicit_confirmation(monkeypatch, tmp_path):
    proposal = _forex_proposal()
    _mock_geometry(monkeypatch, "LONG", proposal.entry, proposal.stop_loss, proposal.tp1)
    calls = _mock_order_open(monkeypatch)

    coordinator = _coordinator(tmp_path)
    result = coordinator.submit(proposal, user_confirmed=False)

    assert result.status == STATUS_CONFIRMATION_REQUIRED
    assert result.execution_report.gate_reason_code == "EXECUTION_NOT_AUTHORIZED"
    assert calls == []  # order_send never reachable without explicit confirmation


# ============================================================================= Crypto routing

def test_crypto_proposal_remains_proposal_only(tmp_path):
    proposal = _crypto_proposal()
    coordinator = _coordinator(tmp_path)

    result = coordinator.submit(proposal, user_confirmed=True)

    assert result.status == STATUS_PROPOSAL_ONLY
    assert result.adapter_result.status == "NOT_IMPLEMENTED"
    assert result.execution_report is None  # never touched the Forex/executor path


def test_crypto_adapter_performs_no_live_call(monkeypatch, tmp_path):
    import ast
    import socket

    import execution.adapter as adapter_module

    # No networking library is even imported by the adapter module -- structurally there
    # is nothing to call out with, not merely "it wasn't invoked this run." Parse the
    # actual import statements (not the prose/docstrings) so this doesn't false-positive
    # on the module's own documentation of what it deliberately does NOT do.
    tree = ast.parse(open(adapter_module.__file__, "r", encoding="utf-8").read())
    imported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_names.add(node.module.split(".")[0])
    forbidden = {"socket", "requests", "urllib", "aiohttp", "websocket", "ccxt", "http"}
    assert imported_names & forbidden == set()

    # Belt-and-suspenders: make any actual socket construction raise, then prove
    # submit() still succeeds -- if a network call were reachable, this would blow up.
    def _explode(*a, **kw):
        raise AssertionError("CryptoExecutionAdapter.submit() must never open a socket")

    monkeypatch.setattr(socket, "socket", _explode)

    proposal = _crypto_proposal()
    coordinator = _coordinator(tmp_path)
    result = coordinator.submit(proposal, user_confirmed=True)

    assert result.status == STATUS_PROPOSAL_ONLY


# ============================================================================= synthetic metadata safety

def test_synthetic_crypto_metadata_cannot_reach_real_execution():
    synthetic = crypto_symbol_meta("BTCUSDT")
    assert synthetic.metadata_source != METADATA_SOURCE_EXCHANGE_VERIFIED

    with pytest.raises(SyntheticMetadataError):
        require_exchange_verified_metadata(synthetic)

    verified = SymbolMeta(symbol="EURUSD", tick_size=0.00001, tick_value=1.0, contract_size=100000.0,
                           volume_min=0.01, volume_max=100.0, volume_step=0.01, digits=5)
    require_exchange_verified_metadata(verified)  # does not raise -- EXCHANGE_VERIFIED by default


# ============================================================================= global open-position guard

def test_forex_position_blocks_crypto_proposal(monkeypatch, tmp_path):
    coordinator = _coordinator(tmp_path)
    coordinator.open_position_guard.register_open("pos-eurusd-1", STRATEGY_A, "EURUSD")

    result = coordinator.submit(_crypto_proposal(), user_confirmed=True)

    assert result.status == STATUS_BLOCKED_OPEN_POSITION
    assert result.adapter_result is None  # blocked before ever reaching the adapter


def test_crypto_position_blocks_forex_proposal(monkeypatch, tmp_path):
    coordinator = _coordinator(tmp_path)
    coordinator.open_position_guard.register_open("pos-btcusdt-1", STRATEGY_A, "BTCUSDT")
    calls = _mock_order_open(monkeypatch)

    result = coordinator.submit(_forex_proposal(), user_confirmed=True)

    assert result.status == STATUS_BLOCKED_OPEN_POSITION
    assert calls == []  # blocked before ever reaching the real executor


def test_position_from_another_strategy_blocks_sweep_retest_execution(monkeypatch, tmp_path):
    coordinator = _coordinator(tmp_path)
    # A position opened by a DIFFERENT strategy_id (simulating ST_ASIAN_SWEEP_5R_V1).
    coordinator.open_position_guard.register_open("pos-gbpusd-1", STRATEGY_A, "GBPUSD")
    calls = _mock_order_open(monkeypatch)

    proposal = _forex_proposal(strategy_id=STRATEGY_B)  # ST_LIQUIDITY_SWEEP_RETEST_V1's own setup
    result = coordinator.submit(proposal, user_confirmed=True)

    assert result.status == STATUS_BLOCKED_OPEN_POSITION
    assert calls == []


# ============================================================================= global daily-loss guard

def test_daily_loss_from_two_strategies_triggers_global_circuit(monkeypatch, tmp_path):
    coordinator = _coordinator(tmp_path)
    day = dt.date(2026, 1, 5)
    coordinator.daily_loss_guard.record_trade_result(day, -1.0)  # e.g. STRATEGY_A's loss
    coordinator.daily_loss_guard.record_trade_result(day, -1.0)  # e.g. STRATEGY_B's loss
    assert coordinator.daily_loss_guard.is_blocked(day) is True

    calls = _mock_order_open(monkeypatch)
    result = coordinator.submit(_forex_proposal(), user_confirmed=True,
                                 now=dt.datetime(2026, 1, 5, 12, tzinfo=UTC))

    assert result.status == STATUS_BLOCKED_DAILY_LOSS
    assert calls == []


def test_daily_loss_reset_restores_eligibility_next_day(monkeypatch, tmp_path):
    coordinator = _coordinator(tmp_path)
    day1 = dt.date(2026, 1, 5)
    day2 = dt.date(2026, 1, 6)
    coordinator.daily_loss_guard.record_trade_result(day1, -2.0)
    assert coordinator.daily_loss_guard.is_blocked(day1) is True
    assert coordinator.daily_loss_guard.is_blocked(day2) is False  # fresh key, 0 realized R

    proposal = _forex_proposal()
    _mock_geometry(monkeypatch, "LONG", proposal.entry, proposal.stop_loss, proposal.tp1)
    _mock_order_open(monkeypatch)

    result = coordinator.submit(proposal, user_confirmed=True, now=dt.datetime(2026, 1, 6, 12, tzinfo=UTC))

    assert result.status != STATUS_BLOCKED_DAILY_LOSS
    assert result.status == STATUS_EXECUTION_DELEGATED


# ============================================================================= idempotency

def test_duplicate_submission_does_not_re_delegate_to_executor(monkeypatch, tmp_path):
    proposal = _forex_proposal()
    _mock_geometry(monkeypatch, "LONG", proposal.entry, proposal.stop_loss, proposal.tp1)
    calls = _mock_order_open(monkeypatch)

    executed_ids = set()
    monkeypatch.setattr(executor.journal, "has_executed", lambda command_id: command_id in executed_ids)

    coordinator = _coordinator(tmp_path)
    first = coordinator.submit(proposal, user_confirmed=True)
    assert first.status == STATUS_EXECUTION_DELEGATED
    assert len(calls) == 1

    # Simulate the real journal now reflecting this setup_id's ORDER_EXECUTED event (what
    # executor.execute() would have caused via journal.record_event in production).
    executed_ids.add(proposal.setup_id)

    second = coordinator.submit(proposal, user_confirmed=True)

    assert second.status == STATUS_DUPLICATE_REQUEST
    assert len(calls) == 1  # order_open was NOT called a second time -- no re-delegation


# ============================================================================= rejection does not register state

def test_rejected_request_registers_no_open_position_state(monkeypatch, tmp_path):
    coordinator = _coordinator(tmp_path)
    coordinator.open_position_guard.register_open("pos-existing-1", STRATEGY_A, "EURUSD")
    before = coordinator.open_position_guard.store.all()

    calls = _mock_order_open(monkeypatch)
    result = coordinator.submit(_crypto_proposal(), user_confirmed=True)

    assert result.status == STATUS_BLOCKED_OPEN_POSITION
    assert calls == []
    assert coordinator.open_position_guard.store.all() == before  # nothing new registered


# ============================================================================= no duplicated risk sizing

def test_coordinator_reads_volume_and_risk_amount_off_the_proposal_not_recomputed(monkeypatch):
    proposal = _forex_proposal(volume=0.42, risk_amount=123.4)

    command = _forex_command(proposal)

    assert command.volume == pytest.approx(0.42)
    assert command.sl == pytest.approx(proposal.stop_loss)
    assert command.tp == pytest.approx(proposal.tp1)
    assert command.entry == pytest.approx(proposal.entry)


def test_coordinator_never_calls_size_position(monkeypatch, tmp_path):
    import execution.risk as risk_module

    def _explode(*a, **kw):
        raise AssertionError("ExecutionCoordinator must never recompute risk sizing")

    monkeypatch.setattr(risk_module, "size_position", _explode)

    proposal = _forex_proposal()
    _mock_geometry(monkeypatch, "LONG", proposal.entry, proposal.stop_loss, proposal.tp1)
    _mock_order_open(monkeypatch)

    coordinator = _coordinator(tmp_path)
    result = coordinator.submit(proposal, user_confirmed=True)

    assert result.status == STATUS_EXECUTION_DELEGATED
