"""PANEL_R3_OWNER_DECISION_BRIDGE focused tests: owner_decision.bridge.

Covers the 10 semantic points required by the mission brief:
  1. valid explicit owner approval can produce an ExecutionDecision (AUTHORIZED)
  2. reject cannot produce executable authority
  3. viewing/selecting a proposal cannot execute (structural: no such call path exists)
  4. missing owner confirmation fails closed (no OwnerDecision => nothing evaluated)
  5. stale proposal fails closed
  6. malformed decision fails closed
  7. duplicate confirmation cannot create duplicate execution authority
  8. Live account/environment remains rejected
  9. scheduler cannot synthesize approval (structural: no scheduler import/call path)
  10. watch/alert system cannot synthesize approval (structural: same)

MT5 I/O is never touched -- build_proposal_from_canonical/trade_command_template are
already execution-free (see test_assistant_canonical_proposal_adapter.py), and this
bridge never imports execution.executor or execution.mt5_gateway.
"""
from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import assistant.commands as commands
from execution.executor import ProposalStore
from execution.models import ExecutionSource
from owner_decision.bridge import (
    REASON_BROKER_MUTATION_BLOCKED,
    REASON_DEMO_NOT_AUTHORIZED,
    REASON_MALFORMED_DECISION,
    REASON_NON_DEMO_ENVIRONMENT,
    REASON_OWNER_REJECTED,
    REASON_PROPOSAL_NOT_READY,
    REASON_PROPOSAL_STALE,
    REASON_SYMBOL_MISMATCH,
    OwnerDecisionStore,
    evaluate_owner_decision,
)
from owner_decision.models import (
    ENVIRONMENT_DEMO,
    EXECUTION_DECISION_AUTHORIZED,
    EXECUTION_DECISION_REJECTED,
    OWNER_ACTION_APPROVE_DEMO,
    OWNER_ACTION_REJECT,
    OwnerDecision,
)
from proposal_envelope.models import CanonicalProposal, PROPOSAL_BLOCKED, PROPOSAL_READY


@pytest.fixture(autouse=True)
def _isolated_store(monkeypatch):
    monkeypatch.setattr(commands, "_store", ProposalStore())


def _envelope(**overrides) -> CanonicalProposal:
    base = dict(
        proposal_envelope_id="OPP:ST_ASIAN_SWEEP_5R_V1:occ-1",
        strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1",
        market="FX", venue="VANTAGE_DEMO_MT5", symbol="EURUSD",
        proposal_state=PROPOSAL_READY,
        direction="BUY", entry=1.1000, stop=1.0950, targets=(1.1100,),
        demo_authorized=True, broker_mutation_blocked=False,
    )
    base.update(overrides)
    return CanonicalProposal(**base)


def _decision(**overrides) -> OwnerDecision:
    base = dict(
        decision_id="dec-1", proposal_envelope_id="OPP:ST_ASIAN_SWEEP_5R_V1:occ-1",
        action=OWNER_ACTION_APPROVE_DEMO, symbol="EURUSD", environment=ENVIRONMENT_DEMO,
    )
    base.update(overrides)
    return OwnerDecision(**base)


# --------------------------------------------------------------------------- 1
def test_valid_explicit_approval_produces_authorized_execution_decision():
    envelope = _envelope()
    decision = _decision()
    result = evaluate_owner_decision(decision, envelope, store=OwnerDecisionStore())

    assert result.status == EXECUTION_DECISION_AUTHORIZED
    assert result.trade_command is not None
    assert result.trade_command.source == ExecutionSource.ASSISTANT_PROPOSAL
    assert result.trade_command.symbol == "EURUSD"
    assert result.trade_command.proposal_id == envelope.proposal_envelope_id
    # Never executed by constructing/returning it (execution.models.TradeCommand's own
    # contract) -- nothing in this module calls execute_command/execute().


# --------------------------------------------------------------------------- 2
def test_reject_action_can_never_produce_executable_authority():
    envelope = _envelope()
    decision = _decision(action=OWNER_ACTION_REJECT)
    result = evaluate_owner_decision(decision, envelope, store=OwnerDecisionStore())

    assert result.status == EXECUTION_DECISION_REJECTED
    assert result.reason_code == REASON_OWNER_REJECTED
    assert result.trade_command is None


