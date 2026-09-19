"""TD-8B: structure cache isolation across live, replay, data, and semantics."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from historical_replay import HistoricalCandleStore, historical_data_context
from market_structure import analyzer
from market_structure.models import MarketStructureConfig
from shared_cache import derived_fact_cache as cache
from strategy_engine.session import Candle

CONFIG = MarketStructureConfig(swing_length=3, close_break=True, default_analysis_count=5)
START = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def clean_cache():
    cache.clear_cache()
    yield
    cache.clear_cache()


def candles(n=120):
    return [Candle(time=START + timedelta(minutes=5*i), open=1.1+i*0.0001,
                   high=1.101+i*0.0001, low=1.099+i*0.0001,
                   close=1.1002+i*0.0001, volume=10+i) for i in range(n)]


def detector_spy():
    return patch.object(analyzer, "latest_swings_and_breaks", return_value={
        "latest_bos": None, "latest_choch": None,
        "latest_swing_high": None, "latest_swing_low": None,
    })


def test_live_hit_and_content_parameter_version_misses():
    data = candles()
    with patch.object(analyzer, "get_latest_candles", return_value=data), detector_spy() as compute:
        first = analyzer.analyze_structure("EURUSD", "M5", config=CONFIG)
        second = analyzer.analyze_structure("EURUSD", "M5", config=CONFIG)
        assert first == second and compute.call_count == 1
        assert cache.cache_diagnostics()["hits"] == 1
        analyzer.analyze_structure("EURUSD", "M5", config=replace(CONFIG, swing_length=4))
        assert compute.call_count == 2
        with patch.object(analyzer, "_DERIVED_FEATURE_VERSION", "NEXT_VERSION"):
            analyzer.analyze_structure("EURUSD", "M5", config=CONFIG)
        assert compute.call_count == 3
        data[-1] = replace(data[-1], close=data[-1].close + 0.0001)
        analyzer.analyze_structure("EURUSD", "M5", config=CONFIG)
        assert compute.call_count == 4


def test_replay_hit_boundary_dataset_and_live_isolation():
    original = candles()
    changed = list(original)
    changed[-1] = replace(changed[-1], high=changed[-1].high + 10)
    store_a, store_b = HistoricalCandleStore(), HistoricalCandleStore()
    store_a.load_series("EURUSD", "M5", original)
    store_b.load_series("EURUSD", "M5", changed)
    t = START + timedelta(minutes=5*118)
    earlier = t - timedelta(minutes=5)
    with detector_spy() as compute:
        with historical_data_context(store_a, t):
            at_t = analyzer.analyze_structure("EURUSD", "M5", config=CONFIG)
            assert analyzer.analyze_structure("EURUSD", "M5", config=CONFIG) == at_t
        assert compute.call_count == 1
        with historical_data_context(store_a, earlier):
            analyzer.analyze_structure("EURUSD", "M5", config=CONFIG)
        assert compute.call_count == 2
        with historical_data_context(store_b, t):
            assert analyzer.analyze_structure("EURUSD", "M5", config=CONFIG) == at_t
        assert compute.call_count == 3  # different full dataset, identical visible prefix
        with patch.object(analyzer, "get_latest_candles", return_value=original[:118]):
            analyzer.analyze_structure("EURUSD", "M5", config=CONFIG)
        assert compute.call_count == 4  # LIVE cannot consume REPLAY


def test_cache_failure_recomputes_without_changing_result():
    with patch.object(analyzer, "get_latest_candles", return_value=candles()), detector_spy() as compute:
        expected = analyzer.analyze_structure("EURUSD", "M5", config=CONFIG)
        with patch.object(cache, "get", side_effect=RuntimeError("cache unavailable")):
            assert analyzer.analyze_structure("EURUSD", "M5", config=CONFIG) == expected
        assert compute.call_count == 2
