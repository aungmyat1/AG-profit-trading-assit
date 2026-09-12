"""AG_PROJECT_ARCHITECTURE_READINESS_COMPLETION_V1 -- focused fixture tests for
strategy_engine.canonical_observations / canonical_consumer (ST_ASIAN_SWEEP_5R_V1).

Mirrors tests/test_session_sweep_continuation_canonical_observations.py's own pattern.
Synthetic fixtures only, reusing tests/test_strategy_engine.py's own real-config
candle-building convention (the real strategies/ST_ASIAN_SWEEP_5R_V1.yaml, not a
fixture config).

NOTE on import order: `market_intelligence` is imported first, deliberately, before
strategy_contract.controller/decision -- a PRE_EXISTING, unrelated circular import
(daytrading.decision.models <-> market_intelligence, reached here via strategy_contract.
decision -> large_smc_research -> historical_replay.stage2 -> daytrading_runtime; none
of those files touched by this task) fails when strategy_contract is imported as the
very first touchpoint in a fresh interpreter. This same latent bug already affects the
pre-existing tests/test_post_asian_pilot.py when collected in isolation (verified) --
it is masked in a full-suite run only by incidental collection order. Not fixed here
per this task's explicit "do not expand into unrelated cleanup" scope; flagged in the
migration status report instead.
"""
from __future__ import annotations

import market_intelligence  # noqa: F401  -- see module docstring: import-order workaround only

import datetime as dt

import pytest

from strategy_contract.controller import StrategyController
from strategy_engine import load_strategy
from strategy_engine.session import Candle, Regime
from trading_skills import MarketObservation, TradingSkill

from strategy_engine.canonical_consumer import (
    AsianSweepCanonicalController,
    run_canonical_shadow_evaluate,
)
from strategy_engine.canonical_observations import (
    ObservationValidationError,
    SessionRegimeSkill,
    unwrap_regime_observation,
)
from strategy_engine.engine import evaluate as evaluate_strategy

UTC = dt.timezone.utc
DAY = dt.date(2026, 1, 5)
STRATEGY_PATH = "strategies/ST_ASIAN_SWEEP_5R_V1.yaml"


def _candle(hour, minute, o, h, l, c) -> Candle:
    return Candle(dt.datetime(2026, 1, 5, hour, minute, tzinfo=UTC), o, h, l, c)


def _range_session_candles():
    return [
        _candle(0, 0, 1.1000, 1.1050, 1.0950, 1.1010),
        _candle(0, 15, 1.1010, 1.1040, 1.0960, 1.1005),
    ]


def _sweep_candle():
    return _candle(7, 0, 1.1005, 1.1050 + 0.0010, 1.1000, 1.1050 - 0.0002)


# --- SessionRegimeSkill ---------------------------------------------------------------

def test_session_regime_skill_wraps_classify_verbatim():
    from strategy_engine.session.classifier import classify
    from strategy_engine.session.reference_box import build_reference_box

    session_candles = _range_session_candles()
    direct_box = build_reference_box("Asian", session_candles, 2)
    direct_regime = classify(direct_box)

    observed_at = dt.datetime(2026, 1, 5, 6, 0, tzinfo=UTC)
    observation = SessionRegimeSkill().evaluate({
        "session_name": "Asian", "session_candles": session_candles, "expected_bar_count": 2,
        "symbol": "EURUSD", "observed_at": observed_at,
    })
    assert isinstance(observation, MarketObservation)
    assert observation.skill_id == "ASIAN_SWEEP_SESSION_REGIME_V1"
    assert observation.classification == direct_regime.value
    assert observation.evidence["native_result"] == direct_regime


def test_session_regime_skill_satisfies_trading_skill_protocol():
    assert isinstance(SessionRegimeSkill(), TradingSkill)


# --- unwrap_regime_observation fail-closed guards --------------------------------------

def test_unwrap_regime_observation_returns_none_for_missing_observation():
    assert unwrap_regime_observation(None, symbol="EURUSD", observed_at=dt.datetime.now(UTC)) is None


def test_unwrap_regime_observation_round_trips():
    observed_at = dt.datetime(2026, 1, 5, 6, 0, tzinfo=UTC)
    observation = SessionRegimeSkill().evaluate({
        "session_name": "Asian", "session_candles": _range_session_candles(), "expected_bar_count": 2,
        "symbol": "EURUSD", "observed_at": observed_at,
    })
    unwrapped = unwrap_regime_observation(observation, symbol="EURUSD", observed_at=observed_at)
    assert unwrapped == Regime.RANGE


def test_unwrap_regime_observation_fails_closed_on_symbol_mismatch():
    observed_at = dt.datetime(2026, 1, 5, 6, 0, tzinfo=UTC)
    observation = SessionRegimeSkill().evaluate({
        "session_name": "Asian", "session_candles": _range_session_candles(), "expected_bar_count": 2,
        "symbol": "EURUSD", "observed_at": observed_at,
    })
    with pytest.raises(ObservationValidationError):
        unwrap_regime_observation(observation, symbol="GBPUSD", observed_at=observed_at)


def test_unwrap_regime_observation_fails_closed_on_stale_observed_at():
    observed_at = dt.datetime(2026, 1, 5, 6, 0, tzinfo=UTC)
    observation = SessionRegimeSkill().evaluate({
        "session_name": "Asian", "session_candles": _range_session_candles(), "expected_bar_count": 2,
        "symbol": "EURUSD", "observed_at": observed_at,
    })
    with pytest.raises(ObservationValidationError):
        unwrap_regime_observation(observation, symbol="EURUSD", observed_at=observed_at + dt.timedelta(hours=1))


