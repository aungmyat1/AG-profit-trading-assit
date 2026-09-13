from datetime import datetime, timedelta, timezone

import pytest

from canonical_experiments import (
    CanonicalExperimentRunner, CanonicalOccurrence, CandleSnapshot, ControlPolicy,
    ExperimentScopeError, TimeStopPolicy, chronological_split,
)
from canonical_experiments.population import load_population, write_population

UTC = timezone.utc


def _occurrence(occurrence_id="a", side="LONG", entry_time=None):
    entry = entry_time or datetime(2026, 1, 1, 13, 30, tzinfo=UTC)
    path = tuple(
        CandleSnapshot((entry + timedelta(minutes=index + 1)).isoformat(), price, price + .1, price - .1, price)
        for index, price in enumerate((100.0, 100.2, 100.4, 100.3))
    )
    return CanonicalOccurrence(
        occurrence_id=occurrence_id, strategy_id="ST_LIQUIDITY_SWEEP_RETEST_V1", strategy_version="2.0.0",
        exchange="BYBIT_USDT_M_PERP", symbol="BTCUSDT", side=side,
        entry_timestamp=entry.isoformat(), entry_price=100.0, initial_sl=99.0, initial_tp=101.0,
        m1_path=path, cost_context={"total_cost_R": .05},
    )


def test_control_and_time_stop_share_the_same_population_hash():
    population = [_occurrence("a"), _occurrence("b", entry_time=datetime(2026, 1, 2, 13, 30, tzinfo=UTC))]
    runner = CanonicalExperimentRunner(population, ["a", "b"], "discovery")
    results = runner.run_suite([ControlPolicy(), TimeStopPolicy(30)])
    assert len({result.population_hash for result in results}) == 1
    assert results[0].sample_size == results[1].sample_size == 2


def test_discovery_runner_rejects_unknown_or_holdout_id():
    with pytest.raises(ExperimentScopeError, match="UNKNOWN_OCCURRENCE_IDS"):
        CanonicalExperimentRunner([_occurrence("a"), _occurrence("b")], ["a", "holdout-b"], "discovery")


def test_chronological_split_is_oldest_first_and_nonempty_when_possible():
    population = [_occurrence("b", entry_time=datetime(2026, 1, 2, 13, 30, tzinfo=UTC)), _occurrence("a")]
    split = chronological_split(population)
    assert split["discovery_ids"] == ["a"]
    assert split["holdout_ids"] == ["b"]


def test_same_candle_stop_and_target_is_fail_closed():
    occurrence = _occurrence()
    path = (CandleSnapshot(occurrence.m1_path[0].timestamp, 100.0, 101.1, 98.9, 100.0),)
    occurrence = CanonicalOccurrence(**{**occurrence.to_dict(), "m1_path": path})
    with pytest.raises(ValueError, match="AMBIGUOUS_SAME_CANDLE_STOP_TARGET"):
        CanonicalExperimentRunner([occurrence], ["a"], "discovery").run(ControlPolicy())


def test_population_is_write_once_and_hash_checked(tmp_path):
    path = tmp_path / "population.json"
    occurrence = _occurrence()
    write_population(path, [occurrence], strategy_id=occurrence.strategy_id, strategy_version=occurrence.strategy_version, exchange=occurrence.exchange, symbol=occurrence.symbol)
    manifest, loaded = load_population(path)
    assert manifest["population_hash"]
    assert loaded[0].occurrence_id == "a"
    with pytest.raises(FileExistsError, match="IMMUTABLE_POPULATION_EXISTS"):
        write_population(path, [occurrence], strategy_id=occurrence.strategy_id, strategy_version=occurrence.strategy_version, exchange=occurrence.exchange, symbol=occurrence.symbol)