"""Offline integration proof for the production pre-eligibility bridge.

An accepted ProposalEligibilityDecision in this file is an explicit test fixture for
the already-completed eligibility boundary; it is not a production policy or API.
"""
from __future__ import annotations

import ast
import dataclasses
import datetime as dt
from pathlib import Path

import pytest

from mt5.symbol_resolver import SymbolMeta
from opportunity.contracts import (
    ELIGIBILITY_BLOCKED, ELIGIBILITY_ELIGIBLE, MARKET_DATA_MODE_REPLAY,
    MARKET_DATA_MODE_SYNTHETIC, CandidateGeometry, MarketEvent, OpportunityCandidate,
    ProposalEligibilityDecision,
)
from opportunity.asian_sweep_adapter import AsianSweepFunnelAdapter
from opportunity.engine import evaluate_funnel
from opportunity.proposal_eligibility import evaluate_proposal_eligibility
from opportunity.registry_binding import StrategyBinding
from opportunity.stages import OUTCOME_ACTIVE, STAGE_ENTRY_CONFIRMED
from post_asian_pilot.decision import map_trade_signal_to_decision
from post_asian_pilot.orchestration_bridge import (
    STRATEGY_CONFIG_PATH, _build_after_accepted_eligibility,
    evaluate_marketstate_to_proposal,
)
from post_asian_pilot.pilot_config import DEFAULT_PILOT_CONFIG_PATH, load_pilot_config
from proposal_envelope.ledger import ProposalLedger, ProposalLedgerError
from proposal_envelope.adapters.opportunity_adapter import to_canonical_proposal
from proposal_envelope.formation_gate import apply_formation_gate
from proposal_envelope.models import PROPOSAL_BLOCKED, PROPOSAL_READY
from api.schemas import CanonicalProposalResponse
from strategy_contract.market_snapshot import MarketSnapshot
from strategy_engine.engine import evaluate
from strategy_engine.loader import load_strategy
from strategy_engine.session import Candle
from packages.contracts.v1 import ContractError, MarketState, SCHEMA_VERSION

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 22, 11, 15, tzinfo=UTC)
DAY = NOW.date()


def _bars(*, breach: bool = False) -> tuple[Candle, ...]:
    start = dt.datetime.combine(DAY, dt.time(0), tzinfo=UTC)
    candles = []
    for i in range(44):
        t = start + dt.timedelta(minutes=15 * i)
        if i < 24:
            candles.append(Candle(t, 1.1000, 1.1010, 1.0990, 1.1000, 100))
        elif breach and i == 24:
            candles.append(Candle(t, 1.1000, 1.1012, 1.0970, 1.0975, 150))
        else:
            candles.append(Candle(t, 1.1000, 1.1005, 1.0995, 1.1000, 100))
    return tuple(candles)


def _state(snapshot: MarketSnapshot) -> MarketState:
    return MarketState(
        schema_version=SCHEMA_VERSION, event_id="ms-event-1", created_at=NOW,
        source=snapshot.source, correlation_id="corr-bridge-1", symbol=snapshot.symbol,
        facts={"symbol": snapshot.symbol, "source": snapshot.source,
               "source_timestamp": snapshot.market_data_asof.isoformat(),
               "freshness": {"is_fresh": True, "as_of": snapshot.market_data_asof.isoformat(),
                             "closed_bar": True}},
    )


def _snapshot(candle: Candle, mode: str = "SYNTHETIC", fingerprint: str = "fingerprint-closed-bar") -> MarketSnapshot:
    close = candle.time + dt.timedelta(minutes=15)
    return MarketSnapshot(
        symbol="EURUSD", timeframe="M15", source="TEST_MT5_SOURCE", market_data_mode=mode,
        bar_open_time=candle.time, bar_close_time=close, market_data_asof=close,
        retrieved_at=NOW, is_closed=True, fingerprint=fingerprint,
    )