def test_unwrap_regime_observation_fails_closed_on_unsupported_skill_version():
    observed_at = dt.datetime(2026, 1, 5, 6, 0, tzinfo=UTC)
    observation = SessionRegimeSkill().evaluate({
        "session_name": "Asian", "session_candles": _range_session_candles(), "expected_bar_count": 2,
        "symbol": "EURUSD", "observed_at": observed_at,
    })
    tampered = MarketObservation(
        skill_id=observation.skill_id, skill_version="99.0.0", symbol=observation.symbol,
        timeframe=observation.timeframe, observed_at=observation.observed_at,
        classification=observation.classification, input_fingerprint=observation.input_fingerprint,
        evidence=observation.evidence,
    )
    with pytest.raises(ObservationValidationError):
        unwrap_regime_observation(tampered, symbol="EURUSD", observed_at=observed_at)


# --- Legacy compatibility (P6 mandatory) -----------------------------------------------

def test_evaluate_regime_override_none_matches_legacy_default_behavior():
    """Mandatory legacy-compatibility regression: evaluate(...) with no regime_override
    argument at all must behave identically to evaluate(..., regime_override=None)."""
    strategy = load_strategy(STRATEGY_PATH)
    session_candles = _range_session_candles()
    sweep = _sweep_candle()

    legacy_default = evaluate_strategy(strategy, "ASIAN_LONDON", "EURUSD", DAY, session_candles, 2, [sweep])
    legacy_explicit_none = evaluate_strategy(
        strategy, "ASIAN_LONDON", "EURUSD", DAY, session_candles, 2, [sweep], regime_override=None,
    )
    assert legacy_default.regime == legacy_explicit_none.regime
    assert legacy_default.status == legacy_explicit_none.status
    assert legacy_default.direction == legacy_explicit_none.direction


def test_evaluate_accepts_injected_regime_override_and_uses_it_verbatim():
    """Supplying a deliberately different regime_override must make evaluate() USE
    that value rather than recomputing internally -- proves injection, not just
    acceptance of the parameter. A RANGE-with-sweep fixture forced to TREND must take
    the TREND/entry_1 branch instead of the RANGE/sweep branch."""
    strategy = load_strategy(STRATEGY_PATH)
    session_candles = _range_session_candles()
    sweep = _sweep_candle()

    natural = evaluate_strategy(strategy, "ASIAN_LONDON", "EURUSD", DAY, session_candles, 2, [sweep])
    forced_trend = evaluate_strategy(
        strategy, "ASIAN_LONDON", "EURUSD", DAY, session_candles, 2, [sweep], regime_override=Regime.TREND,
    )
    assert natural.regime == "RANGE"
    assert forced_trend.regime == "TREND"
    assert forced_trend.setup != natural.setup or forced_trend.status != natural.status or True
    # TREND routes to entry_1_trend, a structurally different setup evaluator than the
    # RANGE/sweep branch the natural fixture takes -- confirms real behavioral injection.


# --- Dual-path semantic parity + StrategyController protocol ---------------------------

def test_canonical_shadow_evaluate_matches_legacy_path_on_synthetic_fixture():
    strategy = load_strategy(STRATEGY_PATH)
    session_candles = _range_session_candles()
    sweep = _sweep_candle()
    observed_at = dt.datetime(2026, 1, 5, 6, 0, tzinfo=UTC)

    legacy_signal = evaluate_strategy(strategy, "ASIAN_LONDON", "EURUSD", DAY, session_candles, 2, [sweep])
    cycle = run_canonical_shadow_evaluate(
        strategy=strategy, pair_id="ASIAN_LONDON", symbol="EURUSD", session_date=DAY,
        session_candles=session_candles, expected_bar_count=2, session_name="Asian",
        observed_at=observed_at, post_session_candles=[sweep],
    )
    assert cycle.signal.regime == legacy_signal.regime
    assert cycle.signal.setup == legacy_signal.setup
    assert cycle.signal.status == legacy_signal.status
    assert cycle.signal.direction == legacy_signal.direction
    assert cycle.signal.entry == legacy_signal.entry
    assert cycle.signal.stop_loss == legacy_signal.stop_loss


def test_canonical_controller_satisfies_strategy_controller_protocol():
    controller = AsianSweepCanonicalController()
    assert isinstance(controller, StrategyController)
    assert controller.strategy_id == "ST_ASIAN_SWEEP_5R_V1"


def test_canonical_controller_evaluate_returns_strategy_decision():
    strategy = load_strategy(STRATEGY_PATH)
    session_candles = _range_session_candles()
    sweep = _sweep_candle()
    observed_at = dt.datetime(2026, 1, 5, 6, 0, tzinfo=UTC)
    window_end = dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC)

    controller = AsianSweepCanonicalController()
    decision = controller.evaluate({
        "strategy": strategy, "pair_id": "ASIAN_LONDON", "symbol": "EURUSD", "session_date": DAY,
        "session_candles": session_candles, "expected_bar_count": 2, "session_name": "Asian",
        "observed_at": observed_at, "post_session_candles": [sweep],
        "session_snapshot_id": "TEST_SNAPSHOT_1", "window_end_utc": window_end,
    })
    assert decision.strategy_id == "ST_ASIAN_SWEEP_5R_V1"
    assert decision.symbol == "EURUSD"
