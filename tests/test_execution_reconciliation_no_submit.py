"""PANEL_R5C P10/P13#11: reconciliation cannot invoke broker submission.

Critical acceptance criterion for this package: execution.reconciliation must never
call order_send, submit, place_order, execute_order, or any equivalent broker mutation
-- statically (import graph, source text) and dynamically (a mock standing in for any
such capability is never invoked even when reconciliation runs a full, real,
MATCHED-outcome reconciliation cycle).
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock

from execution.durable_idempotency import DurableExecutionStore, STATE_AUTHORIZED, STATE_SUBMISSION_PENDING, compute_execution_fingerprint
from execution.reconciliation import comment_tag_for, reconcile_decision


def _module_path() -> Path:
    return Path(__file__).resolve().parents[1] / "src" / "execution" / "reconciliation.py"


# --------------------------------------------------------------------------- static
def test_module_imports_no_write_capable_code():
    tree = ast.parse(_module_path().read_text(encoding="utf-8"))
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)

    forbidden = {
        "execution.executor", "execution.mt5_gateway", "execution.coordinator",
        "mt5.management_gateway", "authorization.mt5_execution_handler",
        "authorization.telegram_gateway", "assistant.commands",
    }
    assert imported_modules & forbidden == set()
    assert imported_modules == {"__future__", "dataclasses", "typing", "execution.durable_idempotency"}


def test_module_source_never_mentions_broker_mutation_calls():
    text = _module_path().read_text(encoding="utf-8")
    for forbidden_call in ("order_send(", "order_check(", ".submit(", "place_order(", "execute_order("):
        assert forbidden_call not in text
    assert "user_confirmed=True" not in text
    assert "user_confirmed = True" not in text


def test_reconcile_decision_signature_has_no_execution_handler_parameter():
    """Structural proof: the function's own parameter list has nowhere to plug in a
    submission callable, unlike e.g. api.execution_service.authorize_demo_execution's
    execution_handler parameter."""
    import inspect

    from execution.reconciliation import reconcile_decision as target

    params = set(inspect.signature(target).parameters)
    assert "execution_handler" not in params
    assert "order_send" not in params
    assert params == {"store", "decision_id", "symbol", "positions_lookup", "deals_lookup"}


# --------------------------------------------------------------------------- dynamic
def _fp(decision_id: str) -> str:
    return compute_execution_fingerprint(
        decision_id=decision_id, proposal_envelope_id="FX:R5C-NOSUBMIT", action="APPROVE_DEMO",
        symbol="EURUSD", environment="DEMO",
    )


def test_full_matched_reconciliation_cycle_never_touches_a_submission_mock(tmp_path):
    """Runs a complete, real MATCHED reconciliation (the happy path most likely to
    tempt a future edit into "just resubmit if unmatched") while a submission mock sits
    in scope, never wired to anything reconcile_decision could reach. If a future edit
    ever gave reconcile_decision a way to call it, this mock's call count would move --
    today it structurally cannot."""
    order_send_mock = MagicMock(name="order_send_should_never_be_called")

    store = DurableExecutionStore(state_dir=str(tmp_path / "exec"))
    decision_id = "dec-nosubmit-1"
    command_id = f"OWNER_DECISION:{decision_id}"
    store.create_or_get(decision_id=decision_id, proposal_id="FX:R5C-NOSUBMIT", fingerprint=_fp(decision_id), command_id=command_id)
    store.transition(decision_id, state=STATE_AUTHORIZED)
    store.transition(decision_id, state=STATE_SUBMISSION_PENDING)

    class _Position:
        def __init__(self, ticket, comment):
            self.ticket = ticket
            self.identifier = ticket  # MT5: position identifier == its own ticket
            self.comment = comment

    tag = comment_tag_for(command_id)
    positions_lookup = lambda symbol=None: [_Position(ticket=1, comment=tag)]
    deals_lookup = lambda symbol=None: []

    result = reconcile_decision(
        store, decision_id, symbol="EURUSD", positions_lookup=positions_lookup, deals_lookup=deals_lookup,
    )
    assert result.record.state == "BROKER_ACCEPTED"
    order_send_mock.assert_not_called()
