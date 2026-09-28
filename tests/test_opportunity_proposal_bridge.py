"""WP-4 focused tests: proposal_envelope.adapters.opportunity_adapter.to_canonical_proposal.

Builds OpportunityCandidate/ProposalEligibilityDecision values directly, reusing the
same fixture style as tests/test_opportunity_proposal_eligibility.py (WP-3) -- no MT5, no
CandidateStore, no ProposalLedger, no registry file I/O.
"""
from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path

import pytest

from opportunity.contracts import (
    ELIGIBILITY_BLOCKED,
    ELIGIBILITY_ELIGIBLE,
    ELIGIBILITY_INCOMPLETE,
    MARKET_DATA_MODE_REAL,
    MARKET_DATA_MODE_SYNTHETIC,
    CandidateGeometry,
    OpportunityCandidate,
    ProposalEligibilityDecision,
)
from opportunity.proposal_eligibility import (
    REASON_MISSING_REQUIRED_INPUT,
    REASON_NOT_YET_READY,
    REASON_STRATEGY_NOT_REGISTERED,
    REASON_TERMINAL_CANDIDATE,
    evaluate_proposal_eligibility,
)
from opportunity.registry_binding import StrategyBinding
from opportunity.stages import OUTCOME_ACTIVE, OUTCOME_REJECT, STAGE_ENTRY_CONFIRMED, STAGE_TRIGGER_ARMED
from proposal_envelope.adapters.opportunity_adapter import (
    BRIDGE_VERSION,
    BridgeIdentityMismatch,
    UnsupportedEligibilityStatus,
    to_canonical_proposal,
)
from proposal_envelope.models import (
    AUTHORITY_NONE,
    PROPOSAL_BLOCKED,
    PROPOSAL_INCOMPLETE,
    PROPOSAL_READY,
    WATCHER_INVALIDATED,
    WATCHER_SETUP_QUALIFIED,
)
from proposal_envelope.strategy_authority import StrategyAuthority

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 22, 8, 15, 20, tzinfo=UTC)

STRATEGY_ID = "ST_ASIAN_SWEEP_5R_V1"
STRATEGY_VERSION = "1.1.1"


def _binding(**overrides) -> StrategyBinding:
    base = dict(
        strategy_id=STRATEGY_ID, semantic_version=STRATEGY_VERSION, engine_id="strategy_engine",
        engine_version=None, adapter_id=None, adapter_version=None, dispatchable=False,
        opportunity_authority=True, proposal_authority=False, execution_authority="NONE",
        live_observation_supported=True,
    )
    base.update(overrides)
    return StrategyBinding(**base)


def _geometry(**overrides) -> CandidateGeometry:
    base = dict(direction="BUY", entry=1.1000, invalidation=1.0950, targets=(1.1100,), estimated_rr=2.0)
    base.update(overrides)
    return CandidateGeometry(**base)


def _candidate(**overrides) -> OpportunityCandidate:
    base = dict(
        candidate_id="cand-1", occurrence_id="occ-1", strategy_id=STRATEGY_ID,
        strategy_version=STRATEGY_VERSION, strategy_engine_version=None, symbol="EURUSD",
        market="FX", venue="VANTAGE_DEMO_MT5", direction="BUY", detected_at=NOW,
        last_evaluated_at=NOW, expires_at=None, stage=STAGE_ENTRY_CONFIRMED, outcome=OUTCOME_ACTIVE,
        revision=1, geometry=_geometry(), market_data_mode=MARKET_DATA_MODE_REAL,
    )
    base.update(overrides)
    return OpportunityCandidate(**base)


def _eligibility(candidate: OpportunityCandidate, binding: StrategyBinding = None) -> ProposalEligibilityDecision:
    return evaluate_proposal_eligibility(candidate, binding or _binding(), evaluated_at=NOW)


def _authority(**overrides) -> StrategyAuthority:
    base = dict(
        strategy_id=STRATEGY_ID, semantic_version=STRATEGY_VERSION, lifecycle_stage="RESEARCH",
        demo_eligible=False, demo_authorized=False, live_authorized=False,
    )
    base.update(overrides)
    return StrategyAuthority(**base)


# ---------------------------------------------------------------------------
# 1. eligible candidate -> CanonicalProposal (PROPOSAL_READY)
# ---------------------------------------------------------------------------

