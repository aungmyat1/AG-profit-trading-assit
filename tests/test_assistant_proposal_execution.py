"""Tests for AG_ASSISTANT_PROPOSAL_EXECUTION_V1 + AG_RISK_PERCENT_SIZING_LIVE_V1
(2026-08-28): TradeProposal creation/identity/resolution, staleness, risk-percent
sizing revalidation, and the "execute it" duplicate-protection gap fixed this pass.

Conservative volume normalization (floor-only rounding) and broker-min-volume
fail-closed behavior are NOT re-tested here -- already covered by
tests/test_trade_management_pretrade.py::test_normalization_rounds_down_never_up and
::test_normalization_below_min_is_size_unavailable, which executor.py's sizing path
reuses unchanged (trade_management.pretrade_engine.evaluate_trade_management).

MT5 I/O is monkeypatched throughout -- no live terminal connection needed, matching the
rest of the execution/ test suite's convention.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import assistant.commands as commands
from assistant.analysis_models import PROPOSAL_EXECUTED, PROPOSAL_READY, TradeCandidate, TradeProposal
from execution import executor
from execution.models import ExecutionSource, OrderSendResult, TradeCommand
from mt5.symbol_resolver import SymbolMeta


def _eurusd_meta(**overrides):
    fields = dict(symbol="EURUSD", tick_size=1e-5, tick_value=1.0, contract_size=100000.0,
                  volume_min=0.01, volume_max=100.0, volume_step=0.01, digits=5, point=1e-5)
    fields.update(overrides)
    return SymbolMeta(**fields)


def _proposal(symbol="EURUSD", direction="SHORT", entry=1.16442, sl=1.16474, tp=1.16346,
              risk_percent=0.5, equity=1000.0, age_seconds=0, ttl_minutes=15, status=PROPOSAL_READY,
              symbol_meta=None):
    now = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    candidate = TradeCandidate(
        direction=direction, entry_price=entry, stop_loss=sl, take_profit=tp,
        risk_percent=risk_percent, equity=equity, symbol_meta=symbol_meta or _eurusd_meta(),
    )
    return TradeProposal(
        proposal_id="AGP-TEST-1", created_at=now, expires_at=now + timedelta(minutes=ttl_minutes),
        symbol=symbol, timeframe="M15", candidate=candidate, status=status,
    )


def _fresh_store(proposal=None):
    store = executor.ProposalStore()
    if proposal is not None:
        store.put(proposal)
    return store


# --------------------------------------------------------------------- proposal identity/resolution

def test_build_proposal_ids_are_unique_and_command_references_the_same_id(monkeypatch):
    # commands.build_proposal() is the real production path (not the test fixture's
    # fixed "AGP-TEST-1" id) -- prove TWO real calls get distinct, stable ids, and that
    # a TradeCommand built to execute one references exactly that id.
    from assistant.analysis_models import AssistantAnalysisRequest, FiveSkillAnalysisResult
    from mt5.symbol_resolver import SymbolMeta as _SM

    candidate = TradeCandidate(direction="SHORT", entry_price=1.16442, stop_loss=1.16474,
                                take_profit=1.16346, risk_percent=0.5)
    fake_result = FiveSkillAnalysisResult(symbol="EURUSD", timeframe="M15",
                                           timestamp_utc=datetime.now(timezone.utc),
                                           market_context_status="OK")
    monkeypatch.setattr(commands, "analyze_market", lambda request: fake_result)

    req = AssistantAnalysisRequest(symbol="EURUSD", candidate=candidate)
    p1 = commands.build_proposal(req)
    p2 = commands.build_proposal(req)

    assert p1.proposal_id != p2.proposal_id

    command = TradeCommand(command_id="cmd-1", action="OPEN", symbol="",
                            source=ExecutionSource.ASSISTANT_PROPOSAL, proposal_id=p1.proposal_id)
    assert command.proposal_id == p1.proposal_id
    assert commands.get_proposal(p1.proposal_id).proposal_id == p1.proposal_id


def test_resolve_no_active_proposal(monkeypatch):
    monkeypatch.setattr(commands, "_store", executor.ProposalStore())
    proposal, reason = commands.resolve_active_proposal()
    assert proposal is None
    assert reason == commands.NO_ACTIVE_PROPOSAL


def test_resolve_single_eligible_proposal(monkeypatch):
    store = executor.ProposalStore()
    store.put(_proposal())
    monkeypatch.setattr(commands, "_store", store)
    proposal, reason = commands.resolve_active_proposal()
    assert reason is None
    assert proposal.proposal_id == "AGP-TEST-1"


def test_resolve_ambiguous_proposal(monkeypatch):
    store = executor.ProposalStore()
    p1 = _proposal()
    p2 = TradeProposal(proposal_id="AGP-TEST-2", created_at=p1.created_at, expires_at=p1.expires_at,
                        symbol="EURUSD", timeframe="M15", candidate=p1.candidate, status=PROPOSAL_READY)
    store.put(p1)
    store.put(p2)
    monkeypatch.setattr(commands, "_store", store)
    proposal, reason = commands.resolve_active_proposal()
    assert proposal is None
    assert reason == commands.AMBIGUOUS_PROPOSAL


def test_resolve_explicit_proposal_id_bypasses_ambiguity(monkeypatch):
    store = executor.ProposalStore()
    p1 = _proposal()
    p2 = TradeProposal(proposal_id="AGP-TEST-2", created_at=p1.created_at, expires_at=p1.expires_at,
                        symbol="EURUSD", timeframe="M15", candidate=p1.candidate, status=PROPOSAL_READY)
    store.put(p1)
    store.put(p2)
    monkeypatch.setattr(commands, "_store", store)
    proposal, reason = commands.resolve_active_proposal(proposal_id="AGP-TEST-2")
    assert reason is None
    assert proposal.proposal_id == "AGP-TEST-2"


def test_resolve_unknown_proposal_id_not_found(monkeypatch):
    monkeypatch.setattr(commands, "_store", executor.ProposalStore())
    proposal, reason = commands.resolve_active_proposal(proposal_id="does-not-exist")
    assert proposal is None
    assert reason == commands.PROPOSAL_NOT_FOUND


# ----------------------------------------------------------------------------- no-auth / stale gates

def test_assistant_proposal_execution_blocked_without_authorization(monkeypatch):
    store = _fresh_store(_proposal())
    calls = []
    monkeypatch.setattr(executor.mt5_gateway, "order_open", lambda **kw: calls.append(kw))

    command = TradeCommand(command_id="c1", action="OPEN", symbol="EURUSD",
                            source=ExecutionSource.ASSISTANT_PROPOSAL, proposal_id="AGP-TEST-1")
    report = executor.execute(command, user_confirmed=False, proposal_store=store)

    assert report.status == "REJECTED"
    assert report.gate_reason_code == "EXECUTION_NOT_AUTHORIZED"
    assert calls == []


def test_stale_proposal_blocks_before_order_send(monkeypatch):
    # created 10 minutes ago -- exceeds _STALE_PROPOSAL_MAX_AGE_SECONDS (300s).
    store = _fresh_store(_proposal(age_seconds=600))
    monkeypatch.setattr(executor, "get_tick", lambda symbol: __import__("types").SimpleNamespace(
        bid=1.16442, ask=1.16456, spread_points=13))
    calls = []
    monkeypatch.setattr(executor.mt5_gateway, "order_open", lambda **kw: calls.append(kw))
    monkeypatch.setattr(executor.journal, "record_event", lambda *a, **kw: None)
    monkeypatch.setattr(executor.journal, "has_executed", lambda command_id: False)

    command = TradeCommand(command_id="c2", action="OPEN", symbol="EURUSD",
                            source=ExecutionSource.ASSISTANT_PROPOSAL, proposal_id="AGP-TEST-1")
    report = executor.execute(command, user_confirmed=True, proposal_store=store)

    assert report.status == "REJECTED"
    assert report.gate_reason_code == "PROPOSAL_STALE_AGE"
    assert "PROPOSAL_STALE" in report.reasons
    assert calls == []
    assert store.get("AGP-TEST-1").status == "STALE"


# ---------------------------------------------------------------- proposal-driven execution (happy path)

def test_proposal_fields_resolve_side_sl_tp_risk_and_order_send_exactly_once(monkeypatch):
    # Command carries ONLY identity (command_id/action/source/proposal_id) -- no side/
    # sl/tp/risk_percent/symbol -- exactly the target CLI shape from section 20.
    store = _fresh_store(_proposal(direction="SHORT", entry=1.16442, sl=1.16474, tp=1.16346,
                                    risk_percent=0.5, equity=1000.0))
    monkeypatch.setattr(executor, "get_tick", lambda symbol: __import__("types").SimpleNamespace(
        bid=1.16445, ask=1.16459, spread_points=13))
    monkeypatch.setattr(executor.journal, "record_event", lambda *a, **kw: None)
    monkeypatch.setattr(executor.journal, "has_executed", lambda command_id: False)
    # Fresh equity/symbol_meta at execution time (section 11) -- not the proposal's own
    # stale snapshot. Mocked here so this test stays offline/deterministic.
    monkeypatch.setattr(executor, "_resolve_equity_and_symbol_meta",
                         lambda symbol: (1000.0, _eurusd_meta(), None))

    sent = {}
    call_count = {"n": 0}

    def fake_order_open(**kwargs):
        call_count["n"] += 1
        sent.update(kwargs)
        return OrderSendResult(status="EXECUTED", reason_code="ORDER_SEND_DONE", symbol="EURUSD",
                                side=kwargs["side"], requested_volume=kwargs["volume"],
                                filled_volume=kwargs["volume"], ticket=1, deal_id=2)

    monkeypatch.setattr(executor.mt5_gateway, "order_open", fake_order_open)

    command = TradeCommand(command_id="c3", action="OPEN", symbol="",
                            source=ExecutionSource.ASSISTANT_PROPOSAL, proposal_id="AGP-TEST-1")
    report = executor.execute(command, user_confirmed=True, proposal_store=store)

    assert report.status == "EXECUTED"
    assert call_count["n"] == 1
    assert sent["symbol"] == "EURUSD"
    assert sent["side"] == "SELL"  # SHORT -> SELL
    assert sent["sl"] == 1.16474
    assert sent["tp"] == 1.16346
    # risk_percent=0.5% of $1000 equity == $5 budget; volume was DERIVED, not passed in
    # explicitly on the command -- proves the sizing engine actually ran.
    assert sent["volume"] is not None and sent["volume"] > 0
    assert store.get("AGP-TEST-1").status == PROPOSAL_EXECUTED


def test_already_executed_proposal_blocks_second_execution_with_new_command_id(monkeypatch):
    # Section 25's exact scenario: "Execute P123 again" gets a FRESH command_id (a new
    # CLI invocation), which the command_id-keyed journal check alone would not catch.
    store = _fresh_store(_proposal(status=PROPOSAL_EXECUTED))
    calls = []
    monkeypatch.setattr(executor.mt5_gateway, "order_open", lambda **kw: calls.append(kw))
    monkeypatch.setattr(executor.journal, "has_executed", lambda command_id: False)  # different command_id

    command = TradeCommand(command_id="brand-new-command-id", action="OPEN", symbol="",
                            source=ExecutionSource.ASSISTANT_PROPOSAL, proposal_id="AGP-TEST-1")
    report = executor.execute(command, user_confirmed=True, proposal_store=store)

    assert report.status == "REJECTED"
    assert report.gate_reason_code == "DUPLICATE_COMMAND_BLOCKED"
    assert calls == []


# --------------------------------------------------------------------------- risk revalidation

def test_final_risk_revalidation_blocks_before_order_send(monkeypatch):
    # Force a tm_result whose sizing claims MORE actual risk than requested -- the
    # defensive final-risk-revalidation check (section 18) must catch this even though
    # evaluate_sizing() itself is not expected to ever produce it.
    from trade_management.models import (
        GEOMETRY_VALID, OVERALL_READY, PositionSizing, PositionStateAdvisory,
        SIZING_READY, TradeGeometry, TradeManagementResult,
    )

    def fake_tm_result(request):
        return TradeManagementResult(
            symbol="EURUSD", direction="SHORT", overall_status=OVERALL_READY,
            geometry=TradeGeometry(status=GEOMETRY_VALID, direction="SHORT",
                                    entry=1.16442, stop_loss=1.16474, take_profit=1.16346),
            sizing=PositionSizing(status=SIZING_READY, normalized_volume=0.31,
                                   actual_risk_percent=5.0),  # >> requested 0.5%
            position_state=PositionStateAdvisory(status="NOT_EVALUATED"),
        )

    monkeypatch.setattr(executor, "evaluate_trade_management", fake_tm_result)
    monkeypatch.setattr(executor, "_resolve_equity_and_symbol_meta",
                         lambda symbol: (1000.0, _eurusd_meta(), None))
    monkeypatch.setattr(executor.journal, "record_event", lambda *a, **kw: None)
    monkeypatch.setattr(executor.journal, "has_executed", lambda command_id: False)
    calls = []
    monkeypatch.setattr(executor.mt5_gateway, "order_open", lambda **kw: calls.append(kw))

    command = TradeCommand(command_id="c4", action="OPEN", symbol="EURUSD", side="SELL",
                            entry=1.16442, sl=1.16474, tp=1.16346, risk_percent=0.5,
                            source=ExecutionSource.USER_EXPLICIT_ORDER)
    report = executor.execute(command, user_confirmed=True)

    assert report.status == "REJECTED"
    assert report.gate_reason_code == "RISK_LIMIT_EXCEEDED"
    assert calls == []


# --------------------------------------------------------------------------- quote-side entry price

def test_buy_market_entry_resolves_to_ask(monkeypatch):
    import MetaTrader5 as mt5
    from types import SimpleNamespace
    from execution import mt5_gateway as gw

    monkeypatch.setattr(mt5, "symbol_info_tick", lambda symbol: SimpleNamespace(bid=1.16442, ask=1.16456))
    seen = {}
    monkeypatch.setattr(gw, "_order_send_allowed", lambda: False)  # stay in dry-run, just inspect the request

    result = gw.order_open("EURUSD", "BUY", "MARKET", 0.01, sl=1.16400, tp=1.16500,
                            magic_number=0, comment="test")
    assert result.reason_code == "DRY_RUN"
    assert result.requested_price == 1.16456  # ASK for a BUY


def test_sell_market_entry_resolves_to_bid(monkeypatch):
    import MetaTrader5 as mt5
    from types import SimpleNamespace
    from execution import mt5_gateway as gw

    monkeypatch.setattr(mt5, "symbol_info_tick", lambda symbol: SimpleNamespace(bid=1.16442, ask=1.16456))
    monkeypatch.setattr(gw, "_order_send_allowed", lambda: False)

    result = gw.order_open("EURUSD", "SELL", "MARKET", 0.01, sl=1.16500, tp=1.16400,
                            magic_number=0, comment="test")
    assert result.reason_code == "DRY_RUN"
    assert result.requested_price == 1.16442  # BID for a SELL


def test_executor_resolves_buy_entry_to_ask(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(executor, "get_tick", lambda symbol: SimpleNamespace(
        bid=1.16442, ask=1.16456, spread_points=13))
    command = TradeCommand(command_id="c5", action="OPEN", symbol="EURUSD", side="BUY",
                            source=ExecutionSource.USER_EXPLICIT_ORDER)
    price, error = executor._resolve_entry_price(command)
    assert error is None
    assert price == 1.16456  # ASK


def test_executor_resolves_sell_entry_to_bid(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(executor, "get_tick", lambda symbol: SimpleNamespace(
        bid=1.16442, ask=1.16456, spread_points=13))
    command = TradeCommand(command_id="c6", action="OPEN", symbol="EURUSD", side="SELL",
                            source=ExecutionSource.USER_EXPLICIT_ORDER)
    price, error = executor._resolve_entry_price(command)
    assert error is None
    assert price == 1.16442  # BID
