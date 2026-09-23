"""AG_FINAL_DEMO_EXECUTION_GATE_V1 focused tests: OwnerDecisionStore durability.

PANEL_R3 shipped OwnerDecisionStore as pure in-memory ("a restart loses it"). This
mission's gap analysis found that unsafe for AUTHORIZED outcomes: an ordinary process
restart between "owner clicked Confirm" and the separate, later, explicitly-confirmed
execute_command() call would lose the PREPARED TradeCommand template, and a caller
retrying the identical HTTP request after restart would silently re-derive a fresh
result from whatever the proposal looks like now instead of returning the original
durable outcome.

These tests cover the mission's required persistence/restart semantics:
  1. same decision_id -> same outcome across a fresh OwnerDecisionStore instance over
     the same path (restart-stability), count=1, no re-authorization.
  2. a REJECTED outcome is also preserved (no state rewind to "never evaluated").
  3. no `path` (unchanged default) keeps the original pure in-memory behavior -- a
     fresh instance sees nothing, exactly like before this change.
  4. concurrent confirmations of the identical decision_id map to exactly one durable
     record and one computed ExecutionDecision (same-process guarantee, matching
     execution.durable_idempotency.DurableExecutionStore's own documented boundary).

Zero MT5/broker I/O: evaluate_owner_decision never imports execution.executor or
execution.mt5_gateway (see test_owner_decision_bridge.py's own structural tests for
that invariant); nothing here constructs or calls either.
"""
from __future__ import annotations

import threading

import pytest

import assistant.commands as commands
from execution.executor import ProposalStore
from owner_decision.bridge import (
    OwnerDecisionStore,
    OwnerDecisionStoreUnavailable,
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
from proposal_envelope.models import CanonicalProposal, PROPOSAL_READY


@pytest.fixture(autouse=True)
def _isolated_proposal_store(monkeypatch):
    monkeypatch.setattr(commands, "_store", ProposalStore())


def _envelope(**overrides) -> CanonicalProposal:
    base = dict(
        proposal_envelope_id="OPP:ST_ASIAN_SWEEP_5R_V1:occ-persist-1",
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
        decision_id="dec-persist-1",
        proposal_envelope_id="OPP:ST_ASIAN_SWEEP_5R_V1:occ-persist-1",
        action=OWNER_ACTION_APPROVE_DEMO, symbol="EURUSD", environment=ENVIRONMENT_DEMO,
    )
    base.update(overrides)
    return OwnerDecision(**base)


# --------------------------------------------------------------------------- 1
def test_authorized_outcome_survives_a_fresh_store_instance_over_the_same_path(tmp_path):
    path = str(tmp_path / "owner_decisions.json")
    store_before_restart = OwnerDecisionStore(path=path)
    envelope = _envelope()
    decision = _decision()

    first = evaluate_owner_decision(decision, envelope, store=store_before_restart)
    assert first.status == EXECUTION_DECISION_AUTHORIZED
    assert first.trade_command is not None

    # Simulate a process restart: a brand-new OwnerDecisionStore instance, never
    # sharing memory with the one above, pointed at the SAME on-disk path.
    store_after_restart = OwnerDecisionStore(path=path)
    replayed = evaluate_owner_decision(decision, envelope, store=store_after_restart)

    assert replayed == first
    assert replayed.trade_command.command_id == first.trade_command.command_id
    # count=1: re-observing the same proposal/decision after restart records no
    # second entry.
    assert len(store_after_restart._decisions) == 1


# --------------------------------------------------------------------------- 2
def test_rejected_outcome_also_survives_restart_without_rewinding_to_unevaluated(tmp_path):
    path = str(tmp_path / "owner_decisions.json")
    store_before_restart = OwnerDecisionStore(path=path)
    decision = _decision(action=OWNER_ACTION_REJECT, decision_id="dec-persist-reject")

    first = evaluate_owner_decision(decision, _envelope(), store=store_before_restart)
    assert first.status == EXECUTION_DECISION_REJECTED

    store_after_restart = OwnerDecisionStore(path=path)
    replayed = evaluate_owner_decision(decision, _envelope(), store=store_after_restart)
    assert replayed.status == EXECUTION_DECISION_REJECTED
    assert replayed == first


# --------------------------------------------------------------------------- 3
def test_default_path_none_keeps_original_pure_in_memory_behavior():
    store_a = OwnerDecisionStore()
    evaluate_owner_decision(_decision(), _envelope(), store=store_a)

    store_b = OwnerDecisionStore()
    assert store_b.get("dec-persist-1") is None


# --------------------------------------------------------------------------- 4
def test_corrupt_on_disk_ledger_fails_closed_not_empty(tmp_path):
    path = tmp_path / "owner_decisions.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(OwnerDecisionStoreUnavailable):
        OwnerDecisionStore(path=str(path))


# --------------------------------------------------------------------------- 5
def test_concurrent_confirmations_of_the_same_decision_produce_one_winning_outcome(tmp_path):
    path = str(tmp_path / "owner_decisions.json")
    envelope = _envelope(proposal_envelope_id="OPP:ST_ASIAN_SWEEP_5R_V1:occ-concurrent",
                          strategy_id="ST_ASIAN_SWEEP_5R_V1")
    decision = _decision(decision_id="dec-concurrent-1",
                          proposal_envelope_id="OPP:ST_ASIAN_SWEEP_5R_V1:occ-concurrent")

    results = []
    barrier = threading.Barrier(8)

    def _confirm():
        store = OwnerDecisionStore(path=path)
        barrier.wait(timeout=5)
        results.append(evaluate_owner_decision(decision, envelope, store=store))

    threads = [threading.Thread(target=_confirm) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(results) == 8
    first = results[0]
    for r in results[1:]:
        assert r == first
        assert r.trade_command.command_id == first.trade_command.command_id

    # Exactly one durable record on disk for this decision_id.
    final_store = OwnerDecisionStore(path=path)
    assert len(final_store._decisions) == 1