def test_eligible_candidate_produces_proposal_ready():
    candidate = _candidate()
    proposal = to_canonical_proposal(candidate, _eligibility(candidate))
    assert proposal.proposal_state == PROPOSAL_READY
    assert proposal.watcher_state == WATCHER_SETUP_QUALIFIED


# ---------------------------------------------------------------------------
# 2. ineligible (BLOCKED) -> no PROPOSAL_READY envelope
# ---------------------------------------------------------------------------

def test_terminal_candidate_is_blocked_not_ready():
    candidate = _candidate(outcome=OUTCOME_REJECT)
    eligibility = _eligibility(candidate)
    proposal = to_canonical_proposal(candidate, eligibility)
    assert proposal.proposal_state == PROPOSAL_BLOCKED
    assert proposal.proposal_state != PROPOSAL_READY
    assert proposal.watcher_state == WATCHER_INVALIDATED
    assert REASON_TERMINAL_CANDIDATE in proposal.reasons


def test_not_yet_registered_strategy_is_blocked():
    candidate = _candidate()
    eligibility = _eligibility(candidate, _binding(opportunity_authority=False))
    proposal = to_canonical_proposal(candidate, eligibility)
    assert proposal.proposal_state == PROPOSAL_BLOCKED
    assert REASON_STRATEGY_NOT_REGISTERED in proposal.reasons


def test_incomplete_candidate_is_incomplete_not_ready():
    candidate = _candidate(stage=STAGE_TRIGGER_ARMED, geometry=None)
    eligibility = _eligibility(candidate)
    assert eligibility.status == ELIGIBILITY_INCOMPLETE
    proposal = to_canonical_proposal(candidate, eligibility)
    assert proposal.proposal_state == PROPOSAL_INCOMPLETE
    assert proposal.proposal_state != PROPOSAL_READY
    assert REASON_NOT_YET_READY in proposal.reasons


def test_incomplete_geometry_never_leaks_into_top_level_trade_plan():
    candidate = _candidate(geometry=CandidateGeometry(direction="BUY", entry=1.1, invalidation=None))
    eligibility = _eligibility(candidate)
    assert eligibility.status == ELIGIBILITY_INCOMPLETE
    assert REASON_MISSING_REQUIRED_INPUT in eligibility.reason_codes
    proposal = to_canonical_proposal(candidate, eligibility)
    assert proposal.entry is None
    assert proposal.stop is None
    assert proposal.targets == ()
    # partial geometry is still visible for audit, just not as the trade plan
    assert proposal.setup_evidence["candidate_geometry_entry"] == 1.1


# ---------------------------------------------------------------------------
# 3. malformed/unknown eligibility state -> no proposal, fail closed
# ---------------------------------------------------------------------------

def test_unknown_eligibility_status_fails_closed():
    candidate = _candidate()

    class _FakeDecision:
        candidate_id = candidate.candidate_id
        status = "SOMETHING_NEW"
        reason_codes = ()

    with pytest.raises(UnsupportedEligibilityStatus):
        to_canonical_proposal(candidate, _FakeDecision())


# ---------------------------------------------------------------------------
# 4/5. candidate decision identity + strategy identity/version retained
# ---------------------------------------------------------------------------

def test_candidate_and_strategy_identity_retained():
    candidate = _candidate()
    proposal = to_canonical_proposal(candidate, _eligibility(candidate))
    assert proposal.source_record_id == candidate.candidate_id
    assert proposal.strategy_id == candidate.strategy_id
    assert proposal.strategy_version == candidate.strategy_version
    assert proposal.identity_version == BRIDGE_VERSION


# ---------------------------------------------------------------------------
# 6. deterministic proposal identity
# ---------------------------------------------------------------------------

def test_same_occurrence_yields_same_proposal_identity():
    candidate = _candidate()
    first = to_canonical_proposal(candidate, _eligibility(candidate))
    second = to_canonical_proposal(candidate, _eligibility(candidate))
    assert first.proposal_envelope_id == second.proposal_envelope_id


def test_different_occurrence_yields_different_proposal_identity():
    a = _candidate(occurrence_id="occ-1")
    b = _candidate(occurrence_id="occ-2", candidate_id="cand-2")
    proposal_a = to_canonical_proposal(a, _eligibility(a))
    proposal_b = to_canonical_proposal(b, _eligibility(b))
    assert proposal_a.proposal_envelope_id != proposal_b.proposal_envelope_id


