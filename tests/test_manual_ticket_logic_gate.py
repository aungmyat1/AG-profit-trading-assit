"""Manual Trade Ticket V1 Phase 4: Logic Gate L1-L6 on recorded historical sessions.

Fixture: tests/fixtures/manual_ticket/EURUSD_M15_recorded.csv (see README there). Offline,
no MT5. The gate must report -- never repair -- frozen-spec/engine divergences."""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

import pytest

from strategy_engine import load_strategy
from strategy_engine.session import Candle
from v1_tickets.fx import STRATEGY_PATH, build_fx_ticket, session_windows_utc
from v1_tickets.logic_gate import (
    FAIL, NOT_APPLICABLE, NOT_EVALUABLE, PASS, WARN, blocking_failures, l1_determinism, l2_rule_conformance,
    l3_geometry, l4_data_session, l5_cost, l6_freshness,
)

UTC = dt.timezone.utc
FIXTURE = Path(__file__).parent / "fixtures" / "manual_ticket" / "EURUSD_M15_recorded.csv"
CANDLES = [Candle(dt.datetime.fromisoformat(r["timestamp_utc"]).replace(tzinfo=UTC), float(r["open"]),
                  float(r["high"]), float(r["low"]), float(r["close"])) for r in csv.DictReader(FIXTURE.open())]
STRATEGY = load_strategy(STRATEGY_PATH)


@pytest.fixture(autouse=True)
def _no_repo_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("AG_EVIDENCE_ROOT", str(tmp_path / "no_evidence"))


def replay(day: str, at: str = "11:00", spread=0.00008):
    d = dt.date.fromisoformat(day)
    w = session_windows_utc(d)["ASIAN_LONDON"]
    now = dt.datetime.fromisoformat(f"{day}T{at}:00+00:00")
    session = [c for c in CANDLES if w["ref"][0] <= c.time < w["ref"][1]]
    post = [c for c in CANDLES if w["trade"][0] <= c.time < w["trade"][1] and c.time + dt.timedelta(minutes=15) <= now]

    def build(evaluated_at=now):
        return build_fx_ticket("EURUSD", "ASIAN_LONDON", d, session, 24, post, data_source="FIXTURE",
                               evaluated_at=evaluated_at, data_close=evaluated_at, spread=spread)
    return d, w, now, session, post, build


def by_id(gate):
    return {c["id"]: c for c in gate["checks"]}


def test_recorded_branches_are_what_the_fixture_documents():
    seen = {day: replay(day)[5]() for day in ("2026-06-15", "2026-06-16", "2026-06-17", "2026-06-23", "2026-07-17")}
    assert seen["2026-06-15"]["reason_code"] == "NO_SETUP_BY_WINDOW_END"
    assert seen["2026-06-16"]["setup"] == "TREND"
    assert (seen["2026-06-17"]["setup"], seen["2026-06-17"]["direction"]) == ("SWEEP", "LONG")
    assert (seen["2026-06-23"]["setup"], seen["2026-06-23"]["direction"]) == ("SWEEP", "SHORT")
    assert seen["2026-07-17"]["risk_distance"] == 0


@pytest.mark.parametrize("day", ["2026-06-15", "2026-06-16", "2026-06-17", "2026-06-23", "2026-07-17"])
def test_l1_same_input_identical_ticket_and_closed_bars_only(day):
    d, w, now, session, post, build = replay(day)
    assert l1_determinism(build, session + post, now)["status"] == PASS
    # An unclosed bar at decision time is look-ahead -> FAIL.
    early = post[-1].time + dt.timedelta(minutes=5)
    gate = l1_determinism(build, session + post, early)
    assert gate["status"] == FAIL and by_id(gate)["L1.closed_bars_only"]["verdict"] == FAIL


SPEC_RULES = {"R.reference_session", "R.trend_bias_filter", "R.range_session_check", "R.entry_trigger",
              "R.entry_order_type", "R.entry_level", "R.stop_loss", "R.target_leg1", "R.target_leg2",
              "R.position_split", "R.max_entries_per_session", "R.max_spread", "R.time_invalidation",
              "R.risk_mode", "R.slippage_limit", "R.post_fill_management", "R.structural_invalidation"}


def test_l2_evaluates_every_spec_rule_and_fails_closed_on_frozen_divergences():
    d, w, now, session, post, build = replay("2026-06-17")
    t = build()
    gate = l2_rule_conformance(STRATEGY, t, session, 24, post, digits=5, spread=0.00008)
    checks = by_id(gate)
    assert set(checks) == SPEC_RULES                                       # missing evaluation would fail here
    assert gate["status"] == FAIL
    assert checks["R.entry_trigger"]["verdict"] == PASS and checks["R.target_leg1"]["verdict"] == PASS
    assert checks["R.target_leg2"]["verdict"] == PASS and checks["R.entry_order_type"]["verdict"] == PASS
    assert checks["R.max_spread"]["verdict"] == PASS and checks["R.max_spread"]["value"] == 0.8
    # Pre-existing frozen divergences are reported, not repaired.
    assert checks["R.trend_bias_filter"]["verdict"] == NOT_EVALUABLE
    assert checks["R.stop_loss"]["verdict"] == FAIL
    assert checks["R.stop_loss"]["expected"] > checks["R.stop_loss"]["value"]   # 25% of range vs wick stop
    assert checks["R.risk_mode"]["verdict"] == NOT_APPLICABLE


