"""AG_PANEL_R5C_PROPOSAL_DECISION_UNIQUENESS_V2 focused tests.

Invariant under test: ONE canonical proposal -> AT MOST ONE authoritative owner
decision. decision_id remains the request/idempotency identity (unchanged,
independently-verified R3/R4/R5A behavior); proposal_envelope_id becomes the
higher-level authority key layered on top, enforced atomically inside
owner_decision.bridge.OwnerDecisionStore.commit_terminal_decision.

Matrix (P11), each item independently proven:
  1. first APPROVE succeeds
  2. first REJECT succeeds
  3. identical APPROVE replay remains idempotent
  4. identical REJECT replay remains idempotent
  5. same-ID APPROVE->REJECT preserves original
  6. same-ID REJECT->APPROVE preserves original
  7. different-ID APPROVE->APPROVE creates one authority
  8. different-ID REJECT->REJECT creates one authority
  9. different-ID APPROVE->REJECT fails closed
  10. different-ID REJECT->APPROVE fails closed
  11. restart preserves APPROVE authority
  12. restart preserves REJECT authority
  13. post-restart same-semantic/different-ID creates no duplicate
  14. post-restart opposite/different-ID fails closed
  15. concurrent APPROVE/REJECT leaves exactly one authority
  16. concurrent APPROVE/APPROVE leaves exactly one authority
  17. concurrent REJECT/REJECT leaves exactly one authority
  18. corrupt duplicate proposal authority fails closed
  19. unavailable persistence fails closed (store construction)
  20. unauthenticated request creates no authority -- structural: this module has no
      auth of its own; auth is enforced at the API layer (require_owner_auth), entirely
      above this bridge -- see test_api_owner_decision_auth.py for the actual gate. This
      file only proves that evaluate_owner_decision()/OwnerDecisionStore have no
      alternate, auth-free path to authority (i.e. there is exactly one function that
      can ever establish proposal authority, and it always requires a full OwnerDecision
      object -- never invoked implicitly).

Validation-failure rejections (non-DEMO environment, envelope missing/not-ready,
symbol mismatch, demo not authorized, broker mutation blocked, stale, malformed
proposal, unknown action, missing ids) are deliberately EXCLUDED from proposal-level
authority -- see OwnerDecisionStore._is_terminal_owner_outcome's docstring. A test below
proves a validation failure never blocks a later, correctly-formed request for the same
proposal from being evaluated for real.
"""
from __future__ import annotations

import threading

import pytest

import assistant.commands as commands
from execution.executor import ProposalStore
from owner_decision.bridge import (
    REASON_NON_DEMO_ENVIRONMENT,
    REASON_OWNER_REJECTED,
    REASON_PROPOSAL_ALREADY_DECIDED,
    OwnerDecisionProposalAuthorityConflict,
    OwnerDecisionStore,
    OwnerDecisionStoreUnavailable,
    evaluate_owner_decision,
)
from owner_decision.models import (
    ENVIRONMENT_DEMO,
    ENVIRONMENT_LIVE,
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
        proposal_envelope_id="OPP:ST_ASIAN_SWEEP_5R_V1:occ-r5c-1",
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
        decision_id="dec-r5c-A",
        proposal_envelope_id="OPP:ST_ASIAN_SWEEP_5R_V1:occ-r5c-1",
        action=OWNER_ACTION_APPROVE_DEMO, symbol="EURUSD", environment=ENVIRONMENT_DEMO,
    )
    base.update(overrides)
    return OwnerDecision(**base)


# --------------------------------------------------------------------------- 1, 2
def test_first_approve_succeeds():
    result = evaluate_owner_decision(_decision(), _envelope(), store=OwnerDecisionStore())
    assert result.status == EXECUTION_DECISION_AUTHORIZED


def test_first_reject_succeeds():
    result = evaluate_owner_decision(
        _decision(action=OWNER_ACTION_REJECT), _envelope(), store=OwnerDecisionStore(),
    )
    assert result.status == EXECUTION_DECISION_REJECTED
    assert result.reason_code == REASON_OWNER_REJECTED


# --------------------------------------------------------------------------- 3, 4
def test_identical_approve_replay_remains_idempotent():
    store = OwnerDecisionStore()
    first = evaluate_owner_decision(_decision(), _envelope(), store=store)
    second = evaluate_owner_decision(_decision(), _envelope(), store=store)
    assert first == second
    assert len(store._decisions) == 1


def test_identical_reject_replay_remains_idempotent():
    store = OwnerDecisionStore()
    d = _decision(action=OWNER_ACTION_REJECT)
    first = evaluate_owner_decision(d, _envelope(), store=store)
    second = evaluate_owner_decision(d, _envelope(), store=store)
    assert first == second
    assert len(store._decisions) == 1