def test_same_occurrence_id_stable_across_blocked_and_ready_states():
    """One logical occurrence keeps the SAME proposal_envelope_id across its own BLOCKED
    -> READY lifecycle transitions (mirrors occurrence_identity_v1's own occurrence
    stability rule at the opportunity-candidate layer)."""
    incomplete = _candidate(stage=STAGE_TRIGGER_ARMED, geometry=None)
    ready = _candidate()
    incomplete_proposal = to_canonical_proposal(incomplete, _eligibility(incomplete))
    ready_proposal = to_canonical_proposal(ready, _eligibility(ready))
    assert incomplete_proposal.proposal_envelope_id == ready_proposal.proposal_envelope_id


# ---------------------------------------------------------------------------
# 7. missing required authority -> fail closed
# ---------------------------------------------------------------------------

def test_eligibility_identity_mismatch_fails_closed():
    candidate = _candidate()
    mismatched = ProposalEligibilityDecision(
        candidate_id="some-other-candidate", status=ELIGIBILITY_ELIGIBLE, evaluated_at=NOW,
    )
    with pytest.raises(BridgeIdentityMismatch):
        to_canonical_proposal(candidate, mismatched)


# ---------------------------------------------------------------------------
# 8. geometry mapped correctly
# ---------------------------------------------------------------------------

def test_geometry_mapped_correctly_on_ready():
    candidate = _candidate()
    proposal = to_canonical_proposal(candidate, _eligibility(candidate))
    assert proposal.direction == "BUY"
    assert proposal.entry == 1.1000
    assert proposal.stop == 1.0950
    assert proposal.targets == (1.1100,)
    assert proposal.expected_R == 2.0


# ---------------------------------------------------------------------------
# 9. no risk calculation
# ---------------------------------------------------------------------------

def test_execution_authority_always_none_regardless_of_strategy_authority():
    candidate = _candidate()
    proposal = to_canonical_proposal(
        candidate, _eligibility(candidate),
        strategy_authority=_authority(demo_authorized=True, live_authorized=True),
    )
    assert proposal.execution_authority == AUTHORITY_NONE


def test_no_strategy_authority_supplied_leaves_safe_defaults():
    candidate = _candidate()
    proposal = to_canonical_proposal(candidate, _eligibility(candidate))
    assert proposal.demo_authorized is False
    assert proposal.live_authorized is False
    assert proposal.economic_edge_established is False
    assert proposal.execution_eligible is False
    assert proposal.proposal_only is True
    assert proposal.broker_mutation_blocked is True


# ---------------------------------------------------------------------------
# 10/11. no TradeCommand, no MT5 interaction -- static import/name boundary
# ---------------------------------------------------------------------------

def test_module_never_imports_execution_or_mt5():
    path = (
        Path(__file__).resolve().parents[1] / "src" / "proposal_envelope" / "adapters"
        / "opportunity_adapter.py"
    )
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    forbidden_prefixes = ("execution", "mt5")
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            for forbidden in forbidden_prefixes:
                assert not name.startswith(forbidden), f"opportunity_adapter.py imports {name!r}"


def test_module_never_references_order_send_or_trade_command():
    path = (
        Path(__file__).resolve().parents[1] / "src" / "proposal_envelope" / "adapters"
        / "opportunity_adapter.py"
    )
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    forbidden_names = {"order_send", "order_check", "TradeCommand"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            continue
        name = None
        if isinstance(node, ast.Name):
            name = node.id
        elif isinstance(node, ast.Attribute):
            name = node.attr
        assert name not in forbidden_names, f"opportunity_adapter.py references {name!r}"


# ---------------------------------------------------------------------------
# Firewall / expiry pass-through (WP-3 reuse, not re-implemented here)
# ---------------------------------------------------------------------------

def test_synthetic_mode_blocked_candidate_maps_to_data_blocked_watcher_state():
    candidate = _candidate(market_data_mode=MARKET_DATA_MODE_SYNTHETIC)
    eligibility = _eligibility(candidate)
    assert eligibility.status == ELIGIBILITY_BLOCKED
    proposal = to_canonical_proposal(candidate, eligibility)
    assert proposal.proposal_state == PROPOSAL_BLOCKED
    from proposal_envelope.models import WATCHER_DATA_BLOCKED
    assert proposal.watcher_state == WATCHER_DATA_BLOCKED
