from __future__ import annotations

import datetime as dt
import json
import random
from pathlib import Path

import pytest

from asian_sweep_v1_2 import BAR, Bar, actionable_at, evaluate, stream
from asian_sweep_v1_2.reference import reference_evaluate

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 10, 7, tzinfo=UTC)


def reference(high=1.1020, low=1.1000):
    return [Bar(T0, 1.1010, high, low, 1.1010)]


def lower(*, low=1.0998, close=1.1002, high=1.1010, at=T0 + dt.timedelta(hours=7)):
    return Bar(at, 1.1001, high, low, close)


def upper(*, high=1.1022, close=1.1018, low=1.1010, at=T0 + dt.timedelta(hours=7)):
    return Bar(at, 1.1019, high, low, close)


def semantic_ref(symbol, ref, bars, spread):
    return reference_evaluate(symbol, ref, bars, spread)


@pytest.mark.parametrize("bar,direction", [(lower(), "LONG"), (upper(), "SHORT")])
def test_close_entry_stop_formula_targets_split_and_expiry(bar, direction):
    d = evaluate("EURUSD", reference(), [bar], spread_distance=.00005)
    assert d.status == "ACTIONABLE" and d.direction == direction
    assert d.entry == bar.close
    assert d.decision_time == bar.time + BAR and d.expiry == d.decision_time + BAR
    assert abs(d.entry - d.stop_loss) == pytest.approx((1.1020 - 1.1000) * .25)
    assert (d.stop_loss <= bar.low) if direction == "LONG" else (d.stop_loss >= bar.high)
    assert (d.stop_loss < d.entry < d.tp1 <= d.tp2) if direction == "LONG" else (
        d.stop_loss > d.entry > d.tp1 >= d.tp2)


def test_wick_clear_rejects_without_stretching_stop():
    bar = lower(low=1.0999, close=1.1005)
    d = evaluate("EURUSD", reference(), [bar], spread_distance=.00001)
    assert d.reason == "SL_DOES_NOT_CLEAR_SWEEP_EXTREME"
    assert d.stop_loss == pytest.approx(1.1000) and d.sweep_extreme == 1.0999


def test_dual_sweep_zero_range_and_unsupported_fail_closed():
    dual = Bar(T0, 1.101, 1.103, 1.099, 1.101)
    assert evaluate("EURUSD", reference(), [dual], spread_distance=0).reason == "AMBIGUOUS_DUAL_SWEEP"
    assert evaluate("EURUSD", reference(1.1, 1.1), [], spread_distance=0).reason == "INVALID_REFERENCE_RANGE"
    with pytest.raises(ValueError, match="UNSUPPORTED_INSTRUMENT"):
        evaluate("AUDUSD", reference(), [], spread_distance=0)


@pytest.mark.parametrize("spread,reason", [(.00005, "PASS"), (.000075, "PASS"),
                                            (.0001, "SPREAD_R_EXCEEDED"), (.000200001, "SPREAD_ABSOLUTE_EXCEEDED")])
def test_both_spread_gates(spread, reason):
    # stop=.0005; .0002 is exactly 2 pips but 40% R, proving independent gates.
    assert evaluate("EURUSD", reference(), [lower()], spread_distance=spread).reason == reason


def test_spread_exactly_15_percent_passes_slightly_above_fails():
    stop = .0005
    assert evaluate("EURUSD", reference(), [lower()], spread_distance=stop * .15).reason == "PASS"
    assert evaluate("EURUSD", reference(), [lower()], spread_distance=stop * .150001).reason == "SPREAD_R_EXCEEDED"


def test_expiry_boundary_is_half_open():
    d = evaluate("EURUSD", reference(), [lower()], spread_distance=.00005)
    assert actionable_at(d, d.expiry - dt.timedelta(seconds=1))
    assert not actionable_at(d, d.expiry)
    assert not actionable_at(d, d.expiry + dt.timedelta(seconds=1))


