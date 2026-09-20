from datetime import date, datetime, timezone
from unittest.mock import patch

import MetaTrader5 as mt5
import pytest

from historical_replay import HistoricalCandleStore, ReplayEvaluationContext
from historical_replay.utc_export_csv_loader import load_utc_export_csv
from market_intelligence import (SSCCompatibilityError, build_ssc_compatibility_context,
                                  compose_market_intelligence)
from session_sweep_continuation.canonical_observations import H1MarketBiasSkill, M15RegimeSkill, unwrap_bias_observation, unwrap_regime_observation
from session_sweep_continuation.config import load_config
from session_sweep_continuation.replay import run_replay
from session_sweep_continuation.sessions import build_reference_session, session_windows_from_config

UTC = timezone.utc
ROOT = "data/research/ssc_fresh_dev/SSC_V1_0_1_G2_DEV_002/raw/"
DAY = date(2026, 6, 23)
T = datetime(2026, 6, 23, 11, tzinfo=UTC)
REFERENCE_T = datetime(2026, 6, 23, 6, tzinfo=UTC)


def _event():
    store = HistoricalCandleStore()
    loaded = {}
    for tf in ("H1", "M15", "M1"):
        loaded[tf], _ = load_utc_export_csv(ROOT + f"EURUSD_{tf}.csv", "EURUSD", tf)
        store.load_series("EURUSD", tf, loaded[tf])
    return store, loaded, ReplayEvaluationContext.create(store, "EURUSD", T, ("H1", "M15", "M1"))


def _evidence(store, loaded):
    config = load_config()
    bias_obs = H1MarketBiasSkill().evaluate({
        "h1_store": store, "manifest": __import__("historical_replay.symbol_metadata_manifest", fromlist=["load_symbol_metadata_manifest"]).load_symbol_metadata_manifest("config/historical_datasets/EURUSD_H1_SSC_G2_DEV_002_symbol_metadata.yaml"),
        "symbol": "EURUSD", "decision_time": REFERENCE_T, "session_pair": "ASIAN_LONDON",
    })
    bias = unwrap_bias_observation(bias_obs, symbol="EURUSD", decision_time=REFERENCE_T)
    windows = session_windows_from_config(config)["ASIAN_LONDON"]
    reference = build_reference_session(loaded["M15"], windows["reference"], DAY, REFERENCE_T, .0001)
    regime_obs = M15RegimeSkill().evaluate({
        "reference_closes": [c.close for c in loaded["M15"] if c.time < T],
        "range_pips": reference.range_pips, "candle_count": reference.candle_count,
        "config": config, "symbol": "EURUSD", "observed_at": REFERENCE_T,
    })
    return config, bias, unwrap_regime_observation(regime_obs, symbol="EURUSD", observed_at=REFERENCE_T)


def test_mi_backed_context_matches_legacy_ssc_inputs_and_decision():
    store, loaded, replay = _event()
    config, bias, regime = _evidence(store, loaded)
    mi = compose_market_intelligence(replay, sessions={"reference": "canonical"},
                                     higher_timeframe_context={"h1_bias": bias})
    compat = build_ssc_compatibility_context(mi, replay, bias_result=bias, regime_result=regime)
    legacy = run_replay(tuple(loaded["M15"]), config, "EURUSD", "ASIAN_LONDON", DAY, .0001,
                        bias_result=bias, m1_candles=tuple(loaded["M1"]), regime_result=regime)
    adapted = compat.run(config=config, session_pair_id="ASIAN_LONDON", trading_date=DAY, pip_size=.0001)
    assert compat.event_id == replay.event_id == mi.identity.event_id
    assert compat.m15_candles == tuple(replay.candles("M15"))
    assert compat.m1_candles == tuple(replay.candles("M1"))
    assert adapted == legacy


def test_incomplete_mi_cannot_enter_ssc_and_identity_mismatch_fails_closed():
    store, loaded, replay = _event()
    config, bias, regime = _evidence(store, loaded)
    incomplete = compose_market_intelligence(replay)
    with pytest.raises(SSCCompatibilityError):
        build_ssc_compatibility_context(incomplete, replay, bias_result=bias, regime_result=regime)
    other = ReplayEvaluationContext.create(store, "EURUSD", datetime(2026, 6, 23, 12, tzinfo=UTC), ("H1", "M15", "M1"))
    with pytest.raises(SSCCompatibilityError):
        build_ssc_compatibility_context(compose_market_intelligence(replay, higher_timeframe_context={"h1_bias": bias}), other, bias_result=bias, regime_result=regime)


def test_adapter_historical_path_has_zero_live_fallback():
    store, loaded, replay = _event()
    config, bias, regime = _evidence(store, loaded)
    mi = compose_market_intelligence(replay, higher_timeframe_context={"h1_bias": bias})
    compat = build_ssc_compatibility_context(mi, replay, bias_result=bias, regime_result=regime)
    with patch.object(mt5, "copy_rates_from_pos", side_effect=AssertionError("live fallback")), patch.object(mt5, "copy_rates_range", side_effect=AssertionError("live fallback")):
        result = compat.run(config=config, session_pair_id="ASIAN_LONDON", trading_date=DAY, pip_size=.0001)
    assert result.symbol == "EURUSD"
