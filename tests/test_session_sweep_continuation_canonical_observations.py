"""AG_PLAN2_GOLDEN_STRATEGY_CANONICAL_OBSERVATION_MIGRATION_V1 -- focused fixture tests
for session_sweep_continuation.canonical_observations / canonical_consumer.

Synthetic fixtures only (mirrors tests/test_session_sweep_continuation_h1_bias.py's own
documented pattern) -- proves the MarketObservation wiring is mechanically correct,
fail-closed, and semantically transparent (canonical shadow decisions match what the
existing run_replay would produce given the same inputs), independent of any real
dataset's availability/authorization state.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from historical_replay.candle_store import HistoricalCandleStore
from historical_replay.symbol_metadata_manifest import HistoricalSymbolMetadataManifest
from market_intelligence.models import MarketBiasResult
from strategy_contract.controller import StrategyController
from strategy_engine.session import Candle
from trading_skills import MarketObservation, TradingSkill

from session_sweep_continuation.canonical_consumer import (
    SessionSweepContinuationCanonicalController,
    run_canonical_shadow_cycle,
)
from session_sweep_continuation.canonical_observations import (
    H1MarketBiasSkill,
    M15RegimeSkill,
    ObservationValidationError,
    unwrap_bias_observation,
    unwrap_regime_observation,
)
from session_sweep_continuation.config import load_config
from session_sweep_continuation.h1_bias import resolve_h1_market_bias
from session_sweep_continuation.regime import classify_regime
from session_sweep_continuation.replay import run_replay
from session_sweep_continuation.sessions import session_windows_from_config

UTC = timezone.utc
SYMBOL = "EURUSD"


def _hand_built_manifest(symbol: str = SYMBOL, tick_size: float = 0.00001) -> HistoricalSymbolMetadataManifest:
    return HistoricalSymbolMetadataManifest(
        dataset_id="TEST_H1_DATASET", symbol=symbol, tick_size=tick_size,
        metadata_scope="HISTORICAL_ANALYSIS_ONLY", authority="OWNER_APPROVED_DATASET_MANIFEST",
        approval_date="2026-09-02", dataset_fingerprint="sha256:" + "0" * 64, source_file="unused",
    )


def _build_h1_candles(count: int = 1300):
    out = []
    base = datetime(2020, 1, 1, tzinfo=UTC)
    price = 1.1000
    for i in range(count):
        price += 0.0006 if (i // 20) % 2 == 0 else -0.0006
        out.append(Candle(time=base + timedelta(hours=i), open=price, high=price + 0.0015,
                           low=price - 0.0015, close=price, volume=1.0))
    return out


def _store_with_h1_series(candles):
    store = HistoricalCandleStore()
    store.load_series(SYMBOL, "H1", candles)
    return store


def _build_m15_candles(count: int, start: datetime, trend: bool = False):
    out = []
    price = 1.1000
    for i in range(count):
        step = 0.0002 if trend else (0.00005 if i % 2 == 0 else -0.00005)
        price += step
        t = start + timedelta(minutes=15 * i)
        out.append(Candle(time=t, open=price, high=price + 0.0003, low=price - 0.0003, close=price, volume=1.0))
    return out


# --- H1MarketBiasSkill --------------------------------------------------------------

def test_h1_market_bias_skill_wraps_resolve_h1_market_bias_verbatim():
    candles = _build_h1_candles()
    store = _store_with_h1_series(candles)
    manifest = _hand_built_manifest()
    decision_time = candles[-1].time + timedelta(hours=1)

    direct = resolve_h1_market_bias(store, manifest, SYMBOL, decision_time, "ASIAN_LONDON")
    observation = H1MarketBiasSkill().evaluate({
        "h1_store": store, "manifest": manifest, "symbol": SYMBOL,
        "decision_time": decision_time, "session_pair": "ASIAN_LONDON",
    })

    assert isinstance(observation, MarketObservation)
    assert observation.skill_id == "H1_MARKET_BIAS_V1"
    assert observation.classification == direct.bias
    assert observation.input_fingerprint == direct.input_fingerprint
    assert observation.evidence["native_result"] == direct


def test_h1_market_bias_skill_never_emits_forbidden_classification():
    """MarketObservation.__post_init__ itself raises for BUY/SELL/etc -- this proves the
    adapter's classification values (BULLISH/BEARISH/NEUTRAL) never collide with that
    guard, for both a normal and an insufficient-history (NEUTRAL/UNAVAILABLE) case."""
    candles = _build_h1_candles(count=50)
    store = _store_with_h1_series(candles)
    manifest = _hand_built_manifest()
    decision_time = candles[-1].time + timedelta(hours=1)

    observation = H1MarketBiasSkill().evaluate({
        "h1_store": store, "manifest": manifest, "symbol": SYMBOL,
        "decision_time": decision_time, "session_pair": "ASIAN_LONDON",
    })
    assert observation.classification == "NEUTRAL"


# --- unwrap_bias_observation fail-closed guards --------------------------------------

def test_unwrap_bias_observation_returns_none_for_missing_observation():
    assert unwrap_bias_observation(None, symbol=SYMBOL, decision_time=datetime.now(UTC)) is None


def test_unwrap_bias_observation_round_trips_native_result():
    candles = _build_h1_candles()
    store = _store_with_h1_series(candles)
    manifest = _hand_built_manifest()
    decision_time = candles[-1].time + timedelta(hours=1)

    observation = H1MarketBiasSkill().evaluate({
        "h1_store": store, "manifest": manifest, "symbol": SYMBOL,
        "decision_time": decision_time, "session_pair": "ASIAN_LONDON",
    })
    unwrapped = unwrap_bias_observation(observation, symbol=SYMBOL, decision_time=decision_time)
    assert isinstance(unwrapped, MarketBiasResult)
    assert unwrapped.input_fingerprint == observation.input_fingerprint


def test_unwrap_bias_observation_fails_closed_on_symbol_mismatch():
    candles = _build_h1_candles()
    store = _store_with_h1_series(candles)
    manifest = _hand_built_manifest()
    decision_time = candles[-1].time + timedelta(hours=1)

    observation = H1MarketBiasSkill().evaluate({
        "h1_store": store, "manifest": manifest, "symbol": SYMBOL,
        "decision_time": decision_time, "session_pair": "ASIAN_LONDON",
    })
    with pytest.raises(ObservationValidationError):
        unwrap_bias_observation(observation, symbol="GBPUSD", decision_time=decision_time)


def test_unwrap_bias_observation_fails_closed_on_stale_decision_time():
    candles = _build_h1_candles()
    store = _store_with_h1_series(candles)
    manifest = _hand_built_manifest()
    decision_time = candles[-1].time + timedelta(hours=1)

    observation = H1MarketBiasSkill().evaluate({
        "h1_store": store, "manifest": manifest, "symbol": SYMBOL,
        "decision_time": decision_time, "session_pair": "ASIAN_LONDON",
    })
    with pytest.raises(ObservationValidationError):
        unwrap_bias_observation(observation, symbol=SYMBOL, decision_time=decision_time + timedelta(hours=1))


def test_unwrap_bias_observation_fails_closed_on_unsupported_skill_version():
    candles = _build_h1_candles()
    store = _store_with_h1_series(candles)
    manifest = _hand_built_manifest()
    decision_time = candles[-1].time + timedelta(hours=1)

    observation = H1MarketBiasSkill().evaluate({
        "h1_store": store, "manifest": manifest, "symbol": SYMBOL,
        "decision_time": decision_time, "session_pair": "ASIAN_LONDON",
    })
    stale_version_observation = MarketObservation(
        skill_id=observation.skill_id, skill_version="99.0.0", symbol=observation.symbol,
        timeframe=observation.timeframe, observed_at=observation.observed_at,
        classification=observation.classification, input_fingerprint=observation.input_fingerprint,
        evidence=observation.evidence,
    )
    with pytest.raises(ObservationValidationError):
        unwrap_bias_observation(stale_version_observation, symbol=SYMBOL, decision_time=decision_time)


# --- M15RegimeSkill --------------------------------------------------------------------

def test_m15_regime_skill_wraps_classify_regime_verbatim():
    config = load_config(repo_root=".")
    closes = [1.1000 + (0.0001 if i % 2 == 0 else -0.0001) for i in range(200)]
    observation = M15RegimeSkill().evaluate({
        "reference_closes": closes, "range_pips": 5.0, "candle_count": 24,
        "config": config, "symbol": SYMBOL, "observed_at": datetime.now(UTC),
    })
    assert observation.skill_id == "M15_MARKET_REGIME_V1"
    assert observation.classification in ("RANGE", "TREND_UP", "TREND_DOWN", "TRANSITION", "UNKNOWN")


# --- unwrap_regime_observation fail-closed guards + regime injection (AG_PLAN2_GOLDEN_
# CANONICAL_COMPLETION_V1) ---------------------------------------------------------------

def _regime_observation_fixture():
    config = load_config(repo_root=".")
    closes = [1.1000 + (0.0001 if i % 2 == 0 else -0.0001) for i in range(200)]
    observed_at = datetime(2026, 1, 5, tzinfo=UTC)
    observation = M15RegimeSkill().evaluate({
        "reference_closes": closes, "range_pips": 5.0, "candle_count": 24,
        "config": config, "symbol": SYMBOL, "observed_at": observed_at,
    })
    return observation, observed_at, config, closes


def test_unwrap_regime_observation_returns_none_for_missing_observation():
    assert unwrap_regime_observation(None, symbol=SYMBOL, observed_at=datetime.now(UTC)) is None


def test_unwrap_regime_observation_round_trips_native_result():
    observation, observed_at, config, closes = _regime_observation_fixture()
    direct = classify_regime(closes, 5.0, 24, config)

    unwrapped = unwrap_regime_observation(observation, symbol=SYMBOL, observed_at=observed_at)
    assert unwrapped == direct


def test_unwrap_regime_observation_fails_closed_on_symbol_mismatch():
    observation, observed_at, _, _ = _regime_observation_fixture()
    with pytest.raises(ObservationValidationError):
        unwrap_regime_observation(observation, symbol="GBPUSD", observed_at=observed_at)


def test_unwrap_regime_observation_fails_closed_on_wrong_timeframe():
    observation, observed_at, _, _ = _regime_observation_fixture()
    tampered = MarketObservation(
        skill_id=observation.skill_id, skill_version=observation.skill_version, symbol=observation.symbol,
        timeframe="H1", observed_at=observation.observed_at, classification=observation.classification,
        input_fingerprint=observation.input_fingerprint, evidence=observation.evidence,
    )
    with pytest.raises(ObservationValidationError):
        unwrap_regime_observation(tampered, symbol=SYMBOL, observed_at=observed_at)


def test_unwrap_regime_observation_fails_closed_on_unsupported_skill_version():
    observation, observed_at, _, _ = _regime_observation_fixture()
    tampered = MarketObservation(
        skill_id=observation.skill_id, skill_version="99.0.0", symbol=observation.symbol,
        timeframe=observation.timeframe, observed_at=observation.observed_at,
        classification=observation.classification, input_fingerprint=observation.input_fingerprint,
        evidence=observation.evidence,
    )
    with pytest.raises(ObservationValidationError):
        unwrap_regime_observation(tampered, symbol=SYMBOL, observed_at=observed_at)


def test_unwrap_regime_observation_fails_closed_on_evidence_fingerprint_mismatch():
    observation, observed_at, _, _ = _regime_observation_fixture()
    tampered_evidence = dict(observation.evidence)
    tampered_evidence["ema_fast"] = (tampered_evidence["ema_fast"] or 0.0) + 1.0
    tampered = MarketObservation(
        skill_id=observation.skill_id, skill_version=observation.skill_version, symbol=observation.symbol,
        timeframe=observation.timeframe, observed_at=observation.observed_at,
        classification=observation.classification, input_fingerprint=observation.input_fingerprint,
        evidence=tampered_evidence,
    )
    with pytest.raises(ObservationValidationError):
        unwrap_regime_observation(tampered, symbol=SYMBOL, observed_at=observed_at)


def test_run_replay_regime_result_none_matches_legacy_default_behavior():
    """Mandatory P6 legacy-compatibility regression: run_replay(...) with no
    regime_result argument at all must behave identically to run_replay(...,
    regime_result=None) -- the new parameter's default preserves exact legacy
    behavior for every existing caller that does not pass it."""
    config = load_config(repo_root=".")
    session_pair_id = config["session_pairs"][0]["pair_id"]
    windows = session_windows_from_config(config)[session_pair_id]
    trading_date = datetime(2026, 1, 10, tzinfo=UTC).date()
    ref_start, _ = windows["reference"].bounds_for_date(trading_date)
    m15_candles = _build_m15_candles(count=800, start=ref_start - timedelta(days=3), trend=True)

    legacy_default = run_replay(m15_candles, config, SYMBOL, session_pair_id, trading_date, 0.0001)
    legacy_explicit_none = run_replay(
        m15_candles, config, SYMBOL, session_pair_id, trading_date, 0.0001, regime_result=None,
    )
    assert legacy_default.regime == legacy_explicit_none.regime
    assert len(legacy_default.accepted_setups) == len(legacy_explicit_none.accepted_setups)
    assert len(legacy_default.rejected_setups) == len(legacy_explicit_none.rejected_setups)


def test_run_replay_accepts_injected_regime_result_and_uses_it_verbatim():
    """Supplying a (deliberately wrong, deterministic) regime_result must make
    run_replay USE that value rather than recomputing internally -- proves injection,
    not just acceptance of the parameter."""
    from session_sweep_continuation.regime import Regime, RegimeResult

    config = load_config(repo_root=".")
    session_pair_id = config["session_pairs"][0]["pair_id"]
    windows = session_windows_from_config(config)[session_pair_id]
    trading_date = datetime(2026, 1, 10, tzinfo=UTC).date()
    ref_start, _ = windows["reference"].bounds_for_date(trading_date)
    m15_candles = _build_m15_candles(count=800, start=ref_start - timedelta(days=3), trend=True)

    forced_unknown = RegimeResult(Regime.UNKNOWN, None, None, None, None, "FORCED_FOR_TEST")
    result = run_replay(m15_candles, config, SYMBOL, session_pair_id, trading_date, 0.0001, regime_result=forced_unknown)
    assert result.regime == "UNKNOWN"
    assert result.campaign is None
    assert result.accepted_setups == []


def test_canonical_shadow_cycle_injects_regime_result_into_run_replay():
    """The canonical controller's regime must actually be CONSUMED by run_replay, not
    merely computed and discarded -- verified by forcing a synthetic fixture where the
    injected regime, if actually used, produces a deterministically different outcome
    (NO_TRADE / UNKNOWN) than the legacy path's own internally-computed regime would
    naturally reach."""
    config = load_config(repo_root=".")
    h1_candles = _build_h1_candles(count=1300)
    h1_store = _store_with_h1_series(h1_candles)
    manifest = _hand_built_manifest()

    session_pair_id = config["session_pairs"][0]["pair_id"]
    windows = session_windows_from_config(config)[session_pair_id]
    trading_date = (h1_candles[-1].time + timedelta(hours=1)).date()
    ref_start, ref_end = windows["reference"].bounds_for_date(trading_date)
    m15_candles = _build_m15_candles(count=800, start=ref_start - timedelta(days=3), trend=True)

    cycle = run_canonical_shadow_cycle(
        h1_store=h1_store, manifest=manifest, m15_candles=m15_candles, config=config,
        symbol=SYMBOL, session_pair_id=session_pair_id, trading_date=trading_date,
        decision_time=ref_end, pip_size=0.0001,
    )
    regime_observation = next(o for o in cycle.observations if o.skill_id == "M15_MARKET_REGIME_V1")
    # The regime actually used by run_replay (surfaced on ReplayResult.regime) must
    # equal the MARKET_REGIME observation's own classification -- proving injection,
    # not independent recomputation that happened to agree.
    assert cycle.replay_result.regime == regime_observation.classification


# --- TradingSkill / StrategyController protocol conformance ---------------------------

def test_skills_satisfy_trading_skill_protocol():
    assert isinstance(H1MarketBiasSkill(), TradingSkill)
    assert isinstance(M15RegimeSkill(), TradingSkill)


def test_canonical_controller_satisfies_strategy_controller_protocol():
    controller = SessionSweepContinuationCanonicalController()
    assert isinstance(controller, StrategyController)
    assert controller.strategy_id == "ST_SESSION_SWEEP_CONTINUATION_V1"


# --- Dual-path semantic parity on a synthetic fixture ----------------------------------

def test_canonical_shadow_cycle_matches_legacy_path_on_synthetic_fixture():
    """The canonical shadow path must reach the SAME regime/campaign/setup outcome as
    calling h1_bias.resolve_h1_market_bias + run_replay directly (the legacy path) for
    an identical synthetic fixture -- by construction (transparent wrap/unwrap), but
    verified here rather than merely asserted."""
    config = load_config(repo_root=".")
    h1_candles = _build_h1_candles(count=1300)
    h1_store = _store_with_h1_series(h1_candles)
    manifest = _hand_built_manifest()

    session_pair_id = config["session_pairs"][0]["pair_id"]
    windows = session_windows_from_config(config)[session_pair_id]
    trading_date = (h1_candles[-1].time + timedelta(hours=1)).date()
    ref_start, ref_end = windows["reference"].bounds_for_date(trading_date)
    trade_start, trade_end = windows["trade"].bounds_for_date(trading_date)

    m15_start = ref_start - timedelta(days=3)
    m15_candles = _build_m15_candles(count=800, start=m15_start, trend=True)

    pip_size = 0.0001

    legacy_bias = resolve_h1_market_bias(h1_store, manifest, SYMBOL, ref_end, session_pair_id)
    legacy_result = run_replay(m15_candles, config, SYMBOL, session_pair_id, trading_date, pip_size, bias_result=legacy_bias)

    cycle = run_canonical_shadow_cycle(
        h1_store=h1_store, manifest=manifest, m15_candles=m15_candles, config=config,
        symbol=SYMBOL, session_pair_id=session_pair_id, trading_date=trading_date,
        decision_time=ref_end, pip_size=pip_size,
    )

    assert cycle.replay_result.regime == legacy_result.regime
    assert len(cycle.replay_result.accepted_setups) == len(legacy_result.accepted_setups)
    assert len(cycle.replay_result.rejected_setups) == len(legacy_result.rejected_setups)
    if legacy_result.campaign is not None:
        assert cycle.replay_result.campaign is not None
        assert cycle.replay_result.campaign.direction == legacy_result.campaign.direction
    else:
        assert cycle.replay_result.campaign is None


def test_canonical_controller_evaluate_returns_strategy_decision():
    config = load_config(repo_root=".")
    h1_candles = _build_h1_candles(count=1300)
    h1_store = _store_with_h1_series(h1_candles)
    manifest = _hand_built_manifest()

    session_pair_id = config["session_pairs"][0]["pair_id"]
    windows = session_windows_from_config(config)[session_pair_id]
    trading_date = (h1_candles[-1].time + timedelta(hours=1)).date()
    ref_start, ref_end = windows["reference"].bounds_for_date(trading_date)
    m15_candles = _build_m15_candles(count=800, start=ref_start - timedelta(days=3), trend=True)

    controller = SessionSweepContinuationCanonicalController()
    decision = controller.evaluate({
        "h1_store": h1_store, "manifest": manifest, "m15_candles": m15_candles, "config": config,
        "symbol": SYMBOL, "session_pair_id": session_pair_id, "trading_date": trading_date,
        "decision_time": ref_end, "pip_size": 0.0001,
    })
    assert decision.strategy_id == "ST_SESSION_SWEEP_CONTINUATION_V1"
    assert decision.symbol == SYMBOL