def _candidate(mode: str) -> tuple[OpportunityCandidate, ProposalEligibilityDecision]:
    binding = StrategyBinding(
        strategy_id="ST_ASIAN_SWEEP_5R_V1", semantic_version="1.1.1", engine_id="strategy_engine",
        engine_version=None, adapter_id=None, adapter_version=None, dispatchable=False,
        opportunity_authority=True, proposal_authority=False, execution_authority="NONE",
        live_observation_supported=True,
    )
    candidate = OpportunityCandidate(
        candidate_id=f"candidate-{mode.lower()}", occurrence_id=f"occ-{mode.lower()}",
        strategy_id=binding.strategy_id, strategy_version="1.1.1", strategy_engine_version=None,
        symbol="EURUSD", market="FX", venue="TEST_MT5_SOURCE", direction="LONG",
        detected_at=NOW, last_evaluated_at=NOW, expires_at=None,
        stage=STAGE_ENTRY_CONFIRMED, outcome=OUTCOME_ACTIVE, revision=1,
        geometry=CandidateGeometry(direction="LONG", entry=1.0990, invalidation=1.0970,
                                   targets=(1.1010,), estimated_rr=1.0),
        market_data_mode=mode, data_lineage=f"{mode}:explicit-test-fixture",
    )
    return candidate, evaluate_proposal_eligibility(candidate, binding, evaluated_at=NOW)


def test_no_setup_strategy_produces_no_opportunity_or_proposal():
    strategy = load_strategy(STRATEGY_CONFIG_PATH)
    candles = _bars()
    signal = evaluate(strategy, "ASIAN_LONDON", "EURUSD", DAY, candles[:24], 24, candles[24:])
    decision = map_trade_signal_to_decision(signal, "snapshot-test", NOW, NOW)
    assert strategy.version == "1.1.1"
    assert signal.reason_code == "NO_SETUP_BY_WINDOW_END"
    assert decision.status == "EXPIRED"


@pytest.mark.parametrize("mode,expected_reason", [
    (MARKET_DATA_MODE_SYNTHETIC, "SYNTHETIC_DATA_NOT_PROPOSAL_ELIGIBLE"),
    (MARKET_DATA_MODE_REPLAY, "REPLAY_DATA_NOT_BROKER_EXECUTABLE"),
])
def test_production_eligibility_firewalls_reject_before_risk(mode, expected_reason, monkeypatch):
    candidate, eligibility = _actual_candidate(_ready_decision(), mode)
    assert eligibility.status == ELIGIBILITY_BLOCKED
    assert expected_reason in eligibility.reason_codes
    called = False

    def risk_must_not_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("risk called after rejected eligibility")

    monkeypatch.setattr("post_asian_pilot.orchestration_bridge.build_entry_proposal", risk_must_not_run)
    assert candidate.market_data_mode == mode
    assert eligibility.status != ELIGIBILITY_ELIGIBLE
    assert called is False


def _ready_decision():
    strategy = load_strategy(STRATEGY_CONFIG_PATH)
    candles = _bars(breach=True)
    from post_asian_pilot.snapshot import build_asian_session_snapshot
    session = build_asian_session_snapshot(strategy.strategy_id, "EURUSD", DAY, "asian",
        candles[0].time, candles[24].time, candles[:24], 24, as_of=NOW,
        created_at_utc=NOW).snapshot
    return map_trade_signal_to_decision(
        evaluate(strategy, "ASIAN_LONDON", "EURUSD", DAY, candles[:24], 24, candles[24:]),
        session.snapshot_id, NOW, NOW + dt.timedelta(hours=1),
    )


def _actual_candidate(decision, mode, snapshot=None):
    binding = StrategyBinding(
        strategy_id="ST_ASIAN_SWEEP_5R_V1", semantic_version=None, engine_id="strategy_engine",
        engine_version=None, adapter_id=None, adapter_version=None, dispatchable=False,
        opportunity_authority=True, proposal_authority=False, execution_authority="NONE",
        live_observation_supported=True,
    )
    candle = _bars(breach=True)[24]
    snapshot = snapshot or _snapshot(candle, mode=mode, fingerprint="offline-fixture-fingerprint")
    event = MarketEvent(
        event_id="bridge-firewall-test", event_type="BAR_CLOSE", symbol="EURUSD", market="FX",
        venue="OFFLINE_FIXTURE", timeframe=snapshot.timeframe, bar_open_time=snapshot.bar_open_time,
        bar_close_time=snapshot.bar_close_time, market_data_asof=snapshot.market_data_asof,
        market_data_mode=mode, snapshot_fingerprint=snapshot.fingerprint, source=snapshot.source,
    )
    candidate, _ = evaluate_funnel(event=event, binding=binding,
        adapter=AsianSweepFunnelAdapter(decision, strategy_version="1.1.1"))
    return candidate, evaluate_proposal_eligibility(candidate, binding, evaluated_at=NOW)


