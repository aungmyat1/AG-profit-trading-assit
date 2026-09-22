"""WP-3 focused tests: opportunity.proposal_eligibility.evaluate_proposal_eligibility.

Builds OpportunityCandidate/StrategyBinding values directly (no MT5, no
CandidateStore, no post_asian_pilot pipeline) -- the same fixture style
tests/test_opportunity_contracts.py and tests/test_opportunity_engine.py
already use for this package.
"""
from __future__ import annotations

import ast
import dataclasses
import datetime as dt
from pathlib import Path

import pytest

from opportunity.contracts import (
    ELIGIBILITY_BLOCKED,
    ELIGIBILITY_ELIGIBLE,
    ELIGIBILITY_INCOMPLETE,
    MARKET_DATA_MODE_REAL,
    MARKET_DATA_MODE_REPLAY,
    MARKET_DATA_MODE_SYNTHETIC,
    CandidateGeometry,
    OpportunityCandidate,
)
from opportunity.proposal_eligibility import (
    REASON_EXPIRED,
    REASON_MISSING_REQUIRED_INPUT,
    REASON_NOT_YET_READY,
    REASON_STRATEGY_IDENTITY_MISMATCH,
    REASON_STRATEGY_NOT_OPERATIONALLY_ENABLED,
    REASON_STRATEGY_NOT_REGISTERED,
    REASON_TERMINAL_CANDIDATE,
    REASON_UNSUPPORTED_STATE,
    evaluate_proposal_eligibility,
)
from opportunity.registry_binding import StrategyBinding
from opportunity.stages import (
    OUTCOME_ACTIVE,
    OUTCOME_ERROR,
    OUTCOME_EXPIRED,
    OUTCOME_INVALIDATED,
    OUTCOME_REJECT,
    OUTCOME_WAIT,
    STAGE_ENTRY_CONFIRMED,
    STAGE_MARKET_ELIGIBLE,
    STAGE_OPPORTUNITY_READY,
    STAGE_SETUP_DETECTED,
    STAGE_TRIGGER_ARMED,
)

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 21, 8, 15, 20, tzinfo=UTC)

STRATEGY_ID = "ST_ASIAN_SWEEP_5R_V1"
STRATEGY_VERSION = "1.1.1"


def _binding(**overrides) -> StrategyBinding:
    base = dict(
        strategy_id=STRATEGY_ID,
        semantic_version=STRATEGY_VERSION,
        engine_id="strategy_engine",
        engine_version=None,
        adapter_id=None,
        adapter_version=None,
        dispatchable=False,  # mirrors real registry_binding output for this strategy
        opportunity_authority=True,
        proposal_authority=False,
        execution_authority="NONE",
        live_observation_supported=True,
    )
    base.update(overrides)
    return StrategyBinding(**base)


def _geometry(**overrides) -> CandidateGeometry:
    base = dict(direction="BUY", entry=1.1000, invalidation=1.0950, targets=(), estimated_rr=None)
    base.update(overrides)
    return CandidateGeometry(**base)


def _candidate(**overrides) -> OpportunityCandidate:
    base = dict(
        candidate_id="cand-1",
        occurrence_id="occ-1",
        strategy_id=STRATEGY_ID,
        strategy_version=STRATEGY_VERSION,
        strategy_engine_version=None,
        symbol="EURUSD",
        market="FX",
        venue="VANTAGE_DEMO_MT5",
        direction="BUY",
        detected_at=NOW,
        last_evaluated_at=NOW,
        expires_at=None,
        stage=STAGE_ENTRY_CONFIRMED,
        outcome=OUTCOME_ACTIVE,
        revision=1,
        geometry=_geometry(),
        market_data_mode=MARKET_DATA_MODE_REAL,
    )
    base.update(overrides)
    return OpportunityCandidate(**base)


# ---------------------------------------------------------------------------
# 1. valid proposal-ready candidate -> eligible
# ---------------------------------------------------------------------------

