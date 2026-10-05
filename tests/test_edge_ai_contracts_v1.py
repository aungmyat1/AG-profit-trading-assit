from dataclasses import FrozenInstanceError
import json

import pytest

from contracts.v1 import (
    AccountState,
    ContractError,
    ExecutionRequest,
    ExecutionResult,
    MarketState,
    Opportunity,
    OwnerDecision,
    Proposal,
    ProposalEligibilityDecision,
    SemanticError,
)


def common(**overrides):
    values = {
        "schema_version": "1.0",
        "event_id": "event-1",
        "created_at": "2026-09-26T12:00:00Z",
        "source": "test.fixture",
        "correlation_id": "corr-1",
    }
    values.update(overrides)
    return values


def accepted_eligibility(opportunity_id="opp-1", **overrides):
    values = common(
        event_id="eligibility-1",
        opportunity_id=opportunity_id,
        eligible=True,
        reason_codes=("ELIGIBLE",),
        details={},
    )
    values.update(overrides)
    return ProposalEligibilityDecision(**values)


@pytest.mark.parametrize(
    "contract",
    [
        MarketState(
            **common(symbol="EURUSD", facts={"spread": 0.8, "session": "LONDON"})
        ),
        Opportunity(
            **common(
                symbol="EURUSD",
                opportunity_id="opp-1",
                strategy_id="s1",
                strategy_version="1.0",
                details={"side": "LONG"},
            )
        ),
        ProposalEligibilityDecision(
            **common(
                opportunity_id="opp-1",
                eligible=False,
                reason_codes=("ACCOUNT_BLOCKED",),
                details={},
            )
        ),
        Proposal(
            **common(
                symbol="EURUSD",
                opportunity_id="opp-1",
                strategy_id="s1",
                strategy_version="1.0",
                eligibility=accepted_eligibility(),
                details={"entry": 1.1},
            )
        ),
        OwnerDecision(
            **common(
                proposal_id="proposal-1",
                action="REJECT",
                owner_id="owner-1",
                reason_codes=("OWNER_REJECTED",),
            )
        ),
        ExecutionRequest(
            **common(
                symbol="EURUSD",
                proposal_id="proposal-1",
                owner_decision_id="decision-1",
                account_id="acct-1",
                mode="DEMO",
                idempotency_key="idem-1",
                request={},
            )
        ),
        ExecutionResult(
            **common(
                request_id="request-1",
                status="REJECTED",
                reason_codes=("GATE_CLOSED",),
                result={},
            )
        ),
        AccountState(
            **common(
                account_id="acct-1",
                broker="mt5.demo",
                currency="USD",
                state={"equity": 1000.0},
            )
        ),
        SemanticError(
            **common(
                code="NOT_ELIGIBLE",
                message="Proposal blocked",
                reason_codes=("RISK_LIMIT",),
                details={},
            )
        ),
    ],
)
def test_contract_round_trip_is_canonical(contract):
    encoded = contract.to_json()
    restored = type(contract).from_dict(json.loads(encoded))
    assert restored.to_json() == encoded
    assert restored.semantic_hash == contract.semantic_hash


def test_semantic_hash_ignores_event_provenance_but_changes_with_semantics():
    a = MarketState(**common(symbol="eurusd", facts={"spread": 0.8}))
    b = MarketState(
        **common(
            event_id="event-2",
            created_at="2026-09-26T13:00:00+01:00",
            correlation_id="corr-2",
            symbol="EURUSD",
            facts={"spread": 0.8},
        )
    )
    changed = MarketState(**common(symbol="EURUSD", facts={"spread": 0.9}))
    changed_symbol = MarketState(**common(symbol="GBPUSD", facts={"spread": 0.8}))
    assert a.semantic_hash == b.semantic_hash
    assert a.semantic_hash != changed.semantic_hash
    assert a.semantic_hash != changed_symbol.semantic_hash


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_non_finite_values_are_rejected(bad):
    with pytest.raises(ContractError, match="finite"):
        MarketState(**common(symbol="EURUSD", facts={"price": bad}))


