"""ST_ASIAN_SWEEP_5R_V1@1.1.3 engine path (strategy_engine.append_only): D-ASW-1 and D-ASW-2 enforced
for v1.1.3 only, with the v1.1.1/v1.1.2 engine and the registry S1 identity untouched."""
from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path

import pytest

from strategy_engine import evaluate, load_strategy
from strategy_engine.append_only import (
    NON_POSITIVE_RISK,
    emission_stream,
    evaluate_append_only,
    evaluate_for,
    route_append_only,
    uses_append_only,
)
from strategy_engine.session import Candle
from strategy_engine.session.classifier import Regime
from strategy_engine.session.reference_box import build_reference_box
from v1_tickets import fx
from v1_tickets.authority import logic_identity

ROOT = Path(__file__).resolve().parents[1]
V113 = load_strategy(str(ROOT / "strategies" / "ST_ASIAN_SWEEP_5R_V1_1_1_3.yaml"))
V112 = load_strategy(str(ROOT / "strategies" / "ST_ASIAN_SWEEP_5R_V1_1_1_2.yaml"))
S1_IDENTITY = "d7a8ebe5b176e8089905c75a6b0223eebd893c2b9324ca61865aa135d2eec7d5"
DAY = dt.date(2026, 7, 31)
UTC = dt.timezone.utc
BOX_HIGH, BOX_LOW, BOX_MID = 1.1515, 1.1505, 1.1510


def bar(h, m, o, hi, lo, c):
    return Candle(time=dt.datetime(2026, 7, 31, h, m, tzinfo=UTC), open=o, high=hi, low=lo, close=c)


REFERENCE = [Candle(time=dt.datetime(2026, 7, 31, h, 0, tzinfo=UTC), open=BOX_MID - 0.0005, high=BOX_HIGH,
                    low=BOX_LOW, close=BOX_MID + 0.0002) for h in range(24)]
# The 2026-07-31 mechanism: an exact boundary touch (Entry 3, zero risk) ...
TOUCH = bar(8, 30, 1.15075, BOX_LOW + 0.001, BOX_LOW, BOX_LOW + 0.0005)
# ... a sweep bar opening at its own low (Entry 2 zero risk; Entry 3 positive risk on the same bar) ...
OPEN_AT_LOW = bar(9, 45, BOX_LOW - 0.0001, BOX_LOW + 0.005, BOX_LOW - 0.0001, BOX_LOW + 0.002)
# ... and a clean later sweep (Entry 2, positive risk).
CLEAN_SWEEP = bar(10, 0, BOX_LOW + 0.0001, BOX_LOW + 0.0008, BOX_LOW - 0.0003, BOX_LOW + 0.0001)


def route(window):
    return route_append_only("ST_ASIAN_SWEEP_5R_V1", "EURUSD", "Asian", DAY, REFERENCE, 24, window,
                             regime_override=Regime.RANGE)[2]


def test_only_v113_uses_the_append_only_path():
    assert uses_append_only(V113) and evaluate_for(V113) is evaluate_append_only
    assert not uses_append_only(V112) and evaluate_for(V112) is evaluate
    frozen = load_strategy(str(ROOT / "strategies" / "ST_ASIAN_SWEEP_5R_V1.yaml"))
    assert evaluate_for(frozen) is evaluate


def test_s1_identity_is_unchanged_and_v113_has_its_own():
    assert logic_identity("ST_ASIAN_SWEEP_5R_V1", "1.1.2", ROOT)["digest"] == S1_IDENTITY
    v113 = logic_identity("ST_ASIAN_SWEEP_5R_V1", "1.1.3", ROOT)
    v112 = logic_identity("ST_ASIAN_SWEEP_5R_V1", "1.1.2", ROOT)
    assert v113["engine_identity"] != v112["engine_identity"]       # includes append_only.py
    raw = (ROOT / "strategies" / "ST_ASIAN_SWEEP_5R_V1_1_1_3.yaml").read_bytes().replace(b"\r\n", b"\n")
    expected = hashlib.sha256(b"strategies/ST_ASIAN_SWEEP_5R_V1_1_1_3.yaml\0" + raw + b"\0").hexdigest()
    assert v113["contract_hash"] == expected


def test_d_asw_1_zero_risk_boundary_touch_is_no_setup():
    decision = route([TOUCH])
    assert decision.decision_status.value == "NO_SETUP"
    assert decision.reason_code == NON_POSITIVE_RISK
    assert decision.risk_distance is None and decision.direction is None
    assert decision.evidence["rejected_reason_code"] == "LOWER_BOUNDARY_REJECTION"


def test_d_asw_1_zero_risk_sweep_falls_through_to_entry_3_on_the_same_bar():
    decision = route([OPEN_AT_LOW])
    assert (decision.setup_type.value, decision.reason_code) == ("RANGE", "LOWER_BOUNDARY_REJECTION")
    assert decision.risk_distance > 0 and decision.signal_timestamp == OPEN_AT_LOW.time


def test_d_asw_2_first_emission_is_never_rewritten_by_a_later_bar():
    window = [TOUCH, OPEN_AT_LOW, CLEAN_SWEEP]
    first = None
    for k in range(1, len(window) + 1):
        decision = route(window[:k])
        if decision.decision_status.value == "VALID":
            first = first or decision
            assert decision == first                                  # immutable once published
    assert first.signal_timestamp == OPEN_AT_LOW.time


def test_later_qualifications_are_appended_not_substituted():
    box = build_reference_box("Asian", REFERENCE, 24)
    emissions, rejected = emission_stream("ST_ASIAN_SWEEP_5R_V1", "EURUSD", box, Regime.RANGE, DAY,
                                          [TOUCH, OPEN_AT_LOW, CLEAN_SWEEP])
    assert [e.signal_timestamp for e in emissions] == [OPEN_AT_LOW.time, CLEAN_SWEEP.time]
    assert [e.setup_type.value for e in emissions] == ["RANGE", "SWEEP"]
    assert all(e.risk_distance > 0 for e in emissions)
    assert [r.reason_code for r in rejected] == ["LOWER_BOUNDARY_REJECTION", "LOWER_SWEEP_STRICT_PENETRATION"]


def test_signal_id_is_per_qualifying_bar():
    sig = evaluate_append_only(V113, "ASIAN_LONDON", "EURUSD", DAY, REFERENCE, 24, [TOUCH, OPEN_AT_LOW],
                               regime_override=Regime.RANGE)
    assert sig.status == "SIGNAL"
    assert sig.signal_id.endswith(":" + OPEN_AT_LOW.time.isoformat())
    assert sig.strategy_version == "1.1.3"


def test_v112_frozen_behaviour_is_unchanged():
    """The shared router still lets a later sweep replace an earlier emission for v1.1.2 (pinned)."""
    sig = evaluate(V112, "ASIAN_LONDON", "EURUSD", DAY, REFERENCE, 24, [TOUCH, OPEN_AT_LOW],
                   regime_override=Regime.RANGE)
    assert sig.setup == "SWEEP" and sig.risk_distance == 0.0
    assert sig.signal_id == "ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:EURUSD:2026-07-31"


@pytest.mark.parametrize("value,expected", [(1.234565, 1.23457), (1.234564, 1.23456), (1.2345650001, 1.23457)])
def test_od1011_rounding_half_up_for_v113(monkeypatch, value, expected):
    monkeypatch.setattr(fx, "_digits", lambda symbol: 5)
    assert fx._rounder(V113) is fx._r_half_up and fx._rounder(V112) is fx._r
    assert fx._r_half_up("EURUSD", value) == expected
    assert fx._r_half_up("EURUSD", None) is None