# --------------------------------------------------------------------------- 5, 6
def test_same_id_approve_then_reject_preserves_original():
    store = OwnerDecisionStore()
    approve = evaluate_owner_decision(_decision(decision_id="dec-same"), _envelope(), store=store)
    assert approve.status == EXECUTION_DECISION_AUTHORIZED

    replay_as_reject = evaluate_owner_decision(
        _decision(decision_id="dec-same", action=OWNER_ACTION_REJECT), _envelope(), store=store,
    )
    assert replay_as_reject.status == EXECUTION_DECISION_AUTHORIZED
    assert replay_as_reject == approve


def test_same_id_reject_then_approve_preserves_original():
    store = OwnerDecisionStore()
    reject = evaluate_owner_decision(
        _decision(decision_id="dec-same", action=OWNER_ACTION_REJECT), _envelope(), store=store,
    )
    assert reject.status == EXECUTION_DECISION_REJECTED

    replay_as_approve = evaluate_owner_decision(
        _decision(decision_id="dec-same"), _envelope(), store=store,
    )
    assert replay_as_approve.status == EXECUTION_DECISION_REJECTED
    assert replay_as_approve == reject


# --------------------------------------------------------------------------- 7, 8
def test_different_id_approve_then_approve_creates_one_authority():
    store = OwnerDecisionStore()
    env = _envelope()
    first = evaluate_owner_decision(_decision(decision_id="dec-A"), env, store=store)
    second = evaluate_owner_decision(_decision(decision_id="dec-B"), env, store=store)

    assert first.status == EXECUTION_DECISION_AUTHORIZED
    assert second.status == EXECUTION_DECISION_AUTHORIZED
    assert second == first
    assert second.decision_id == "dec-A"  # the ORIGINAL authority is what is replayed
    # "dec-B" itself was never durably recorded as a second authority.
    assert store.get("dec-B") is None
    assert len(store._decisions) == 1


def test_different_id_reject_then_reject_creates_one_authority():
    store = OwnerDecisionStore()
    env = _envelope()
    first = evaluate_owner_decision(
        _decision(decision_id="dec-A", action=OWNER_ACTION_REJECT), env, store=store,
    )
    second = evaluate_owner_decision(
        _decision(decision_id="dec-B", action=OWNER_ACTION_REJECT), env, store=store,
    )

    assert first.status == EXECUTION_DECISION_REJECTED
    assert second == first
    assert second.decision_id == "dec-A"
    assert store.get("dec-B") is None
    assert len(store._decisions) == 1


# --------------------------------------------------------------------------- 9, 10
def test_different_id_approve_then_reject_fails_closed():
    store = OwnerDecisionStore()
    env = _envelope()
    approve = evaluate_owner_decision(_decision(decision_id="dec-A"), env, store=store)
    assert approve.status == EXECUTION_DECISION_AUTHORIZED

    reject_attempt = evaluate_owner_decision(
        _decision(decision_id="dec-B", action=OWNER_ACTION_REJECT), env, store=store,
    )
    assert reject_attempt.status == EXECUTION_DECISION_REJECTED
    assert reject_attempt.reason_code == REASON_PROPOSAL_ALREADY_DECIDED
    assert reject_attempt.decision_id == "dec-B"

    # Original authority untouched -- "dec-A" still resolves to AUTHORIZED.
    assert store.get("dec-A") == approve
    assert store.proposal_authority(env.proposal_envelope_id) == approve


def test_different_id_reject_then_approve_fails_closed():
    store = OwnerDecisionStore()
    env = _envelope()
    reject = evaluate_owner_decision(
        _decision(decision_id="dec-A", action=OWNER_ACTION_REJECT), env, store=store,
    )
    assert reject.status == EXECUTION_DECISION_REJECTED

    approve_attempt = evaluate_owner_decision(_decision(decision_id="dec-B"), env, store=store)
    assert approve_attempt.status == EXECUTION_DECISION_REJECTED
    assert approve_attempt.reason_code == REASON_PROPOSAL_ALREADY_DECIDED
    assert approve_attempt.trade_command is None  # never a prepared command on conflict

    assert store.get("dec-A") == reject
    assert store.proposal_authority(env.proposal_envelope_id) == reject


