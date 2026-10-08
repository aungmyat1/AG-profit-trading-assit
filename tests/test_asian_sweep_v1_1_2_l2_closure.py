"""ST_ASIAN_SWEEP_5R_V1@1.1.2 candidate: Logic Gate L2 closure on the recorded EURUSD fixtures.

Engine behavior is the spec; unsafe/undefined engine outputs fail closed by a declared rule.
v1.1.1 stays the frozen authority and keeps failing L2 exactly as before. No outcome, no edge."""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

import pytest
import yaml

from strategy_engine import load_strategy
from strategy_engine.session import Candle
from v1_tickets.authority import LOGIC_VERIFIED, NOT_VERIFIED, load_registry, logic_identity, resolve_ticket_authority
from v1_tickets.fx import STRATEGY_PATH, build_fx_ticket, session_windows_utc
from v1_tickets.logic_gate import (
    FAIL, NOT_APPLICABLE, NOT_EVALUABLE, PASS, blocking_failures, l1_determinism, l2_rule_conformance, l3_geometry,
    l4_data_session, l5_cost, l6_freshness,
)

UTC = dt.timezone.utc
CANDIDATE = "strategies/ST_ASIAN_SWEEP_5R_V1_1_1_2.yaml"
FIXTURE = Path(__file__).parent / "fixtures" / "manual_ticket" / "EURUSD_M15_recorded.csv"
CANDLES = [Candle(dt.datetime.fromisoformat(r["timestamp_utc"]).replace(tzinfo=UTC), float(r["open"]),
                  float(r["high"]), float(r["low"]), float(r["close"])) for r in csv.DictReader(FIXTURE.open())]
TIGHT, WIDE = 0.00002, 0.00008      # test spread inputs (price units), not recorded data
# Every L2 FAIL allowed on the candidate is one of its declared fail-closed rules.
DECLARED_FAIL_CLOSED = {"R.regime_branch", "R.entry_trigger", "R.entry_level", "R.stop_loss", "R.target_leg2",
                        "R.max_spread", "R.max_spread_fraction", "R.target_order"}


@pytest.fixture(autouse=True)
def _no_repo_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("AG_EVIDENCE_ROOT", str(tmp_path / "no_evidence"))


def gates(day: str, path: str = CANDIDATE, spread: float = TIGHT):
    strategy = load_strategy(path)
    d = dt.date.fromisoformat(day)
    w = session_windows_utc(d)["ASIAN_LONDON"]
    now = dt.datetime.fromisoformat(f"{day}T11:00:00+00:00")
    session = [c for c in CANDLES if w["ref"][0] <= c.time < w["ref"][1]]
    post = [c for c in CANDLES if w["trade"][0] <= c.time < w["trade"][1] and c.time + dt.timedelta(minutes=15) <= now]

    def build():
        return build_fx_ticket("EURUSD", "ASIAN_LONDON", d, session, 24, post, data_source="FIXTURE",
                               evaluated_at=now, data_close=now, spread=spread, strategy_path=path)
    t = build()
    return t, {
        "L1": l1_determinism(build, session + post, now),
        "L2": l2_rule_conformance(strategy, t, session, 24, post, digits=5, spread=spread),
        "L3": l3_geometry(t, post, digits=5, declared_rr=5.0),
        "L4": l4_data_session(t, ref_window=w["ref"], trade_window=w["trade"], reference_name="Asian",
                              session=session, expected_bar_count=24, post=post, data_close=now, now=now),
        "L5": l5_cost(spread, t.get("risk_distance"), commission_r=None, warn_r=None),
        "L6": l6_freshness(t.get("valid_until") or "set", {"x": 1}, {"y": 1}),
    }


def failing(gate):
    return {c["id"] for c in gate["checks"] if c["verdict"] in (FAIL, NOT_EVALUABLE)}


def test_frozen_v1_1_1_contract_untouched_and_candidate_loads():
    frozen, cand = load_strategy(STRATEGY_PATH), load_strategy(CANDIDATE)
    assert (frozen.version, frozen.risk.stop_loss_range_pct, frozen.max_range_pips_eurusd) == ("1.1.1", 0.25, 25.0)
    assert (cand.version, cand.risk.stop_loss_mode, cand.risk.stop_loss_range_pct) == ("1.1.2", "SWEEP_CANDLE_WICK_EXTREME", None)
    raw = yaml.safe_load(Path(CANDIDATE).read_text())
    assert "trend_bias_filter" not in raw["regime_classification"]          # EMA_50 removed
    assert "range_session_check" not in raw["regime_classification"]
    assert cand.structural_invalidation == "NONE"


