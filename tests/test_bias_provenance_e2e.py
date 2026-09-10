"""AG_UNIVERSAL_MARKET_DIRECTION_ARCHITECTURE_V1 M4 end-to-end tests (P21-P27).

Full chain, real code, no mocking of the resolver/router/workflow themselves:

    TieredStructureResult
        -> daytrading.decision.market_bias.derive_market_bias_from_tiers
           (delegates to market_intelligence.bias_resolver.resolve_from_structure_tiers)
        -> MarketBias (carries canonical_provenance)
        -> daytrading_workflow.session_workflow.evaluate_session_completion
           (via daytrading.decision.setup_router.route_daytrading_setup)
        -> SessionTradeProposal (carries bias_decision_cycle_id/bias_input_fingerprint/...)
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from daytrading.decision.market_bias import derive_market_bias_from_tiers  # noqa: E402
from daytrading_workflow.models import PROPOSAL_CONFLICT, PROPOSAL_NO_SETUP  # noqa: E402
from daytrading_workflow.session_workflow import (  # noqa: E402
    ProvenanceMismatchError, evaluate_session_completion, verify_bias_provenance_consistency,
)
from market_structure.models import STATE_BEARISH, STATE_BULLISH, STATE_UNDEFINED, StructureTier, TieredStructureResult  # noqa: E402
from strategy_engine.session import Candle  # noqa: E402

UTC = dt.timezone.utc
DAY = dt.date(2026, 1, 5)
DECISION_TIME = dt.datetime(2026, 1, 5, 6, 0, tzinfo=UTC)


def _candle(hour, minute, o, h, l, c):
    return Candle(dt.datetime(2026, 1, 5, hour, minute, tzinfo=UTC), o, h, l, c)


def _range_session_flat(n=24, price=1.1000):
    return [_candle(*divmod(15 * i, 60), price, price, price, price) for i in range(n)]


def _tiers(direction, status="VALID"):
    external = StructureTier(tier="EXTERNAL", swing_length=50, direction=direction, swings=(), events=())
    return TieredStructureResult(symbol="EURUSD", timeframe="H1", status=status, reason_codes=(), external=external)


def _bias(direction, decision_time=DECISION_TIME, session_pair="ASIAN"):
    return derive_market_bias_from_tiers(_tiers(direction), "H1", decision_time=decision_time, session_pair=session_pair)


# ---------------------------------------------------------------------------
# P21/P22 -- deterministic end-to-end trace + determinism.
# ---------------------------------------------------------------------------


def test_full_trace_preserves_provenance_through_setup_and_proposal():
    bias = _bias(STATE_BULLISH)
    assert bias.canonical_provenance is not None

    proposal = evaluate_session_completion(
        strategy_id="ST_TEST", symbol="EURUSD", reference_session="Asian", trading_date=DAY,
        session_candles=_range_session_flat(), expected_bar_count=24, market_bias=bias,
        evaluation_time=DECISION_TIME,
    )

    assert proposal.bias_decision_cycle_id == bias.canonical_provenance.decision_cycle_id
    assert proposal.bias_input_fingerprint == bias.canonical_provenance.input_fingerprint
    assert proposal.bias_model_version == bias.canonical_provenance.model_version
    assert proposal.bias_decision_time == bias.canonical_provenance.decision_time
    assert proposal.bias_reason_codes == bias.canonical_provenance.reason_codes


def test_determinism_same_evidence_same_provenance():
    bias_a = _bias(STATE_BULLISH)
    bias_b = _bias(STATE_BULLISH)
    assert bias_a.direction == bias_b.direction
    assert bias_a.canonical_provenance.input_fingerprint == bias_b.canonical_provenance.input_fingerprint
    assert bias_a.canonical_provenance.decision_cycle_id == bias_b.canonical_provenance.decision_cycle_id


# ---------------------------------------------------------------------------
# P23/P8 -- NEUTRAL short-circuits before setup evaluation, provenance still bound.
# ---------------------------------------------------------------------------


def test_neutral_short_circuits_to_no_setup_with_provenance_preserved():
    bias = _bias(STATE_UNDEFINED)  # genuinely undefined structure -> NEUTRAL
    assert bias.direction == "NEUTRAL"

    proposal = evaluate_session_completion(
        strategy_id="ST_TEST", symbol="EURUSD", reference_session="Asian", trading_date=DAY,
        session_candles=_range_session_flat(), expected_bar_count=24, market_bias=bias,
        evaluation_time=DECISION_TIME,
    )

    assert proposal.proposal_status == PROPOSAL_NO_SETUP
    assert proposal.direction is None
    # Still traceable, even though no trade was produced.
    assert proposal.bias_decision_cycle_id == bias.canonical_provenance.decision_cycle_id


# ---------------------------------------------------------------------------
# P24/P25/P9/P10 -- BULLISH permits only LONG, BEARISH permits only SHORT, end to end.
# ---------------------------------------------------------------------------


def test_bullish_bias_blocks_conflicting_short_setup_end_to_end():
    from strategy_engine.session import Direction, SetupType

    bias = _bias(STATE_BULLISH)
    assert bias.direction == "BULLISH"

    # A trending-bearish session (close well below open) -- TREND regime, SHORT direction.
    trend_bearish_candles = [
        _candle(*divmod(15 * i, 60), 1.1050 - i * 0.0005, 1.1052 - i * 0.0005, 1.1045 - i * 0.0005, 1.1045 - i * 0.0005)
        for i in range(24)
    ]

    proposal = evaluate_session_completion(
        strategy_id="ST_TEST", symbol="EURUSD", reference_session="Asian", trading_date=DAY,
        session_candles=trend_bearish_candles, expected_bar_count=24, market_bias=bias,
        evaluation_time=DECISION_TIME,
    )

    assert proposal.proposal_status == PROPOSAL_CONFLICT
    assert proposal.setup_type == SetupType.TREND.value
    assert proposal.direction == Direction.SHORT.value  # the setup's OWN direction, correctly not executed
    assert proposal.bias_decision_cycle_id == bias.canonical_provenance.decision_cycle_id  # still traceable


def test_bearish_bias_blocks_conflicting_long_setup_end_to_end():
    from strategy_engine.session import Direction, SetupType

    bias = _bias(STATE_BEARISH)
    assert bias.direction == "BEARISH"

    trend_bullish_candles = [
        _candle(*divmod(15 * i, 60), 1.1000 + i * 0.0005, 1.1055 + i * 0.0005, 1.0998 + i * 0.0005, 1.1050 + i * 0.0005)
        for i in range(24)
    ]

    proposal = evaluate_session_completion(
        strategy_id="ST_TEST", symbol="EURUSD", reference_session="Asian", trading_date=DAY,
        session_candles=trend_bullish_candles, expected_bar_count=24, market_bias=bias,
        evaluation_time=DECISION_TIME,
    )

    assert proposal.proposal_status == PROPOSAL_CONFLICT
    assert proposal.setup_type == SetupType.TREND.value
    assert proposal.direction == Direction.LONG.value
    assert proposal.bias_decision_cycle_id == bias.canonical_provenance.decision_cycle_id


# ---------------------------------------------------------------------------
# P26 -- cross-cycle mismatch fails closed.
# ---------------------------------------------------------------------------


def test_consistent_provenance_passes_verification():
    bias = _bias(STATE_BULLISH)
    proposal = evaluate_session_completion(
        strategy_id="ST_TEST", symbol="EURUSD", reference_session="Asian", trading_date=DAY,
        session_candles=_range_session_flat(), expected_bar_count=24, market_bias=bias,
        evaluation_time=DECISION_TIME,
    )
    from daytrading.decision.setup_router import route_daytrading_setup
    decision = route_daytrading_setup(
        "ST_TEST", "EURUSD", "Asian", DAY, _range_session_flat(), 24, bias, evaluation_time=DECISION_TIME,
    )
    verify_bias_provenance_consistency(decision, proposal)  # must not raise


def test_cross_cycle_mismatch_fails_closed():
    import dataclasses

    bias_a = _bias(STATE_BULLISH, decision_time=DECISION_TIME)
    bias_b = _bias(STATE_BULLISH, decision_time=DECISION_TIME + dt.timedelta(hours=1))  # different cycle

    proposal_a = evaluate_session_completion(
        strategy_id="ST_TEST", symbol="EURUSD", reference_session="Asian", trading_date=DAY,
        session_candles=_range_session_flat(), expected_bar_count=24, market_bias=bias_a,
        evaluation_time=DECISION_TIME,
    )
    from daytrading.decision.setup_router import route_daytrading_setup
    decision_b = route_daytrading_setup(
        "ST_TEST", "EURUSD", "Asian", DAY, _range_session_flat(), 24, bias_b, evaluation_time=DECISION_TIME,
    )

    with pytest.raises(ProvenanceMismatchError):
        verify_bias_provenance_consistency(decision_b, proposal_a)  # decision from cycle B, proposal from cycle A


# ---------------------------------------------------------------------------
# P27 -- resolver invoked exactly once per decision cycle.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# P17 -- proposal builder never resolves bias itself.
# ---------------------------------------------------------------------------


def test_proposal_builder_does_not_import_bias_resolver():
    import ast
    path = REPO_ROOT / "src" / "daytrading_workflow" / "session_workflow.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert not any(m == "market_intelligence" or m.startswith("market_intelligence.") for m in imported)
    assert not any("bias_resolver" in m for m in imported)


def test_resolver_invoked_exactly_once_per_cycle(monkeypatch):
    import market_intelligence.bias_resolver as resolver_module

    call_count = {"n": 0}
    real = resolver_module.resolve_from_structure_tiers

    def counting_wrapper(*args, **kwargs):
        call_count["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(resolver_module, "resolve_from_structure_tiers", counting_wrapper)
    # Re-import market_bias's already-bound reference so the monkeypatch takes effect --
    # it was imported by name (`from market_intelligence.bias_resolver import
    # resolve_from_structure_tiers`), so patch it there too.
    import daytrading.decision.market_bias as market_bias_module
    monkeypatch.setattr(market_bias_module, "resolve_from_structure_tiers", counting_wrapper)

    bias = market_bias_module.derive_market_bias_from_tiers(_tiers(STATE_BULLISH), "H1", decision_time=DECISION_TIME)
    assert call_count["n"] == 1

    # setup_router / evaluate_session_completion never call the resolver again for the
    # same already-resolved bias.
    evaluate_session_completion(
        strategy_id="ST_TEST", symbol="EURUSD", reference_session="Asian", trading_date=DAY,
        session_candles=_range_session_flat(), expected_bar_count=24, market_bias=bias,
        evaluation_time=DECISION_TIME,
    )
    assert call_count["n"] == 1