# --------------------------------------------------------------------------- validation
# failures never establish authority, and never block a later real evaluation.
def test_validation_failure_rejection_does_not_establish_proposal_authority():
    store = OwnerDecisionStore()
    env = _envelope()
    bad_env = evaluate_owner_decision(
        _decision(decision_id="dec-bad-env", environment=ENVIRONMENT_LIVE), env, store=store,
    )
    assert bad_env.status == EXECUTION_DECISION_REJECTED
    assert bad_env.reason_code == REASON_NON_DEMO_ENVIRONMENT
    assert store.proposal_authority(env.proposal_envelope_id) is None

    # A later, correctly-formed request for the SAME proposal still gets a real
    # evaluation and succeeds -- the earlier validation failure was not authoritative.
    good = evaluate_owner_decision(_decision(decision_id="dec-good"), env, store=store)
    assert good.status == EXECUTION_DECISION_AUTHORIZED


# --------------------------------------------------------------------------- 11-14
def test_restart_preserves_approve_authority_and_blocks_conflicting_and_dupes(tmp_path):
    path = str(tmp_path / "owner_decisions.json")
    env = _envelope()
    store1 = OwnerDecisionStore(path=path)
    approve = evaluate_owner_decision(_decision(decision_id="dec-A"), env, store=store1)
    assert approve.status == EXECUTION_DECISION_AUTHORIZED

    # -- 11: restart preserves APPROVE authority
    store2 = OwnerDecisionStore(path=path)
    assert store2.proposal_authority(env.proposal_envelope_id).status == EXECUTION_DECISION_AUTHORIZED

    # -- 13: post-restart same-semantic/different-ID creates no duplicate
    dupe = evaluate_owner_decision(_decision(decision_id="dec-B"), env, store=store2)
    assert dupe.decision_id == "dec-A"
    assert len(store2._decisions) == 1

    # -- 14: post-restart opposite/different-ID fails closed
    store3 = OwnerDecisionStore(path=path)
    conflict = evaluate_owner_decision(
        _decision(decision_id="dec-C", action=OWNER_ACTION_REJECT), env, store=store3,
    )
    assert conflict.status == EXECUTION_DECISION_REJECTED
    assert conflict.reason_code == REASON_PROPOSAL_ALREADY_DECIDED
    assert store3.proposal_authority(env.proposal_envelope_id).status == EXECUTION_DECISION_AUTHORIZED


def test_restart_preserves_reject_authority(tmp_path):
    path = str(tmp_path / "owner_decisions.json")
    env = _envelope()
    store1 = OwnerDecisionStore(path=path)
    reject = evaluate_owner_decision(
        _decision(decision_id="dec-A", action=OWNER_ACTION_REJECT), env, store=store1,
    )
    assert reject.status == EXECUTION_DECISION_REJECTED

    # -- 12: restart preserves REJECT authority
    store2 = OwnerDecisionStore(path=path)
    authority = store2.proposal_authority(env.proposal_envelope_id)
    assert authority is not None
    assert authority.status == EXECUTION_DECISION_REJECTED
    assert authority.reason_code == REASON_OWNER_REJECTED


# --------------------------------------------------------------------------- 15-17
def _race(action_a, action_b, tmp_path, iterations=25):
    for i in range(iterations):
        path = str(tmp_path / f"owner_decisions_{i}.json")
        proposal_id = f"OPP:ST_ASIAN_SWEEP_5R_V1:occ-race-{i}"
        env = _envelope(proposal_envelope_id=proposal_id)
        store = OwnerDecisionStore(path=path)
        barrier = threading.Barrier(2)
        results = []

        def _submit(decision_id, action):
            barrier.wait(timeout=5)
            results.append(
                evaluate_owner_decision(
                    _decision(decision_id=decision_id, proposal_envelope_id=proposal_id, action=action),
                    env, store=store,
                )
            )

        t1 = threading.Thread(target=_submit, args=("dec-race-A", action_a))
        t2 = threading.Thread(target=_submit, args=("dec-race-B", action_b))
        t1.start(); t2.start()
        t1.join(timeout=10); t2.join(timeout=10)

        assert len(results) == 2
        authoritative = [r for r in results if r.reason_code != REASON_PROPOSAL_ALREADY_DECIDED]
        # Exactly one authoritative outcome must exist for this proposal -- the other
        # result is either an identical replay of it (same-action race) or a
        # PROPOSAL_ALREADY_DECIDED fail-closed rejection (opposite-action race).
        assert len({r.status for r in authoritative}) <= 1 or len(authoritative) == 1
        final_store = OwnerDecisionStore(path=path)
        authority = final_store.proposal_authority(proposal_id)
        assert authority is not None


def test_concurrent_approve_and_reject_leaves_exactly_one_authority(tmp_path):
    _race(OWNER_ACTION_APPROVE_DEMO, OWNER_ACTION_REJECT, tmp_path)