def test_loader_still_fails_loudly_when_range_stop_lacks_its_parameter(tmp_path):
    raw = yaml.safe_load(Path(STRATEGY_PATH).read_text())
    del raw["risk_and_money_management"]["stop_loss_range_pct"]
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump(raw))
    with pytest.raises(KeyError):
        load_strategy(str(bad))


def test_v1_1_1_l2_still_fails_on_its_frozen_divergences():
    _, g = gates("2026-06-23", STRATEGY_PATH)
    assert g["L2"]["status"] == FAIL
    assert {"R.trend_bias_filter", "R.range_session_check", "R.stop_loss", "R.structural_invalidation"} <= failing(g["L2"])


def test_candidate_conforming_sweep_passes_every_blocking_gate():
    t, g = gates("2026-06-23")
    assert (t["setup"], t["direction"], t["entry"], t["stop_loss"]) == ("SWEEP", "SHORT", 1.143, 1.14351)
    assert blocking_failures(g) == [], {k: failing(v) for k, v in g.items()}
    assert g["L6"]["status"] == PASS
    checks = {c["id"]: c for c in g["L2"]["checks"]}
    assert checks["R.structural_invalidation"]["verdict"] == NOT_APPLICABLE
    assert not any(c["verdict"] == NOT_EVALUABLE for c in g["L2"]["checks"])


@pytest.mark.parametrize("day,spread,expected", [
    ("2026-06-23", WIDE, {"R.max_spread_fraction"}),                                   # 0.8 pip > 15% of 5.1-pip stop
    ("2026-06-16", TIGHT, {"R.regime_branch", "R.entry_trigger", "R.entry_level", "R.stop_loss"}),   # TREND
    ("2026-06-17", TIGHT, {"R.entry_level", "R.target_order"}),                         # pre-signal open entry, TP1 > TP2
    ("2026-07-17", TIGHT, {"R.entry_level", "R.stop_loss", "R.target_leg2", "R.max_spread_fraction",
                           "R.target_order"}),                                           # zero stop
])
def test_candidate_fails_closed_only_on_declared_rules(day, spread, expected):
    _, g = gates(day, spread=spread)
    assert g["L1"]["status"] == PASS and g["L4"]["status"] == PASS
    assert g["L2"]["status"] == FAIL and failing(g["L2"]) == expected
    assert failing(g["L2"]) <= DECLARED_FAIL_CLOSED
    assert not any(c["verdict"] == NOT_EVALUABLE for c in g["L2"]["checks"])


def test_entry_fail_closed_names_the_reason():
    _, g = gates("2026-06-17")
    entry = next(c for c in g["L2"]["checks"] if c["id"] == "R.entry_level")
    assert entry["note"].startswith("ENTRY_NOT_AVAILABLE_AT_SIGNAL")


def test_registry_candidate_identity_matches_and_ready_stays_paused():
    entry = load_registry()["ST_ASIAN_SWEEP_5R_V1"]
    cand = entry["candidate_versions"]["1.1.2"]
    assert cand["logic_status"] == LOGIC_VERIFIED
    assert cand["logic_verified_identity"] == logic_identity("ST_ASIAN_SWEEP_5R_V1", "1.1.2")["digest"]
    assert cand["edge_verified"] is False and cand["economic_status"] == "NOT_EVALUATED"
    assert cand["ticket_ready"] == "PAUSED_PENDING_OWNER_CONFIRM"
    # The runtime authority is still v1.1.1: NOT_VERIFIED, so no TICKET_READY.
    assert entry["config_source"] == STRATEGY_PATH and entry["logic_status"] == NOT_VERIFIED
    assert resolve_ticket_authority("ST_ASIAN_SWEEP_5R_V1", "1.1.1").logic_status_effective == NOT_VERIFIED
    assert (entry["demo_authorized"], entry["live_authorized"]) == (False, False)