def test_ready_active_candidate_with_full_geometry_is_eligible():
    decision = evaluate_proposal_eligibility(_candidate(), _binding(), evaluated_at=NOW)
    assert decision.status == ELIGIBILITY_ELIGIBLE
    assert decision.reason_codes == ()
    assert decision.candidate_id == "cand-1"


def test_eligible_at_opportunity_ready_stage_too():
    """A strategy whose adapter reaches the funnel's final stage (e.g. Large-SMC/
    SSC's own OPPORTUNITY_READY checkpoint) is equally eligible -- the rule is
    "at least ENTRY_CONFIRMED", not "exactly ENTRY_CONFIRMED"."""
    decision = evaluate_proposal_eligibility(
        _candidate(stage=STAGE_OPPORTUNITY_READY), _binding(), evaluated_at=NOW,
    )
    assert decision.status == ELIGIBILITY_ELIGIBLE


# ---------------------------------------------------------------------------
# 2. terminal candidate -> ineligible
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("outcome", [OUTCOME_REJECT, OUTCOME_INVALIDATED, OUTCOME_ERROR])
def test_terminal_outcome_is_blocked(outcome):
    decision = evaluate_proposal_eligibility(
        _candidate(outcome=outcome), _binding(), evaluated_at=NOW,
    )
    assert decision.status == ELIGIBILITY_BLOCKED
    assert REASON_TERMINAL_CANDIDATE in decision.reason_codes


# ---------------------------------------------------------------------------
# 3. expired/stale candidate -> ineligible where canonical authority supports it
# ---------------------------------------------------------------------------

def test_expired_outcome_is_blocked_with_expired_reason():
    decision = evaluate_proposal_eligibility(
        _candidate(outcome=OUTCOME_EXPIRED), _binding(), evaluated_at=NOW,
    )
    assert decision.status == ELIGIBILITY_BLOCKED
    assert decision.reason_codes == (REASON_EXPIRED,)


def test_expires_at_in_the_past_is_blocked():
    decision = evaluate_proposal_eligibility(
        _candidate(expires_at=NOW - dt.timedelta(minutes=1)), _binding(), evaluated_at=NOW,
    )
    assert decision.status == ELIGIBILITY_BLOCKED
    assert REASON_EXPIRED in decision.reason_codes


def test_expires_at_in_the_future_does_not_block():
    decision = evaluate_proposal_eligibility(
        _candidate(expires_at=NOW + dt.timedelta(minutes=1)), _binding(), evaluated_at=NOW,
    )
    assert decision.status == ELIGIBILITY_ELIGIBLE


# ---------------------------------------------------------------------------
# 4. WAIT/non-ready candidate -> ineligible
# ---------------------------------------------------------------------------

def test_wait_outcome_is_incomplete_not_blocked():
    decision = evaluate_proposal_eligibility(
        _candidate(outcome=OUTCOME_WAIT, geometry=None), _binding(), evaluated_at=NOW,
    )
    assert decision.status == ELIGIBILITY_INCOMPLETE
    assert decision.reason_codes == (REASON_NOT_YET_READY,)


@pytest.mark.parametrize("stage", [STAGE_MARKET_ELIGIBLE, STAGE_SETUP_DETECTED, STAGE_TRIGGER_ARMED])
def test_active_but_early_stage_is_incomplete(stage):
    decision = evaluate_proposal_eligibility(
        _candidate(stage=stage, geometry=None), _binding(), evaluated_at=NOW,
    )
    assert decision.status == ELIGIBILITY_INCOMPLETE
    assert decision.reason_codes == (REASON_NOT_YET_READY,)


# ---------------------------------------------------------------------------
# 5. DATA_ERROR/non-ready candidate -> ineligible
# ---------------------------------------------------------------------------