@pytest.mark.parametrize(
    "timestamp", ["2026-09-26T12:00:00", "not-a-time", "2026-02-30T10:00:00Z"]
)
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
    contract = MarketState(
        **common(symbol="EURUSD", facts={"session": {"name": "LONDON"}})
    )
    with pytest.raises(FrozenInstanceError):
        contract.event_id = "changed"
    with pytest.raises(TypeError):
        contract.facts["new"] = True
    with pytest.raises(TypeError):
        contract.facts["session"]["name"] = "ASIA"


def test_market_state_schema_itself_cannot_be_extended_or_replaced():
    with pytest.raises(TypeError):
        MarketState._FACT_FIELDS["action"] = "string"
    with pytest.raises(TypeError):
        MarketState._NESTED_FACT_FIELDS["session"]["action"] = "string"
    with pytest.raises(AttributeError, match="immutable MarketState schema"):
        MarketState._FACT_FIELDS = {"action": "string"}
    with pytest.raises(AttributeError, match="immutable MarketState schema"):
        MarketState._NESTED_FACT_FIELDS = {"session": {"action": "string"}}


@pytest.mark.parametrize(
    "replacement",
    [
        {**MarketState._FACT_FIELDS, "action": "string"},
        {"action": "string"},
    ],
)
def test_market_state_subclasses_cannot_expand_or_replace_canonical_schema(replacement):
    with pytest.raises(TypeError, match="MarketState is final"):

        class ExtendedMarketState(MarketState):
            _FACT_FIELDS = replacement


@pytest.mark.parametrize(
    "field",
    [
        "desired_position",
        "trade_instruction",
        "broker_intent",
        "execution_intent",
        "owner_authorization",
        "target_lot",
    ],
)
def test_market_state_rejects_noncanonical_authority_aliases(field):
    with pytest.raises(ContractError, match="unsupported MarketState fact field"):
        MarketState(**common(symbol="EURUSD", facts={field: "BUY"}))


@pytest.mark.parametrize(
    "facts",
    [
        {"market_metadata": {"action": "BUY"}},
        {"session": {"name": "LONDON", "desired_position": "LONG"}},
        {"structure": {"trend_state": "BULLISH", "execution_intent": "BUY"}},
        {"liquidity": {"buy_side_level": 1.2, "broker_intent": "SELL"}},
        {"sweep": {"detected": True, "owner_authorization": True}},
        {"freshness": {"is_fresh": True, "trade_instruction": "BUY"}},
        {"provenance": {"provider": "feed-a", "target_lot": 0.1}},
    ],
)
def test_market_state_rejects_authority_smuggling_in_supported_nested_structures(facts):
    with pytest.raises(ContractError, match="unsupported MarketState fact field"):
        MarketState(**common(symbol="EURUSD", facts=facts))


def test_market_state_copies_input_before_freezing_nested_facts():
    source = {"session": {"name": "LONDON"}, "liquidity": {"buy_side_level": 1.2}}
    state = MarketState(**common(symbol="EURUSD", facts=source))
    source["session"]["name"] = "ASIA"
    source["liquidity"]["buy_side_level"] = 9.9
    assert state.facts["session"]["name"] == "LONDON"
    assert state.facts["liquidity"]["buy_side_level"] == 1.2


def test_symbol_provenance_and_semantic_hash_are_validated():
    with pytest.raises(ContractError, match="requires symbol"):
        MarketState(**common(facts={}))
    contract = MarketState(**common(symbol="EURUSD", facts={"spread": 1}))
    raw = contract.to_dict()
    raw["facts"]["spread"] = 2
    with pytest.raises(ContractError, match="semantic_hash"):
        MarketState.from_dict(raw)


@pytest.mark.parametrize(
    "facts",
    [
        {"symbol": "GBPUSD"},
        {"source": "different.feed"},
    ],
)
def test_market_state_rejects_symbol_or_source_provenance_mismatch(facts):
    with pytest.raises(ContractError, match="does not match"):
        MarketState(**common(symbol="EURUSD", facts=facts))