def test_l2_trend_setup_is_not_a_declared_entry_rule():
    d, w, now, session, post, build = replay("2026-06-16")
    checks = by_id(l2_rule_conformance(STRATEGY, build(), session, 24, post, digits=5, spread=0.00008))
    assert checks["R.entry_trigger"]["verdict"] == FAIL and checks["R.entry_trigger"]["value"] == "TREND"


def test_l3_geometry_passes_on_recorded_sweep():
    d, w, now, session, post, build = replay("2026-06-23")
    gate = l3_geometry(build(), post, digits=5, declared_rr=5.0)
    assert gate["status"] == PASS, gate
    assert "no RR tolerance" in by_id(gate)["L3.rr_tp2"]["note"]


def test_l3_target_order_fails_on_recorded_inverted_long():
    """A1 on recorded data: 2026-06-17 LONG TP1 (box high 1.16160) lies beyond TP2 (5R, 1.16145)."""
    d, w, now, session, post, build = replay("2026-06-17")
    gate = l3_geometry(build(), post, digits=5, declared_rr=5.0)
    checks = by_id(gate)
    assert gate["status"] == FAIL and checks["L3.target_order"]["verdict"] == FAIL
    assert all(c["verdict"] == PASS for k, c in checks.items() if k != "L3.target_order")


def _short(entry, sl, tp1, tp2):
    return {"direction": "SHORT", "entry": entry, "stop_loss": sl, "risk_distance": round(sl - entry, 6),
            "targets": [{"leg": 1, "price": tp1}, {"leg": 2, "price": tp2}], "signal_timestamp": None}


def test_l3_target_order_usdjpy_short_regression():
    """A1 fixture: USDJPY SHORT entry 158.148, SL 158.224, TP1 157.762, TP2 157.768 -> L3 FAIL."""
    gate = l3_geometry(_short(158.148, 158.224, 157.762, 157.768), [], digits=3, declared_rr=5.0)
    assert gate["status"] == FAIL and by_id(gate)["L3.target_order"]["verdict"] == FAIL
    assert by_id(gate)["L3.tp1_direction"]["verdict"] == PASS and by_id(gate)["L3.tp2_direction"]["verdict"] == PASS


@pytest.mark.parametrize("direction,entry,tp1,tp2,verdict", [
    ("LONG", 1.1000, 1.1010, 1.1050, PASS), ("LONG", 1.1000, 1.1050, 1.1050, PASS),
    ("LONG", 1.1000, 1.1060, 1.1050, FAIL), ("LONG", 1.1000, 1.0990, 1.1050, FAIL),
    ("SHORT", 1.1000, 1.0990, 1.0950, PASS), ("SHORT", 1.1000, 1.0950, 1.0950, PASS),
    ("SHORT", 1.1000, 1.0940, 1.0950, FAIL), ("SHORT", 1.1000, 1.1010, 1.0950, FAIL),
])
def test_l3_target_order_boundaries(direction, entry, tp1, tp2, verdict):
    t = {"direction": direction, "entry": entry, "targets": [{"leg": 1, "price": tp1}, {"leg": 2, "price": tp2}]}
    assert by_id(l3_geometry(t, [], digits=5, declared_rr=5.0))["L3.target_order"]["verdict"] == verdict


def test_l3_zero_stop_distance_fails():
    d, w, now, session, post, build = replay("2026-07-17")
    gate = l3_geometry(build(), post, digits=5, declared_rr=5.0)
    assert gate["status"] == FAIL and by_id(gate)["L3.sl_side"]["verdict"] == FAIL


def test_l4_data_and_session():
    d, w, now, session, post, build = replay("2026-06-17")
    kw = dict(ref_window=w["ref"], trade_window=w["trade"], reference_name="Asian", session=session,
              expected_bar_count=24, post=post, now=now)
    assert l4_data_session(build(), data_close=now, **kw)["status"] == PASS
    stale = l4_data_session(build(), data_close=now - dt.timedelta(minutes=16), **kw)
    assert by_id(stale)["L4.data_fresh"]["verdict"] == FAIL
    short = l4_data_session(build(), data_close=now, **{**kw, "session": session[:-1]})
    assert by_id(short)["L4.reference_complete"]["verdict"] == FAIL
    leaked = l4_data_session(build(), data_close=now, **{**kw, "session": session + post[:1]})
    assert by_id(leaked)["L4.reference_bars_in_window"]["verdict"] == FAIL


def test_l5_cost_is_advisory_and_needs_owner_warn_level():
    unset = l5_cost(0.00008, 0.00014, commission_r=None, warn_r=None)
    assert unset["status"] == WARN and by_id(unset)["L5.cost_vs_warn_level"]["note"] == "WARN LEVEL NOT SET"
    ok = l5_cost(0.00002, 0.0002, commission_r=0.05, warn_r=0.2)
    assert ok["status"] == PASS and by_id(ok)["L5.cost_vs_warn_level"]["value"] == 0.15
    high = l5_cost(0.0001, 0.0002, commission_r=0.05, warn_r=0.2)
    assert high["status"] == WARN
    assert blocking_failures({"L1": {"status": PASS}, "L2": {"status": PASS}, "L3": {"status": PASS},
                              "L4": {"status": PASS}, "L5": high}) == []


def test_l6_fields_are_flags():
    assert l6_freshness("2026-06-17T07:30:00+00:00", {"x": 1}, {"y": 2})["status"] == PASS
    assert l6_freshness(None, {"x": 1}, {"y": 2})["status"] == WARN