def test_data_error_style_candidate_is_incomplete():
    """Asian Sweep's own adapter projects DATA_ERROR as STAGE_MARKET_ELIGIBLE +
    OUTCOME_WAIT (never a terminal outcome) -- see asian_sweep_adapter._project_data_error.
    Exercised here at the OpportunityCandidate level this module actually consumes."""
    decision = evaluate_proposal_eligibility(
        _candidate(stage=STAGE_MARKET_ELIGIBLE, outcome=OUTCOME_WAIT, geometry=None,
                   raw_strategy_state={"reason_codes": ["MARKET_DATA_UNAVAILABLE"]}),
        _binding(), evaluated_at=NOW,
    )
    assert decision.status == ELIGIBILITY_INCOMPLETE


# ---------------------------------------------------------------------------
# 6. malformed/unknown state -> fail closed
# ---------------------------------------------------------------------------

def test_unknown_outcome_fails_closed():
    """OpportunityCandidate.__post_init__ enum-validates outcome, so a genuinely
    invalid value can never reach a real candidate. This proves the evaluator's
    own defensive fallback still fails closed if that ever changes, using a
    duck-typed stand-in that mimics the fields this module reads."""

    class _FakeCandidate:
        candidate_id = "cand-fake"
        strategy_id = STRATEGY_ID
        outcome = "SOMETHING_NEW"
        stage = STAGE_ENTRY_CONFIRMED
        expires_at = None
        market_data_mode = MARKET_DATA_MODE_REAL
        geometry = None

    decision = evaluate_proposal_eligibility(_FakeCandidate(), _binding(), evaluated_at=NOW)
    assert decision.status == ELIGIBILITY_BLOCKED
    assert decision.reason_codes == (REASON_UNSUPPORTED_STATE,)


# ---------------------------------------------------------------------------
# 7. disabled/non-operational strategy -> ineligible if registry authority applies
# ---------------------------------------------------------------------------

def test_strategy_not_registered_is_blocked():
    decision = evaluate_proposal_eligibility(
        _candidate(), _binding(opportunity_authority=False), evaluated_at=NOW,
    )
    assert decision.status == ELIGIBILITY_BLOCKED
    assert REASON_STRATEGY_NOT_REGISTERED in decision.reason_codes


def test_strategy_not_operationally_active_is_blocked():
    decision = evaluate_proposal_eligibility(
        _candidate(), _binding(live_observation_supported=False), evaluated_at=NOW,
    )
    assert decision.status == ELIGIBILITY_BLOCKED
    assert REASON_STRATEGY_NOT_OPERATIONALLY_ENABLED in decision.reason_codes


def test_strategy_identity_mismatch_is_blocked():
    decision = evaluate_proposal_eligibility(
        _candidate(strategy_id="SOME_OTHER_STRATEGY"), _binding(), evaluated_at=NOW,
    )
    assert decision.status == ELIGIBILITY_BLOCKED
    assert decision.reason_codes == (REASON_STRATEGY_IDENTITY_MISMATCH,)


def test_dispatchable_field_is_not_consulted():
    """binding.dispatchable is False for ST_ASIAN_SWEEP_5R_V1 in real registry_binding
    output (only SESSION_TRADE_V1 is dispatchable) -- this must never block eligibility."""
    decision = evaluate_proposal_eligibility(
        _candidate(), _binding(dispatchable=False, proposal_authority=False), evaluated_at=NOW,
    )
    assert decision.status == ELIGIBILITY_ELIGIBLE


# ---------------------------------------------------------------------------
# Synthetic/replay firewall (existing contracts.py authority, reused)
# ---------------------------------------------------------------------------

def test_synthetic_market_data_mode_is_blocked():
    decision = evaluate_proposal_eligibility(
        _candidate(market_data_mode=MARKET_DATA_MODE_SYNTHETIC), _binding(), evaluated_at=NOW,
    )
    assert decision.status == ELIGIBILITY_BLOCKED
    assert "SYNTHETIC_DATA_NOT_PROPOSAL_ELIGIBLE" in decision.reason_codes


