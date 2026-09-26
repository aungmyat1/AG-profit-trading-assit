from dataclasses import FrozenInstanceError
import json

import pytest

from packages.contracts.v1 import (
    AccountState, ContractError, ExecutionRequest, ExecutionResult, MarketState,
    Opportunity, OwnerDecision, Proposal, ProposalEligibilityDecision, SemanticError,
)


def common(**overrides):
    values = {
        "schema_version": "1.0", "event_id": "event-1",
        "created_at": "2026-09-26T12:00:00Z", "source": "test.fixture",
        "correlation_id": "corr-1",
    }
    values.update(overrides)
    return values


@pytest.mark.parametrize("contract", [
    MarketState(**common(symbol="EURUSD", facts={"spread": 0.8, "session": "LONDON"})),
    Opportunity(**common(symbol="EURUSD", opportunity_id="opp-1", strategy_id="s1", strategy_version="1.0", details={"side": "LONG"})),
    ProposalEligibilityDecision(**common(opportunity_id="opp-1", eligible=False, reason_codes=("ACCOUNT_BLOCKED",), details={})),
    Proposal(**common(symbol="EURUSD", opportunity_id="opp-1", strategy_id="s1", strategy_version="1.0", details={"entry": 1.1})),
    OwnerDecision(**common(proposal_id="proposal-1", action="REJECT", owner_id="owner-1", reason_codes=("OWNER_REJECTED",))),
    ExecutionRequest(**common(symbol="EURUSD", proposal_id="proposal-1", owner_decision_id="decision-1", account_id="acct-1", mode="DEMO", idempotency_key="idem-1", request={})),
    ExecutionResult(**common(request_id="request-1", status="REJECTED", reason_codes=("GATE_CLOSED",), result={})),
    AccountState(**common(account_id="acct-1", broker="mt5.demo", currency="USD", state={"equity": 1000.0})),
    SemanticError(**common(code="NOT_ELIGIBLE", message="Proposal blocked", reason_codes=("RISK_LIMIT",), details={})),
])
def test_contract_round_trip_is_canonical(contract):
    encoded = contract.to_json()
    restored = type(contract).from_dict(json.loads(encoded))
    assert restored.to_json() == encoded
    assert restored.semantic_hash == contract.semantic_hash


def test_semantic_hash_ignores_event_provenance_but_changes_with_semantics():
    a = MarketState(**common(symbol="eurusd", facts={"spread": 0.8}))
    b = MarketState(**common(event_id="event-2", created_at="2026-09-26T13:00:00+01:00", correlation_id="corr-2", symbol="EURUSD", facts={"spread": 0.8}))
    changed = MarketState(**common(symbol="EURUSD", facts={"spread": 0.9}))
    changed_symbol = MarketState(**common(symbol="GBPUSD", facts={"spread": 0.8}))
    assert a.semantic_hash == b.semantic_hash
    assert a.semantic_hash != changed.semantic_hash
    assert a.semantic_hash != changed_symbol.semantic_hash


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_non_finite_values_are_rejected(bad):
    with pytest.raises(ContractError, match="finite"):
        MarketState(**common(symbol="EURUSD", facts={"price": bad}))


@pytest.mark.parametrize("timestamp", ["2026-09-26T12:00:00", "not-a-time", "2026-02-30T10:00:00Z"])
def test_malformed_or_timezone_naive_timestamp_is_rejected(timestamp):
    with pytest.raises(ContractError, match="created_at"):
        MarketState(**common(symbol="EURUSD", created_at=timestamp, facts={}))


def test_schema_version_is_explicit_and_unknown_versions_fail_closed():
    contract = MarketState(**common(symbol="EURUSD", facts={}))
    raw = contract.to_dict()
    raw["schema_version"] = "2.0"
    with pytest.raises(ContractError, match="schema_version"):
        MarketState.from_dict(raw)
    with pytest.raises(ContractError, match="schema_version"):
        MarketState(**common(schema_version="2.0", symbol="EURUSD", facts={}))


def test_identity_and_nested_semantics_are_immutable():
    contract = MarketState(**common(symbol="EURUSD", facts={"session": {"name": "LONDON"}}))
    with pytest.raises(FrozenInstanceError):
        contract.event_id = "changed"
    with pytest.raises(TypeError):
        contract.facts["new"] = True
    with pytest.raises(TypeError):
        contract.facts["session"]["name"] = "ASIA"


def test_symbol_provenance_and_semantic_hash_are_validated():
    with pytest.raises(ContractError, match="requires symbol"):
        MarketState(**common(facts={}))
    contract = MarketState(**common(symbol="EURUSD", facts={"spread": 1}))
    raw = contract.to_dict()
    raw["facts"]["spread"] = 2
    with pytest.raises(ContractError, match="semantic_hash"):
        MarketState.from_dict(raw)


@pytest.mark.parametrize("facts", [
    {"symbol": "GBPUSD"}, {"source": "different.feed"},
])
def test_market_state_rejects_symbol_or_source_provenance_mismatch(facts):
    with pytest.raises(ContractError, match="does not match"):
        MarketState(**common(symbol="EURUSD", facts=facts))


def test_opportunity_eligibility_and_proposal_are_distinct_types():
    opportunity = Opportunity(**common(symbol="EURUSD", opportunity_id="opp-1", strategy_id="s1", strategy_version="1.0", details={}))
    rejected = ProposalEligibilityDecision(**common(opportunity_id=opportunity.opportunity_id, eligible=False, reason_codes=("STALE",), details={}))
    assert isinstance(opportunity, Opportunity)
    assert isinstance(rejected, ProposalEligibilityDecision)
    assert not isinstance(rejected, Proposal)
    with pytest.raises(ContractError, match="reason_codes"):
        ProposalEligibilityDecision(**common(opportunity_id="opp-1", eligible=False, reason_codes=(), details={}))


@pytest.mark.parametrize("facts", [
    {"direction": "BUY"}, {"approved_volume": 0.1}, {"execution_command": "submit"},
    {"risk_approval": True}, {"owner_approval": True}, {"structure": {"decision": "SELL"}},
])
def test_market_state_cannot_encode_decision_or_execution_authority(facts):
    with pytest.raises(ContractError, match="authority fields"):
        MarketState(**common(symbol="EURUSD", facts=facts))
