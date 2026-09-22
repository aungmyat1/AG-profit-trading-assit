"""WP-5/6 bridge focused tests: assistant.canonical_proposal_adapter and
assistant.commands.build_proposal_from_canonical.

MT5 I/O is never touched by anything under test here -- no monkeypatching needed,
unlike tests/test_assistant_proposal_execution.py (which exercises execute()).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

import assistant.commands as commands
from assistant.canonical_proposal_adapter import (
    REQUIRED_OWNER_INPUTS,
    CanonicalProposalMalformed,
    CanonicalProposalNotReady,
    canonical_proposal_to_trade_candidate,
    canonical_proposal_to_trade_proposal,
    trade_command_template,
)
from execution.executor import ProposalStore
from execution.models import ExecutionSource
from proposal_envelope.models import CanonicalProposal, PROPOSAL_BLOCKED, PROPOSAL_INCOMPLETE, PROPOSAL_READY


def _envelope(**overrides) -> CanonicalProposal:
    base = dict(
        proposal_envelope_id="OPP:ST_ASIAN_SWEEP_5R_V1:occ-1",
        strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1",
        market="FX", venue="VANTAGE_DEMO_MT5", symbol="EURUSD",
        proposal_state=PROPOSAL_READY,
        direction="BUY", entry=1.1000, stop=1.0950, targets=(1.1100,),
    )
    base.update(overrides)
    return CanonicalProposal(**base)


@pytest.fixture(autouse=True)
def _isolated_store(monkeypatch):
    monkeypatch.setattr(commands, "_store", ProposalStore())


# --------------------------------------------------------------------------- 1/6/7/8/9/10
def test_ready_envelope_maps_candidate_and_identity_and_geometry():
    envelope = _envelope()
    candidate = canonical_proposal_to_trade_candidate(envelope)
    assert candidate.direction == "LONG"
    assert candidate.entry_price == 1.1000
    assert candidate.stop_loss == 1.0950
    assert candidate.take_profit == 1.1100

    proposal = canonical_proposal_to_trade_proposal(envelope)
    assert proposal.proposal_id == envelope.proposal_envelope_id
    assert proposal.symbol == envelope.symbol
    assert proposal.candidate == candidate


# --------------------------------------------------------------------------- 2/3/4
def test_blocked_envelope_fails_closed():
    envelope = _envelope(proposal_state=PROPOSAL_BLOCKED, direction=None, entry=None, stop=None, targets=())
    with pytest.raises(CanonicalProposalNotReady):
        canonical_proposal_to_trade_candidate(envelope)


def test_incomplete_envelope_fails_closed():
    envelope = _envelope(proposal_state=PROPOSAL_INCOMPLETE, entry=None, stop=None, targets=())
    with pytest.raises(CanonicalProposalNotReady):
        canonical_proposal_to_trade_candidate(envelope)


def test_unknown_proposal_state_fails_closed():
    envelope = _envelope(proposal_state="SOMETHING_NEW")
    with pytest.raises(CanonicalProposalNotReady):
        canonical_proposal_to_trade_candidate(envelope)


# --------------------------------------------------------------------------- 5
def test_proposal_identity_preserved_across_bridge_and_command():
    envelope = _envelope()
    proposal = canonical_proposal_to_trade_proposal(envelope)
    command = trade_command_template(proposal, command_id="cmd-1")
    assert proposal.proposal_id == envelope.proposal_envelope_id
    assert command.proposal_id == proposal.proposal_id


# --------------------------------------------------------------------------- 11 (missing target permitted)
def test_missing_target_does_not_fail_closed_take_profit_stays_none():
    envelope = _envelope(targets=())
    candidate = canonical_proposal_to_trade_candidate(envelope)
    assert candidate.take_profit is None  # TradeCandidate's own existing contract permits this


def test_missing_entry_or_stop_fails_closed_even_if_marked_ready():
    envelope = _envelope(entry=None)
    with pytest.raises(CanonicalProposalMalformed):
        canonical_proposal_to_trade_candidate(envelope)

    envelope2 = _envelope(stop=None)
    with pytest.raises(CanonicalProposalMalformed):
        canonical_proposal_to_trade_candidate(envelope2)


def test_missing_proposal_identity_fails_closed():
    envelope = _envelope(proposal_envelope_id="")
    with pytest.raises(CanonicalProposalMalformed):
        canonical_proposal_to_trade_candidate(envelope)


def test_unsupported_direction_fails_closed():
    envelope = _envelope(direction="LONG")  # CanonicalProposal convention is BUY/SELL, not LONG/SHORT
    with pytest.raises(CanonicalProposalMalformed):
        canonical_proposal_to_trade_candidate(envelope)


# --------------------------------------------------------------------------- direction mapping
def test_sell_direction_maps_to_short_and_sell_side():
    envelope = _envelope(direction="SELL", entry=1.1000, stop=1.1050, targets=(1.0900,))
    candidate = canonical_proposal_to_trade_candidate(envelope)
    assert candidate.direction == "SHORT"
    proposal = canonical_proposal_to_trade_proposal(envelope)
    command = trade_command_template(proposal)
    assert command.side == "SELL"


# --------------------------------------------------------------------------- 12 no strategy re-evaluation
def test_module_never_imports_opportunity_eligibility_or_strategy_engine():
    path = Path(__file__).resolve().parents[1] / "src" / "assistant" / "canonical_proposal_adapter.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    forbidden_prefixes = ("opportunity.proposal_eligibility", "strategy_engine", "opportunity.engine")
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            for forbidden in forbidden_prefixes:
                assert not name.startswith(forbidden), f"canonical_proposal_adapter.py imports {name!r}"


# --------------------------------------------------------------------------- 13/14/15 no MT5/equity/symbol_meta
def test_trade_candidate_carries_no_equity_or_symbol_meta():
    candidate = canonical_proposal_to_trade_candidate(_envelope())
    assert candidate.equity is None
    assert candidate.symbol_meta is None


def test_module_never_imports_mt5():
    path = Path(__file__).resolve().parents[1] / "src" / "assistant" / "canonical_proposal_adapter.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            assert not name.startswith("mt5"), f"canonical_proposal_adapter.py imports {name!r}"


# --------------------------------------------------------------------------- 16/17/18 no execution/broker call
def test_module_never_imports_execution_executor_or_mt5_gateway():
    path = Path(__file__).resolve().parents[1] / "src" / "assistant" / "canonical_proposal_adapter.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            assert name not in ("execution.executor", "execution.mt5_gateway"), \
                f"canonical_proposal_adapter.py imports {name!r}"


def test_module_never_references_order_send_or_execute_command():
    path = Path(__file__).resolve().parents[1] / "src" / "assistant" / "canonical_proposal_adapter.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    forbidden_names = {"order_send", "order_check", "order_open", "execute_command", "execute"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            continue
        name = None
        if isinstance(node, ast.Name):
            name = node.id
        elif isinstance(node, ast.Attribute):
            name = node.attr
        assert name not in forbidden_names, f"canonical_proposal_adapter.py references {name!r}"


def test_constructing_trade_command_performs_no_execution_call(monkeypatch):
    """Behavioral: constructing a TradeCommand from the bridge alone must not reach
    execution.executor.execute -- patch it to explode if ever called."""
    import execution.executor as executor_module

    def _boom(*args, **kwargs):
        raise AssertionError("execute() must never be called by the bridge")

    monkeypatch.setattr(executor_module, "execute", _boom)

    envelope = _envelope()
    proposal = canonical_proposal_to_trade_proposal(envelope)
    command = trade_command_template(proposal)
    assert command.action == "OPEN"
    assert command.source == ExecutionSource.ASSISTANT_PROPOSAL


# --------------------------------------------------------------------------- REQUIRED_OWNER_INPUTS / risk
def test_trade_command_template_leaves_risk_percent_and_volume_unset():
    envelope = _envelope()
    proposal = canonical_proposal_to_trade_proposal(envelope)
    command = trade_command_template(proposal)
    assert command.risk_percent is None
    assert command.volume is None
    assert "risk_percent" in REQUIRED_OWNER_INPUTS


# --------------------------------------------------------------------------- store reuse (no new store)
def test_build_proposal_from_canonical_uses_existing_commands_store():
    envelope = _envelope()
    proposal = commands.build_proposal_from_canonical(envelope)
    assert commands.get_proposal(proposal.proposal_id) is proposal
    assert commands.get_proposal(proposal.proposal_id).proposal_id == envelope.proposal_envelope_id


def test_build_proposal_from_canonical_propagates_fail_closed():
    envelope = _envelope(proposal_state=PROPOSAL_BLOCKED, direction=None, entry=None, stop=None, targets=())
    with pytest.raises(CanonicalProposalNotReady):
        commands.build_proposal_from_canonical(envelope)
    # nothing was stored
    assert commands.list_eligible_proposals() == ()


# --------------------------------------------------------------------------- 19/20 confirmation stays outside
def test_execute_command_signature_and_boundary_unchanged():
    """The existing owner-confirmation boundary is untouched by this bridge: execute_command
    still requires an explicit, non-defaulted user_confirmed keyword."""
    import inspect

    sig = inspect.signature(commands.execute_command)
    assert "user_confirmed" in sig.parameters
    assert sig.parameters["user_confirmed"].default is inspect.Parameter.empty


def test_prepared_command_alone_is_rejected_without_user_confirmed():
    """Full-loop proof (still no broker call -- REJECTED before any MT5 code runs):
    a prepared TradeCommand submitted via the real execute_command() without
    user_confirmed=True is rejected at the very first gate, exactly as for any other
    TradeCommand -- the bridge grants no special-cased confirmation."""
    envelope = _envelope()
    proposal = commands.build_proposal_from_canonical(envelope)
    command = trade_command_template(proposal, command_id="cmd-unconfirmed")
    report = commands.execute_command(command, user_confirmed=False)
    assert report.status == "REJECTED"
    assert report.gate_reason_code == "EXECUTION_NOT_AUTHORIZED"