def test_replay_market_data_mode_is_blocked():
    decision = evaluate_proposal_eligibility(
        _candidate(market_data_mode=MARKET_DATA_MODE_REPLAY), _binding(), evaluated_at=NOW,
    )
    assert decision.status == ELIGIBILITY_BLOCKED
    assert "REPLAY_DATA_NOT_BROKER_EXECUTABLE" in decision.reason_codes


# ---------------------------------------------------------------------------
# Missing required input (incomplete geometry)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "geometry",
    [
        None,
        CandidateGeometry(direction=None, entry=1.1, invalidation=1.09),
        CandidateGeometry(direction="BUY", entry=None, invalidation=1.09),
        CandidateGeometry(direction="BUY", entry=1.1, invalidation=None),
    ],
)
def test_incomplete_geometry_at_ready_stage_is_incomplete(geometry):
    decision = evaluate_proposal_eligibility(
        _candidate(geometry=geometry), _binding(), evaluated_at=NOW,
    )
    assert decision.status == ELIGIBILITY_INCOMPLETE
    assert decision.reason_codes == (REASON_MISSING_REQUIRED_INPUT,)


# ---------------------------------------------------------------------------
# 8. deterministic repeated evaluation
# ---------------------------------------------------------------------------

def test_repeated_evaluation_is_deterministic():
    candidate = _candidate()
    binding = _binding()
    first = evaluate_proposal_eligibility(candidate, binding, evaluated_at=NOW)
    second = evaluate_proposal_eligibility(candidate, binding, evaluated_at=NOW)
    assert first == second


# ---------------------------------------------------------------------------
# 9. no mutation of candidate identity/lifecycle
# ---------------------------------------------------------------------------

def test_candidate_is_not_mutated():
    candidate = _candidate()
    before = dataclasses.asdict(candidate)
    evaluate_proposal_eligibility(candidate, _binding(), evaluated_at=NOW)
    after = dataclasses.asdict(candidate)
    assert before == after


# ---------------------------------------------------------------------------
# 10/11/12. no CanonicalProposal creation, no ProposalLedger write, no MT5/execution reach
# ---------------------------------------------------------------------------

def test_module_never_imports_execution_mt5_or_proposal_construction():
    path = Path(__file__).resolve().parents[1] / "src" / "opportunity" / "proposal_eligibility.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    forbidden_prefixes = ("execution", "mt5", "proposal_envelope")
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            for forbidden in forbidden_prefixes:
                assert not name.startswith(forbidden), f"proposal_eligibility.py imports {name!r}"


def test_module_never_references_order_send_or_canonical_proposal_construction():
    """Checks actual code (Name/Attribute/Call nodes), not prose in the module's own
    docstring that merely discusses what this boundary must never do."""
    path = Path(__file__).resolve().parents[1] / "src" / "opportunity" / "proposal_eligibility.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    forbidden_names = {"order_send", "order_check", "CanonicalProposal", "ProposalLedger"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            continue  # docstrings/string literals are prose, not executable references
        name = None
        if isinstance(node, ast.Name):
            name = node.id
        elif isinstance(node, ast.Attribute):
            name = node.attr
        assert name not in forbidden_names, f"proposal_eligibility.py references {name!r}"


# ---------------------------------------------------------------------------
# 13. eligible does not imply execution authorization
# ---------------------------------------------------------------------------

def test_eligible_decision_carries_no_execution_authorization_field():
    decision = evaluate_proposal_eligibility(_candidate(), _binding(), evaluated_at=NOW)
    assert decision.status == ELIGIBILITY_ELIGIBLE
    field_names = {f.name for f in dataclasses.fields(decision)}
    assert "execution_authority" not in field_names
    assert "demo_authorized" not in field_names
    assert "live_authorized" not in field_names


def test_eligible_even_when_binding_reports_no_execution_authority():
    decision = evaluate_proposal_eligibility(
        _candidate(), _binding(execution_authority="NONE"), evaluated_at=NOW,
    )
    assert decision.status == ELIGIBILITY_ELIGIBLE