def test_streaming_batch_and_independent_reference_parity():
    bars = [Bar(T0 + dt.timedelta(hours=7), 1.101, 1.1015, 1.1002, 1.1008), lower(at=T0 + dt.timedelta(hours=7, minutes=15)),
            Bar(T0 + dt.timedelta(hours=7, minutes=30), 9, 10, 8, 9)]
    batch = evaluate("EURUSD", reference(), bars, spread_distance=.00005)
    streamed = stream("EURUSD", reference(), bars, spread_distance=.00005)
    assert batch.semantic() == streamed.semantic() == semantic_ref("EURUSD", reference(), bars, .00005)
    assert batch.semantic_hash() == streamed.semantic_hash()


def test_future_mutation_isolation_deterministic_property_loop():
    rng = random.Random(120)
    ref = reference()
    decision_bar = lower()
    original = evaluate("EURUSD", ref, [decision_bar], spread_distance=.00005).semantic()
    for _ in range(250):
        future = [Bar(decision_bar.time + BAR * (i + 1), rng.uniform(.5, 2), rng.uniform(2, 4),
                      rng.uniform(.1, .4), rng.uniform(.5, 2)) for i in range(rng.randint(1, 8))]
        assert evaluate("EURUSD", ref, [decision_bar] + future, spread_distance=.00005).semantic() == original


def test_determinism_and_reference_parity_randomized():
    rng = random.Random(12)
    for i in range(200):
        width = rng.uniform(.0002, .01)
        lo = rng.uniform(1, 2)
        hi = lo + width
        close = rng.uniform(lo + width * .01, hi - width * .01)
        if i % 2:
            bar = Bar(T0, close, hi + rng.uniform(.00001, width), lo, close)
        else:
            bar = Bar(T0, close, hi, lo - rng.uniform(.00001, width), close)
        ref = reference(hi, lo)
        spread = rng.uniform(0, width * .1)
        one = evaluate("EURUSD", ref, [bar], spread_distance=spread)
        two = evaluate("EURUSD", ref, [bar], spread_distance=spread)
        assert one.semantic() == two.semantic() == semantic_ref("EURUSD", ref, [bar], spread)


def test_existing_logic_gate_v12_delta_passes_actionable_candidate():
    from v1_tickets.logic_gate import PASS, v120_strategy_delta
    d = evaluate("EURUSD", reference(), [lower()], spread_distance=.00005)
    gate = v120_strategy_delta(d)
    assert gate["status"] == PASS
    assert {c["id"] for c in gate["checks"]} == {
        "V12.entry_close", "V12.stop_25pct", "V12.wick_clear", "V12.target_order",
        "V12.expiry", "V12.spread_absolute", "V12.spread_R"}


def test_golden_fixture_inventory_is_exact_and_missing_data_is_not_invented():
    payload = json.loads(Path("tests/fixtures/asian_sweep_v1_2/recorded_23.json").read_text())
    assert len(payload["cases"]) == 23
    assert sum(c["expected_entry"] is not None for c in payload["cases"]) == 10
    assert sum(c["expected_status"] == "INSUFFICIENT_RECORDED_INPUT" for c in payload["cases"]) == 13
    assert all(c["expected_expiry"] is None for c in payload["cases"])


def test_contract_partial_exit_and_fixed_utc_are_frozen():
    import yaml
    contract = yaml.safe_load(Path("strategies/ST_ASIAN_SWEEP_5R_V1_2_0.yaml").read_text())
    assert contract["session_anchor"] == "FIXED_UTC"
    assert contract["session_pairs"][0]["trade_session"]["end_time_utc"] == "11:00"
    legs = contract["position_split_and_targets"]["legs"]
    assert [(x["volume_pct"], x["target_type"]) for x in legs] == [(.75, "OPPOSITE_REFERENCE_BOUNDARY"), (.25, "FIXED_R_MULTIPLE")]
    assert legs[0]["action_on_fill"] == "MOVE_REMAINING_STOP_TO_BREAKEVEN"
    assert contract["risk_and_cost"]["owner_risk_pct"] == .5
    assert contract["risk_and_cost"]["commission"]["unavailable_value"] == "UNKNOWN"


def test_v111_contract_immutable_hash():
    import hashlib
    assert hashlib.sha256(Path("strategies/ST_ASIAN_SWEEP_5R_V1.yaml").read_bytes()).hexdigest() == \
        "baed22b718e9017f291808063c62d3eda6d00ceb3b8ea89cc071919b8530f9cf"
