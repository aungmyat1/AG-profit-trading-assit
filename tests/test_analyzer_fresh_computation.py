"""Byte comparison with the tracked main analyzer; all candle reads are injected."""
import builtins
import datetime as dt
import hashlib
import importlib.util
import json
import math
from dataclasses import asdict
from pathlib import Path

import pytest

from market_structure import analyzer
from market_structure.models import MarketStructureConfig
from mt5.market_data import MarketDataError
from strategy_engine.session import Candle

BASELINE = Path(__file__).parent / "fixtures/analyzer_main_7b17a9f.py"
BASELINE_SHA256 = "228f0193f8c03ded7fb098ef2c601cc5c5a98599875ac3fabc2d716f5c4cfc9f"


def baseline_module():
    assert hashlib.sha256(BASELINE.read_bytes()).hexdigest() == BASELINE_SHA256
    spec = importlib.util.spec_from_file_location("market_structure._baseline_7b17a9f", BASELINE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def encoded(result):
    return json.dumps(asdict(result), sort_keys=True, separators=(",", ":"),
                      default=lambda value: value.isoformat(), allow_nan=False).encode("utf-8")


@pytest.fixture
def absent_replay(monkeypatch):
    """Reproduce tracked main's absent package even on a host with extra modules."""
    original = builtins.__import__
    attempts = []

    def guarded(name, *args, **kwargs):
        if name.startswith("historical_replay"):
            attempts.append(name)
            raise ModuleNotFoundError("No module named 'historical_replay'")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    return attempts


@pytest.fixture
def no_cache_access(monkeypatch):
    from shared_cache import derived_fact_cache

    calls = []

    def record(*args, **kwargs):
        calls.append((args, kwargs))
        return None

    monkeypatch.setattr(derived_fact_cache, "get", record)
    monkeypatch.setattr(derived_fact_cache, "put", record)
    yield
    assert not calls, "fresh analyzer must never read or write the derived cache"


@pytest.mark.parametrize("swing_length", [3, 5])
@pytest.mark.parametrize("timeframe,trend", [("M5", -0.00001), ("H1", 0.0), ("H4", 0.00001)])
def test_fresh_output_is_byte_identical_to_main(monkeypatch, absent_replay, no_cache_access,
                                               swing_length, timeframe, trend):
    baseline = baseline_module()
    start = dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc)
    candles = []
    for i in range(320):
        center = 1.1 + trend * i + 0.002 * math.sin(i / 7) + 0.0005 * math.sin(i / 2)
        candles.append(Candle(start + dt.timedelta(minutes=5 * i), center - 0.0001,
                              center + 0.0004, center - 0.0004, center + 0.0001, 100.0))
    config = MarketStructureConfig(swing_length, True, 100)
    reads = []

    def fetch(symbol, tf, count):
        reads.append((symbol, tf, count))
        return candles

    monkeypatch.setattr(baseline, "get_latest_candles", fetch)
    monkeypatch.setattr(analyzer, "get_latest_candles", fetch)
    expected = baseline.analyze_structure("EURUSD", timeframe, 100, config)
    assert absent_replay == ["historical_replay.data_source_patch"]
    absent_replay.clear()
    actual = analyzer.analyze_structure("EURUSD", timeframe, 100, config)
    assert actual.status == "VALID" and actual.latest_swing_high is not None
    assert encoded(actual) == encoded(expected)
    assert reads[0] == reads[1] and not absent_replay


@pytest.mark.parametrize("failure", ["data", "short_history"])
def test_failure_output_is_byte_identical_to_main(monkeypatch, failure):
    baseline = baseline_module()

    def fetch(*args):
        if failure == "data":
            raise MarketDataError("INJECTED_DATA_ERROR", "injected offline failure")
        return []

    for module in (baseline, analyzer):
        monkeypatch.setattr(module, "get_latest_candles", fetch)
    config = MarketStructureConfig(3, True, 100)
    assert encoded(analyzer.analyze_structure("EURUSD", "H1", 100, config)) == encoded(
        baseline.analyze_structure("EURUSD", "H1", 100, config))