def test_real_production_preeligibility_path_stops_before_risk(monkeypatch):
    candles = _bars(breach=True)
    decision = _ready_decision()
    called = False

    def risk_must_not_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("risk should be unreachable from replay-labeled data")

    monkeypatch.setattr("post_asian_pilot.orchestration_bridge.build_entry_proposal", risk_must_not_run)
    candidate, eligibility = _actual_candidate(decision, "REPLAY")
    assert candidate.market_data_mode == "REPLAY"
    assert eligibility.status == ELIGIBILITY_BLOCKED
    assert "REPLAY_DATA_NOT_BROKER_EXECUTABLE" in eligibility.reason_codes
    assert called is False


def test_rejected_eligibility_cannot_reach_private_risk_seam(monkeypatch):
    decision = _ready_decision()
    snapshot = _snapshot(_bars(breach=True)[24], mode="SYNTHETIC", fingerprint="offline-fixture-fingerprint")
    candidate, rejected = _actual_candidate(decision, "SYNTHETIC", snapshot)
    strategy = load_strategy(STRATEGY_CONFIG_PATH)
    called = False
    def forbidden_risk(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("rejected eligibility reached risk")
    monkeypatch.setattr("post_asian_pilot.orchestration_bridge.build_entry_proposal", forbidden_risk)
    result, reason = _build_after_accepted_eligibility(candidate, rejected, decision, strategy,
        equity=10_000, symbol_meta=SymbolMeta("EURUSD", .00001, 1, 100000, .01, 100, .01, 5),
        risk_per_trade_pct=.5, snapshot=snapshot, marketstate_event_id="ms", marketstate_semantic_hash="hash")
    assert result is None and reason == "ELIGIBILITY_NOT_ACCEPTED_FOR_CANDIDATE"
    assert called is False
    with pytest.raises(TypeError, match="typed ProposalEligibilityDecision"):
        _build_after_accepted_eligibility(candidate, True, decision, strategy,
            equity=10_000, symbol_meta=None, risk_per_trade_pct=.5, snapshot=snapshot,
            marketstate_event_id="ms", marketstate_semantic_hash="hash")


@pytest.mark.parametrize("candidate_mode", ["SYNTHETIC", "REPLAY"])
def test_nonreal_candidate_real_snapshot_mismatch_stops_before_risk(candidate_mode, monkeypatch):
    decision = _ready_decision()
    original = _snapshot(_bars(breach=True)[24], mode=candidate_mode,
                         fingerprint="offline-fixture-fingerprint")
    candidate, _ = _actual_candidate(decision, candidate_mode, original)
    mismatched_real_snapshot = dataclasses.replace(original, market_data_mode="REAL")
    called = False
    def forbidden_risk(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("provenance mismatch reached risk")
    monkeypatch.setattr("post_asian_pilot.orchestration_bridge.build_entry_proposal", forbidden_risk)
    accepted_fixture = ProposalEligibilityDecision(candidate.candidate_id, ELIGIBILITY_ELIGIBLE, (), NOW)
    with pytest.raises(ValueError, match="mode does not match"):
        _build_after_accepted_eligibility(candidate, accepted_fixture, decision,
            load_strategy(STRATEGY_CONFIG_PATH), equity=10_000,
            symbol_meta=SymbolMeta("EURUSD", .00001, 1, 100000, .01, 100, .01, 5),
            risk_per_trade_pct=.5, snapshot=mismatched_real_snapshot,
            marketstate_event_id="ms", marketstate_semantic_hash="hash")
    assert called is False


def test_real_candidate_snapshot_fingerprint_mismatch_stops_before_risk(monkeypatch):
    decision = _ready_decision()
    snapshot = _snapshot(_bars(breach=True)[24], mode="REAL", fingerprint="real-boundary-fingerprint")
    candidate, _ = _actual_candidate(decision, "REAL", snapshot)
    mismatched = dataclasses.replace(snapshot, fingerprint="other-bar-fingerprint")
    accepted_fixture = ProposalEligibilityDecision(candidate.candidate_id, ELIGIBILITY_ELIGIBLE, (), NOW)
    called = False
    def forbidden_risk(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("fingerprint mismatch reached risk")
    monkeypatch.setattr("post_asian_pilot.orchestration_bridge.build_entry_proposal", forbidden_risk)
    with pytest.raises(ValueError, match="fingerprint does not match"):
        _build_after_accepted_eligibility(candidate, accepted_fixture, decision,
            load_strategy(STRATEGY_CONFIG_PATH), equity=10_000,
            symbol_meta=SymbolMeta("EURUSD", .00001, 1, 100000, .01, 100, .01, 5),
            risk_per_trade_pct=.5, snapshot=mismatched,
            marketstate_event_id="ms", marketstate_semantic_hash="hash")
    assert called is False


def test_synthetic_marketstate_input_fails_closed_before_strategy():
    candles = _bars(breach=True)
    snapshot = _snapshot(candles[-1], mode="SYNTHETIC")
    state = _state(snapshot)
    with pytest.raises(ValueError, match="production orchestration requires REAL MarketSnapshot"):
        evaluate_marketstate_to_proposal(
            state, candles, snapshot, DAY, NOW, venue="OFFLINE_FIXTURE", equity=10_000,
            symbol_meta=SymbolMeta("EURUSD", 0.00001, 1.0, 100000, 0.01, 100.0, 0.01, 5),
        )


def test_offline_post_eligibility_integration_proof(tmp_path, monkeypatch):
    decision = _ready_decision()
    snapshot = _snapshot(_bars(breach=True)[24], mode="SYNTHETIC", fingerprint="offline-fixture-fingerprint")
    candidate, eligibility = _actual_candidate(decision, "SYNTHETIC", snapshot)
    # The test constructs this typed accepted decision as an upstream boundary fixture.
    eligibility_fixture = ProposalEligibilityDecision(
        candidate_id=candidate.candidate_id, status=ELIGIBILITY_ELIGIBLE,
        reason_codes=(), evaluated_at=NOW,
    )
    strategy = load_strategy(STRATEGY_CONFIG_PATH)
    assert decision.status == "READY" and eligibility.status == ELIGIBILITY_BLOCKED
    meta = SymbolMeta("EURUSD", 0.00001, 1.0, 100000, 0.01, 100.0, 0.01, 5)
    pilot = load_pilot_config(DEFAULT_PILOT_CONFIG_PATH)
    assert pilot.risk_per_trade_pct == 0.5
    from post_asian_pilot import orchestration_bridge
    old_builder = orchestration_bridge.build_entry_proposal
    risk_calls = 0
    def count_risk(*args, **kwargs):
        nonlocal risk_calls
        risk_calls += 1
        return old_builder(*args, **kwargs)
    monkeypatch.setattr(orchestration_bridge, "build_entry_proposal", count_risk)
    proposal, formation_reason = _build_after_accepted_eligibility(
        candidate, eligibility_fixture, decision, strategy, equity=10_000,
        symbol_meta=meta, risk_per_trade_pct=pilot.risk_per_trade_pct,
        snapshot=snapshot, marketstate_event_id="ms-event-1", marketstate_semantic_hash="semantic-hash",
    )
    assert formation_reason == "CANONICAL_FORMATION_REJECTED"
    assert risk_calls == 1
    assert proposal.proposal_state == PROPOSAL_BLOCKED
    assert proposal.data_provenance.market_data_mode == "SYNTHETIC"
    ledger = ProposalLedger(str(tmp_path / "offline-ledger.json"))
    with pytest.raises(ProposalLedgerError):
        ledger.record_proposal(proposal)
    stored = proposal
    assert stored.data_provenance.market_data_mode == "SYNTHETIC"  # fixture stays honestly labeled
    response = CanonicalProposalResponse(
        proposal_id=stored.proposal_envelope_id, strategy_id=stored.strategy_id,
        strategy_version=stored.strategy_version, symbol=stored.symbol, market=stored.market,
        direction=stored.direction, entry=stored.entry, stop=stored.stop, targets=list(stored.targets),
        watcher_state=stored.watcher_state, proposal_state=stored.proposal_state,
        execution_authority=stored.execution_authority,
        market_data_mode=stored.data_provenance.market_data_mode,
        market_data_source=stored.data_provenance.source,
        market_data_asof=stored.data_provenance.market_data_asof,
        market_data_fingerprint=stored.data_provenance.market_data_fingerprint,
        version=stored.version, reasons=list(stored.reasons),
    )
    assert response.execution_authority == "NONE"
    assert response.execution_eligible is False
    assert response.market_data_mode == "SYNTHETIC"


def test_accepted_main_production_composition_executes_without_broker_operations(tmp_path, monkeypatch):
    candles = _bars(breach=True)
    # Test double at the external market-truth boundary: candle values are synthetic;
    # this does NOT constitute or claim REAL MT5 evidence. It lets the production
    # composition exercise its accepted branch and REAL-only formation contract.
    snapshot = _snapshot(candles[-1], mode="REAL", fingerprint="mocked-real-boundary-fingerprint")
    state = _state(snapshot)
    ledger = ProposalLedger(str(tmp_path / "accepted-main-ledger.json"))
    from post_asian_pilot import orchestration_bridge
    monkeypatch.setattr(orchestration_bridge, "ProposalLedger", lambda: ledger)
    result = evaluate_marketstate_to_proposal(
        state, candles, snapshot, DAY, NOW, venue="MOCKED_MARKET_AUTHORITY",
        equity=10_000, symbol_meta=SymbolMeta("EURUSD", 0.00001, 1.0, 100000,
            0.01, 100.0, 0.01, 5),
    )
    assert result.decision.status == "READY"
    assert result.candidate is not None
    assert result.eligibility.status == ELIGIBILITY_ELIGIBLE
    assert result.risk_result_count == 1
    assert result.canonical_proposal.proposal_state == PROPOSAL_READY
    assert result.persisted_proposal.proposal_envelope_id == result.canonical_proposal.proposal_envelope_id
    assert ledger.get_proposal(result.persisted_proposal.proposal_envelope_id) is not None


@pytest.mark.parametrize("mode", ["SYNTHETIC", "REPLAY"])
def test_nonreal_marketstate_fails_before_risk_and_ledger(tmp_path, monkeypatch, mode):
    candles = _bars(breach=True)
    snapshot = _snapshot(candles[-1], mode=mode)
    state = _state(snapshot)
    ledger = ProposalLedger(str(tmp_path / f"{mode.lower()}-ledger.json"))
    called = False
    def forbidden_risk(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("nonreal MarketState reached risk")
    from post_asian_pilot import orchestration_bridge
    monkeypatch.setattr(orchestration_bridge, "build_entry_proposal", forbidden_risk)
    with pytest.raises(ValueError, match="production orchestration requires REAL MarketSnapshot"):
        evaluate_marketstate_to_proposal(state, candles, snapshot, DAY, NOW,
            venue="OFFLINE_FIXTURE", equity=10_000,
            symbol_meta=SymbolMeta("EURUSD", .00001, 1, 100000, .01, 100, .01, 5),
            proposal_ledger=ledger)
    assert called is False
    assert ledger.list_active_proposals() == []


def test_production_entrypoint_has_no_market_data_mode_override():
    entrypoint = __import__("inspect").signature(evaluate_marketstate_to_proposal)
    assert "market_data_mode" not in entrypoint.parameters


def test_marketstate_cannot_claim_unrecognized_market_data_mode():
    candles = _bars(breach=True)
    snapshot = _snapshot(candles[-1], mode="REAL")
    state = _state(snapshot)
    with pytest.raises(ContractError, match="unsupported MarketState fact field 'market_data_mode'"):
        MarketState(
            schema_version=SCHEMA_VERSION, event_id="ms-replay-label", created_at=NOW,
            source=snapshot.source, correlation_id="corr-replay-label", symbol=snapshot.symbol,
            facts={"symbol": snapshot.symbol, "source": snapshot.source,
                   "source_timestamp": snapshot.market_data_asof.isoformat(),
                   "market_data_mode": "REPLAY"},
        )


def test_risk_failure_fails_closed_without_proposal():
    decision = _ready_decision()
    snapshot = _snapshot(_bars(breach=True)[24], mode="SYNTHETIC", fingerprint="offline-fixture-fingerprint")
    candidate, _ = _actual_candidate(decision, "SYNTHETIC", snapshot)
    eligibility_fixture = ProposalEligibilityDecision(candidate_id=candidate.candidate_id,
        status=ELIGIBILITY_ELIGIBLE, reason_codes=(), evaluated_at=NOW)
    strategy = load_strategy(STRATEGY_CONFIG_PATH)
    meta = SymbolMeta("EURUSD", 0.00001, 1.0, 100000, 10.0, 100.0, 0.01, 5)
    result, reason = _build_after_accepted_eligibility(candidate, eligibility_fixture, decision, strategy,
        equity=10_000, symbol_meta=meta, risk_per_trade_pct=0.5, snapshot=snapshot,
        marketstate_event_id="ms-event-1", marketstate_semantic_hash="semantic-hash")
    assert result is None
    assert reason == "VOLUME_BELOW_MIN"


def test_test_acceptance_fixture_is_not_in_production_module():
    source = Path("src/post_asian_pilot/orchestration_bridge.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    names = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
    assert "ProposalEligibilityDecision" not in names
    public_functions = {node.name for node in functions if not node.name.startswith("_")}
    assert public_functions == {"evaluate_marketstate_to_proposal"}
    entrypoint = next(node for node in functions if node.name == "evaluate_marketstate_to_proposal")
    argument_names = {arg.arg for arg in (*entrypoint.args.posonlyargs, *entrypoint.args.args, *entrypoint.args.kwonlyargs)}
    assert "eligibility" not in argument_names
    assert "accepted_eligibility" not in argument_names
    production_helper = source.split("def _build_after_accepted_eligibility", 1)[1].split("def evaluate_marketstate_to_proposal", 1)[0]
    assert "def evaluate_marketstate_to_proposal" in source
    assert "ProposalEligibilityDecision(" not in production_helper
    assert "evaluate_proposal_eligibility(" not in production_helper
    assert "evaluate_proposal_eligibility" in source


def test_risk_policy_is_configured_and_no_offline_override_exists():
    assert load_pilot_config(DEFAULT_PILOT_CONFIG_PATH).risk_per_trade_pct == 0.5
    source = Path("src/post_asian_pilot/orchestration_bridge.py").read_text(encoding="utf-8")
    assert "allow_replay" not in source and "allow_synthetic" not in source


def test_downstream_result_is_deterministic_and_risk_called_once(monkeypatch):
    decision = _ready_decision()
    snapshot = _snapshot(_bars(breach=True)[24], mode="SYNTHETIC", fingerprint="offline-fixture-fingerprint")
    candidate, _ = _actual_candidate(decision, "SYNTHETIC", snapshot)
    eligibility = ProposalEligibilityDecision(candidate_id=candidate.candidate_id,
        status=ELIGIBILITY_ELIGIBLE, reason_codes=(), evaluated_at=NOW)
    strategy = load_strategy(STRATEGY_CONFIG_PATH)
    original = __import__("post_asian_pilot.orchestration_bridge", fromlist=["build_entry_proposal"]).build_entry_proposal
    calls = 0

    def counting_risk(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr("post_asian_pilot.orchestration_bridge.build_entry_proposal", counting_risk)
    kwargs = dict(equity=10_000, symbol_meta=SymbolMeta("EURUSD", 0.00001, 1.0, 100000,
        0.01, 100.0, 0.01, 5), risk_per_trade_pct=0.5,
        snapshot=snapshot, marketstate_event_id="ms-event-1",
        marketstate_semantic_hash="same-state")
    one, one_reason = _build_after_accepted_eligibility(candidate, eligibility, decision, strategy, **kwargs)
    two, two_reason = _build_after_accepted_eligibility(candidate, eligibility, decision, strategy, **kwargs)
    assert calls == 2  # exactly one authoritative sizing call per build
    assert one_reason == two_reason == "CANONICAL_FORMATION_REJECTED"
    assert one.proposal_state == PROPOSAL_BLOCKED and two.proposal_state == PROPOSAL_BLOCKED
    assert one.proposal_envelope_id == two.proposal_envelope_id
    assert one.entry == two.entry and one.stop == two.stop and one.targets == two.targets
    assert one.setup_evidence["risk_result"] == two.setup_evidence["risk_result"]