def test_opportunity_eligibility_and_proposal_are_distinct_types():
    opportunity = Opportunity(
        **common(
            symbol="EURUSD",
            opportunity_id="opp-1",
            strategy_id="s1",
            strategy_version="1.0",
            details={},
        )
    )
    rejected = ProposalEligibilityDecision(
        **common(
            opportunity_id=opportunity.opportunity_id,
            eligible=False,
            reason_codes=("STALE",),
            details={},
        )
    )
    assert isinstance(opportunity, Opportunity)
    assert isinstance(rejected, ProposalEligibilityDecision)
    assert not isinstance(rejected, Proposal)
    with pytest.raises(ContractError, match="reason_codes"):
        ProposalEligibilityDecision(
            **common(
                opportunity_id="opp-1", eligible=False, reason_codes=(), details={}
            )
        )


def test_proposal_requires_matching_accepted_eligibility_and_round_trips_binding():
    eligibility = accepted_eligibility("opp-1")
    proposal = Proposal(
        **common(
            symbol="EURUSD",
            opportunity_id="opp-1",
            strategy_id="s1",
            strategy_version="1.0",
            eligibility=eligibility,
            details={"entry": 1.1},
        )
    )
    restored = Proposal.from_dict(json.loads(proposal.to_json()))
    assert restored.eligibility == eligibility
    assert restored.eligibility.event_id == eligibility.event_id
    assert restored.eligibility.semantic_hash == eligibility.semantic_hash
    assert restored.semantic_hash == proposal.semantic_hash
    assert restored.to_json() == proposal.to_json()


def test_rejected_eligibility_cannot_construct_proposal():
    rejected = ProposalEligibilityDecision(
        **common(
            opportunity_id="opp-1",
            eligible=False,
            reason_codes=("STALE",),
            details={},
        )
    )
    with pytest.raises(ContractError, match="rejected eligibility"):
        Proposal(
            **common(
                symbol="EURUSD",
                opportunity_id="opp-1",
                strategy_id="s1",
                strategy_version="1.0",
                eligibility=rejected,
                details={},
            )
        )


def test_proposal_rejects_eligibility_for_different_opportunity():
    with pytest.raises(ContractError, match="opportunity_id does not match"):
        Proposal(
            **common(
                symbol="EURUSD",
                opportunity_id="opp-2",
                strategy_id="s1",
                strategy_version="1.0",
                eligibility=accepted_eligibility("opp-1"),
                details={},
            )
        )


def test_proposal_rejects_tampered_eligibility_hash_on_deserialization():
    proposal = Proposal(
        **common(
            symbol="EURUSD",
            opportunity_id="opp-1",
            strategy_id="s1",
            strategy_version="1.0",
            eligibility=accepted_eligibility(),
            details={},
        )
    )
    raw = proposal.to_dict()
    raw["eligibility"]["semantic_hash"] = "0" * 64
    with pytest.raises(ContractError, match="semantic_hash"):
        Proposal.from_dict(raw)


def test_proposal_rejects_tampered_eligibility_identity_on_deserialization():
    proposal = Proposal(
        **common(
            symbol="EURUSD",
            opportunity_id="opp-1",
            strategy_id="s1",
            strategy_version="1.0",
            eligibility=accepted_eligibility(),
            details={},
        )
    )
    raw = proposal.to_dict()
    raw["eligibility"]["event_id"] = "eligibility-tampered"
    with pytest.raises(ContractError, match="semantic_hash"):
        Proposal.from_dict(raw)