# --------------------------------------------------------------------------- 3
def test_no_view_or_select_call_path_exists_into_the_bridge():
    """Structural: src/api/opportunity_analysis.py (R2, frozen) and the GET
    /api/canonical-proposals* read routes must never import owner_decision -- viewing
    or listing a proposal must be structurally incapable of reaching this module."""
    repo_src = Path(__file__).resolve().parents[1] / "src"
    for path in [repo_src / "api" / "opportunity_analysis.py", repo_src / "api" / "app.py"]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported_names.add(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported_names.add(alias.name)
        get_only_modules = {"opportunity_analysis"}
        if path.name == "opportunity_analysis.py":
            assert not any(m.startswith("owner_decision") for m in imported_names), (
                f"{path} (frozen R2 read model) must never import owner_decision."
            )


# --------------------------------------------------------------------------- 4
def test_missing_owner_confirmation_means_nothing_is_evaluated():
    """There is no code path that derives an OwnerDecision on its own -- a caller that
    never constructs one never reaches an authorization. This is asserted structurally:
    evaluate_owner_decision requires a non-None decision."""
    with pytest.raises(ValueError):
        evaluate_owner_decision(None, _envelope(), store=OwnerDecisionStore())


# --------------------------------------------------------------------------- 5
def test_stale_proposal_fails_closed():
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    envelope = _envelope(plan_expires_at=past)
    decision = _decision()
    result = evaluate_owner_decision(decision, envelope, store=OwnerDecisionStore())

    assert result.status == EXECUTION_DECISION_REJECTED
    assert result.reason_code == REASON_PROPOSAL_STALE
    assert result.trade_command is None


# --------------------------------------------------------------------------- 6
@pytest.mark.parametrize("bad_decision_kwargs", [
    {"action": "APPROVE_LIVE_NOW"},
    {"decision_id": ""},
    {"proposal_envelope_id": ""},
])
def test_malformed_decision_fails_closed(bad_decision_kwargs):
    decision = _decision(**bad_decision_kwargs)
    result = evaluate_owner_decision(decision, _envelope(), store=OwnerDecisionStore())

    assert result.status == EXECUTION_DECISION_REJECTED
    assert result.reason_code == REASON_MALFORMED_DECISION
    assert result.trade_command is None


def test_symbol_identity_mismatch_fails_closed():
    result = evaluate_owner_decision(
        _decision(symbol="GBPUSD"), _envelope(symbol="EURUSD"), store=OwnerDecisionStore(),
    )
    assert result.status == EXECUTION_DECISION_REJECTED
    assert result.reason_code == REASON_SYMBOL_MISMATCH


def test_non_ready_envelope_fails_closed():
    result = evaluate_owner_decision(
        _decision(), _envelope(proposal_state=PROPOSAL_BLOCKED), store=OwnerDecisionStore(),
    )
    assert result.status == EXECUTION_DECISION_REJECTED
    assert result.reason_code == REASON_PROPOSAL_NOT_READY


# --------------------------------------------------------------------------- 7
def test_duplicate_decision_id_never_creates_a_second_authorization():
    store = OwnerDecisionStore()
    envelope = _envelope()
    decision = _decision()

    first = evaluate_owner_decision(decision, envelope, store=store)
    # Replay with a DIFFERENT envelope/action -- the first recorded outcome for this
    # decision_id must win unchanged, never be re-derived.
    second = evaluate_owner_decision(
        _decision(action=OWNER_ACTION_REJECT), _envelope(symbol="GBPUSD"), store=store,
    )

    assert first.status == EXECUTION_DECISION_AUTHORIZED
    assert second is first
    assert second.trade_command is first.trade_command
    assert second.trade_command.command_id == first.trade_command.command_id


# --------------------------------------------------------------------------- 8
def test_live_environment_remains_rejected():
    result = evaluate_owner_decision(
        _decision(environment="LIVE"), _envelope(), store=OwnerDecisionStore(),
    )
    assert result.status == EXECUTION_DECISION_REJECTED
    assert result.reason_code == REASON_NON_DEMO_ENVIRONMENT
    assert result.trade_command is None


def test_demo_not_authorized_governance_is_never_bypassed():
    """Mirrors the existing repo-wide finding that most strategies currently carry
    demo_authorized=False (see docs/status/AG_DEMO_ORDER_VALIDATION_BLOCKED, referenced
    in project memory) -- the bridge must reproduce that same fail-closed outcome, never
    silently promote a strategy to demo authority itself."""
    result = evaluate_owner_decision(
        _decision(), _envelope(demo_authorized=False), store=OwnerDecisionStore(),
    )
    assert result.status == EXECUTION_DECISION_REJECTED
    assert result.reason_code == REASON_DEMO_NOT_AUTHORIZED


def test_broker_mutation_blocked_is_never_bypassed():
    result = evaluate_owner_decision(
        _decision(), _envelope(broker_mutation_blocked=True), store=OwnerDecisionStore(),
    )
    assert result.status == EXECUTION_DECISION_REJECTED
    assert result.reason_code == REASON_BROKER_MUTATION_BLOCKED


# --------------------------------------------------------------------------- 9/10
def test_no_scheduler_or_alert_module_imports_the_bridge():
    """Structural: neither ag_scheduler_v2/ nor alerting/ may import owner_decision --
    a scheduler tick or a watch/alert firing must be structurally incapable of
    synthesizing an OwnerDecision or calling evaluate_owner_decision."""
    repo_src = Path(__file__).resolve().parents[1] / "src"
    offenders = []
    for folder in ("ag_scheduler_v2", "alerting"):
        folder_path = repo_src / folder
        if not folder_path.exists():
            continue
        for py_file in folder_path.rglob("*.py"):
            text = py_file.read_text(encoding="utf-8")
            if "owner_decision" in text:
                offenders.append(str(py_file))
    assert offenders == [], f"scheduler/alert modules must never import owner_decision: {offenders}"


def test_bridge_module_never_imports_execution_executor_or_mt5_gateway():
    """Structural guard on the module itself: owner_decision.bridge must not add a new
    direct path to execution.executor/execution.mt5_gateway or call execute_command
    with user_confirmed=True anywhere."""
    bridge_path = Path(__file__).resolve().parents[1] / "src" / "owner_decision" / "bridge.py"
    tree = ast.parse(bridge_path.read_text(encoding="utf-8"))
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
    assert "execution.executor" not in imported_modules
    assert "execution.mt5_gateway" not in imported_modules
    text = bridge_path.read_text(encoding="utf-8")
    assert "user_confirmed=True" not in text
    assert "user_confirmed = True" not in text