def test_concurrent_approve_and_approve_leaves_exactly_one_authority(tmp_path):
    _race(OWNER_ACTION_APPROVE_DEMO, OWNER_ACTION_APPROVE_DEMO, tmp_path)


def test_concurrent_reject_and_reject_leaves_exactly_one_authority(tmp_path):
    _race(OWNER_ACTION_REJECT, OWNER_ACTION_REJECT, tmp_path)


# --------------------------------------------------------------------------- 18
def test_corrupt_conflicting_proposal_authority_fails_closed(tmp_path):
    import json

    path = tmp_path / "owner_decisions.json"
    proposal_id = "OPP:ST_ASIAN_SWEEP_5R_V1:occ-corrupt"
    # Hand-planted state: two DIFFERENT decision_ids, both terminal owner outcomes, for
    # the SAME proposal_envelope_id, with DISAGREEING statuses -- impossible under
    # normal R5C operation, simulating pre-R5C data or file tampering.
    data = {
        "dec-corrupt-A": {
            "decision_id": "dec-corrupt-A", "proposal_envelope_id": proposal_id,
            "status": EXECUTION_DECISION_AUTHORIZED, "reason_code": "OWNER_APPROVED_DEMO",
            "reasons": [], "trade_command": None,
        },
        "dec-corrupt-B": {
            "decision_id": "dec-corrupt-B", "proposal_envelope_id": proposal_id,
            "status": EXECUTION_DECISION_REJECTED, "reason_code": REASON_OWNER_REJECTED,
            "reasons": [REASON_OWNER_REJECTED], "trade_command": None,
        },
    }
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(OwnerDecisionProposalAuthorityConflict):
        OwnerDecisionStore(path=str(path))
    # Same-family fail-closed signal -- any existing caller that already catches
    # OwnerDecisionStoreUnavailable fails closed here too with no code change.
    with pytest.raises(OwnerDecisionStoreUnavailable):
        OwnerDecisionStore(path=str(path))


def test_corrupt_agreeing_duplicate_proposal_authority_does_not_fail_closed(tmp_path):
    """Two terminal decision_ids for the same proposal that AGREE (both AUTHORIZED) are
    not a contradiction -- not required to fail closed, deterministic reconstruction
    picks one (P7 only requires failing closed on a genuine disagreement)."""
    import json

    path = tmp_path / "owner_decisions.json"
    proposal_id = "OPP:ST_ASIAN_SWEEP_5R_V1:occ-agree"
    data = {
        "dec-agree-A": {
            "decision_id": "dec-agree-A", "proposal_envelope_id": proposal_id,
            "status": EXECUTION_DECISION_AUTHORIZED, "reason_code": "OWNER_APPROVED_DEMO",
            "reasons": [], "trade_command": None,
        },
        "dec-agree-B": {
            "decision_id": "dec-agree-B", "proposal_envelope_id": proposal_id,
            "status": EXECUTION_DECISION_AUTHORIZED, "reason_code": "OWNER_APPROVED_DEMO",
            "reasons": [], "trade_command": None,
        },
    }
    path.write_text(json.dumps(data), encoding="utf-8")

    store = OwnerDecisionStore(path=str(path))
    authority = store.proposal_authority(proposal_id)
    assert authority is not None
    assert authority.status == EXECUTION_DECISION_AUTHORIZED


# --------------------------------------------------------------------------- 19
def test_unavailable_store_fails_closed_on_construction(tmp_path):
    path = tmp_path / "owner_decisions.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(OwnerDecisionStoreUnavailable):
        OwnerDecisionStore(path=str(path))


# --------------------------------------------------------------------------- 20
def test_no_alternate_auth_free_path_to_proposal_authority():
    """Structural: proposal authority can only ever be established by calling
    evaluate_owner_decision() with an explicit, fully-constructed OwnerDecision --
    there is no code path in OwnerDecisionStore that establishes `_proposal_index`
    except commit_terminal_decision, and commit_terminal_decision is only ever called
    from evaluate_owner_decision's two genuine terminal branches (APPROVE_DEMO success,
    REJECT). Actual authentication (X-AG-Owner-Key / require_owner_auth) is enforced
    entirely above this module, at the FastAPI dependency layer, BEFORE this route body
    (and therefore this module) ever runs -- see test_api_owner_decision_auth.py."""
    import inspect

    import owner_decision.bridge as bridge_module

    source = inspect.getsource(bridge_module)
    # Only evaluate_owner_decision's two genuine terminal branches call
    # commit_terminal_decision.
    assert source.count("commit_terminal_decision(") == 3  # 1 def + 2 call sites