@pytest.mark.parametrize(
    "facts",
    [
        {"recommendation": "BUY"},
        {"recommendation": "SELL"},
        {"action": "BUY"},
        {"action": "ENTER"},
        {"signal": "SELL"},
        {"trade_signal": "BUY"},
        {"execution": "ENTER"},
        {"order": "BUY"},
        {"approved": True},
        {"risk_approved": True},
        {"owner_approved": True},
        {"approved_volume": 0.1},
        {"execution_command": "submit"},
        {"structure": {"recommendation": "BUY"}},
        {"structure": {"nested": {"signal": "SELL"}}},
        {"freshness": {"trade_signal": "BUY"}},
        {"structure": {"trend_state": "BUY"}},
        {"metadata": {"action": "SELL"}},
        {"extras": {"execute": True}},
        {"attributes": {"owner_confirmed": True}},
        {"payload": {"order_type": "BUY"}},
        {"context": {"position_size": 1}},
        {"tags": ["CONFIRM"]},
        {"custom": {"lot_size": 0.1}},
        {"extension": {"stop_loss": 1.0}},
        {"session": {"name": "LONDON", "metadata": {"action": "SELL"}}},
        {"provenance": {"provider": "feed-a", "custom": {"execute": True}}},
        {"action": "SELL"},
        {"execute": True},
        {"owner_confirmed": True},
        {"order_type": "BUY"},
        {"position_size": 1},
        {"lot_size": 0.1},
        {"risk_percent": 1.0},
        {"stop_loss": 1.0},
        {"take_profit": 2.0},
    ],
)
def test_market_state_cannot_encode_decision_or_execution_authority(facts):
    with pytest.raises(
        ContractError, match="unsupported MarketState fact field|invalid for"
    ):
        MarketState(**common(symbol="EURUSD", facts=facts))


def test_market_state_allows_only_typed_observable_fact_categories():
    state = MarketState(
        **common(
            symbol="EURUSD",
            facts={
                "session": {"name": "LONDON", "state": "OPEN", "high": 1.2},
                "spread": 0.8,
                "structure": {"trend_state": "BULLISH", "swing_high": 1.2},
                "liquidity": {"buy_side_level": 1.21},
                "sweep": {"detected": True, "liquidity_side": "BUY_SIDE", "price": 1.2},
                "freshness": {"is_fresh": True, "age_seconds": 0.5},
                "provenance": {"provider": "feed-a"},
            },
        )
    )
    assert state.facts["session"]["name"] == "LONDON"
    with pytest.raises(ContractError, match="unsupported MarketState fact field"):
        MarketState(**common(symbol="EURUSD", facts={"custom": {"price": 1.0}}))


def test_market_state_has_distinct_source_observation_and_creation_times():
    state = MarketState(
        **common(
            symbol="EURUSD",
            facts={
                "source_timestamp": "2026-09-26T11:59:58Z",
                "observed_at": "2026-09-26T12:00:00Z",
                "freshness": {"as_of": "2026-09-26T12:00:00Z", "age_seconds": 2.0},
            },
        )
    )
    assert state.facts["source_timestamp"] == "2026-09-26T11:59:58Z"
    assert state.facts["observed_at"] == "2026-09-26T12:00:00Z"
    assert state.created_at == "2026-09-26T12:00:00.000000Z"
    with pytest.raises(ContractError, match="invalid for timestamp"):
        MarketState(**common(symbol="EURUSD", facts={"source_timestamp": "not-a-time"}))


def test_market_state_accepts_producer_neutral_factual_inputs():
    facts = {
        "source_timestamp": "2026-09-26T11:59:58Z",
        "observed_at": "2026-09-26T12:00:00Z",
        "bid": 1.1,
        "ask": 1.1002,
        "structure": {"trend_state": "BULLISH"},
    }
    python_state = MarketState(
        **common(
            source="python.mt5",
            symbol="EURUSD",
            facts={
                **facts,
                "provenance": {"provider": "python.mt5", "feed": "terminal"},
            },
        )
    )
    mql5_state = MarketState(
        **common(
            source="mql5.indicators",
            symbol="EURUSD",
            facts={
                **facts,
                "provenance": {"provider": "mql5.indicators", "feed": "terminal"},
            },
        )
    )
    assert python_state.facts != mql5_state.facts
    assert python_state.semantic_hash == mql5_state.semantic_hash


def test_market_state_serialization_and_identity_ignore_fact_order():
    left = MarketState(
        **common(
            symbol="EURUSD",
            facts={
                "spread": 0.8,
                "structure": {"trend_state": "BULLISH", "swing_high": 1.2},
            },
        )
    )
    right = MarketState(
        **common(
            symbol="EURUSD",
            facts={
                "structure": {"swing_high": 1.2, "trend_state": "BULLISH"},
                "spread": 0.8,
            },
        )
    )
    assert left.to_json() == right.to_json()
    assert left.semantic_hash == right.semantic_hash
