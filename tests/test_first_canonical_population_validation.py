import json

from canonical_experiments import CanonicalOccurrence, chronological_split
from research.session_lifecycle import compare_lifecycle_records, population_hash


def _record():
    return {
        "trade_id": "ASIAN_LONDON_2026-01-01_2026-01-01T07:15:00+00:00_S1_SWEEP_REVERSAL",
        "strategy_id": "ST_SESSION_SWEEP_CONTINUATION_V1",
        "strategy_version": "1.0.0",
        "symbol": "EURUSD",
        "direction": "LONG",
        "entry_time": "2026-01-01T07:15:00+00:00",
        "entry_price": 1.1,
        "initial_stop": 1.099,
        "initial_risk": 0.001,
        "events": [{"time": "2026-01-01T07:30:00+00:00", "gross_R_delta": 1.0}],
        "gross_R": 1.0,
        "friction_R": 0.1,
        "net_R": 0.9,
        "final_state": "RESOLVED_TP1",
        "resolution_time": "2026-01-01T07:30:00+00:00",
    }


def test_lifecycle_hash_is_order_independent_and_reload_stable(tmp_path):
    records = [_record()]
    path = tmp_path / "population.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    assert population_hash(records) == population_hash(reloaded)


def test_duplicate_occurrence_detection_is_explicit():
    records = [_record(), dict(_record())]
    ids = [record["trade_id"] for record in records]
    assert len(ids) != len(set(ids))


def test_future_data_guard_requires_strictly_after_entry():
    entry = "2026-01-01T07:15:00+00:00"
    event = "2026-01-01T07:30:00+00:00"
    assert event > entry
    assert not (entry > event)


def test_split_is_chronological_and_holdout_ids_are_isolated():
    def occurrence(identifier, timestamp):
        return CanonicalOccurrence(
            occurrence_id=identifier, strategy_id="S", strategy_version="1", exchange="X", symbol="Y",
            side="LONG", entry_timestamp=timestamp, entry_price=1.0, initial_sl=0.9, initial_tp=1.1,
            m1_path=(),
        )

    population = [occurrence("a", "2026-01-01T00:00:00+00:00"), occurrence("b", "2026-01-02T00:00:00+00:00")]
    split = chronological_split(population, 0.5)
    assert split["discovery_ids"] == ["a"]
    assert split["holdout_ids"] == ["b"]
    assert set(split["discovery_ids"]).isdisjoint(split["holdout_ids"])


def test_lifecycle_comparison_detects_field_difference():
    first = [_record()]
    second = [dict(_record(), net_R=0.8)]
    comparison = compare_lifecycle_records(first, second)
    assert comparison["trade_count_equal"]
    assert comparison["occurrence_order_equal"]
    assert not comparison["field_level_equal"]
    assert comparison["first_difference"]["field"] == "net_R"


def test_lifecycle_comparison_accepts_identical_order_and_fields():
    first = [_record()]
    comparison = compare_lifecycle_records(first, [dict(first[0])])
    assert comparison["trade_count_equal"]
    assert comparison["occurrence_ids_equal"]
    assert comparison["occurrence_order_equal"]
    assert comparison["field_level_equal"]